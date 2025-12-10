#!/usr/bin/env python3
"""
Landsat GIF Animator - Creates animated GIFs from Landsat satellite imagery
"""

import os
import sys
import click
import ee
from geopy.geocoders import Nominatim
import imageio
import numpy as np
from datetime import datetime, timedelta
import json
import urllib.request
from google.oauth2 import service_account


class LandsatAnimator:
    """Creates animated GIFs from Landsat satellite imagery"""
    
    # Visualization modes and their band configurations
    # Using Landsat Collection 2 Level 2 surface reflectance bands (SR_B*)
    VISUALIZATION_MODES = {
        'rgb': {
            'bands': ['SR_B4', 'SR_B3', 'SR_B2'],  # Red, Green, Blue for Landsat 8
            'min': 0,
            'max': 0.3,
            'description': 'Natural color (RGB)'
        },
        'false_color': {
            'bands': ['SR_B5', 'SR_B4', 'SR_B3'],  # NIR, Red, Green
            'min': 0,
            'max': 0.3,
            'description': 'False color infrared'
        },
        'ndvi': {
            'expression': '(NIR - RED) / (NIR + RED)',
            'bands': {'NIR': 'SR_B5', 'RED': 'SR_B4'},
            'palette': ['blue', 'white', 'green'],
            'min': -1,
            'max': 1,
            'description': 'Normalized Difference Vegetation Index'
        },
        'panchromatic': {
            'bands': ['SR_B8'],  # Panchromatic band
            'min': 0,
            'max': 0.3,
            'description': 'Panchromatic (grayscale)'
        },
        'built_up': {
            'expression': '(SWIR - NIR) / (SWIR + NIR)',
            'bands': {'SWIR': 'SR_B6', 'NIR': 'SR_B5'},
            'palette': ['white', 'yellow', 'red'],
            'min': -1,
            'max': 1,
            'description': 'Built-up index'
        },
        'snow': {
            'expression': '(GREEN - SWIR) / (GREEN + SWIR)',
            'bands': {'GREEN': 'SR_B3', 'SWIR': 'SR_B6'},
            'palette': ['black', 'cyan', 'white'],
            'min': -1,
            'max': 1,
            'description': 'Normalized Difference Snow Index'
        }
    }
    
    def __init__(self):
        """Initialize the animator"""
        self.output_dir = 'output'
        os.makedirs(self.output_dir, exist_ok=True)
        
    def initialize_earth_engine(self):
        """Initialize Google Earth Engine with support for service account authentication via environment variables"""
        try:
            # Check for service account authentication via environment variables
            service_account_email = os.environ.get('EE_SERVICE_ACCOUNT')
            private_key_json = os.environ.get('EE_PRIVATE_KEY')
            credentials_file = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            
            if service_account_email and private_key_json:
                # Authenticate using service account email and private key from environment variables
                click.echo("Authenticating with service account from environment variables...")
                private_key_data = json.loads(private_key_json)
                credentials = service_account.Credentials.from_service_account_info(
                    private_key_data,
                    scopes=['https://www.googleapis.com/auth/earthengine']
                )
                ee.Initialize(credentials=credentials)
                click.echo("Successfully authenticated with service account.")
            elif credentials_file:
                # Authenticate using credentials file path from environment variable
                click.echo(f"Authenticating with credentials file: {credentials_file}")
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_file,
                    scopes=['https://www.googleapis.com/auth/earthengine']
                )
                ee.Initialize(credentials=credentials)
                click.echo("Successfully authenticated with credentials file.")
            else:
                # Fall back to default authentication (user credentials)
                ee.Initialize()
                click.echo("Using default Earth Engine authentication.")
        except Exception as e:
            click.echo(f"Error initializing Earth Engine: {e}")
            click.echo("\nAuthentication options:")
            click.echo("1. Default: Run 'earthengine authenticate' to set up user credentials")
            click.echo("2. Service Account: Set EE_SERVICE_ACCOUNT and EE_PRIVATE_KEY environment variables")
            click.echo("3. Credentials File: Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
            sys.exit(1)
    
    def get_coordinates(self, location):
        """
        Convert city name or lat/long to coordinates
        
        Args:
            location: Either "lat,long" string or city name
            
        Returns:
            Tuple of (latitude, longitude)
        """
        # Check if input is already coordinates
        if ',' in location:
            try:
                parts = location.split(',')
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return lat, lon
            except ValueError:
                pass
        
        # Geocode city name
        try:
            geolocator = Nominatim(user_agent="landsat_animator")
            location_data = geolocator.geocode(location)
            if location_data:
                return location_data.latitude, location_data.longitude
            else:
                raise ValueError(f"Could not find location: {location}")
        except Exception as e:
            raise ValueError(f"Error geocoding location: {e}")
    
    def calculate_region(self, lat, lon, scale=60000):
        """
        Calculate bounding box for 1:scale view at given coordinates
        
        Args:
            lat: Latitude
            lon: Longitude
            scale: Map scale (default 1:60000)
            
        Returns:
            Earth Engine Geometry
        """
        # For 1024 pixels, calculate the ground distance
        # At 1:60000 scale, 1024 pixels = 61.44 km (60m per pixel)
        meters_per_pixel = scale / 1000  # 60m at 1:60000
        width_meters = 1024 * meters_per_pixel
        
        # Convert to degrees (approximate)
        # At equator: 1 degree ≈ 111,320 meters
        # This is approximate and works reasonably well for small areas
        lat_degrees = width_meters / 111320
        lon_degrees = width_meters / (111320 * np.cos(np.radians(lat)))
        
        # Create bounding box
        return ee.Geometry.Rectangle([
            lon - lon_degrees / 2,
            lat - lat_degrees / 2,
            lon + lon_degrees / 2,
            lat + lat_degrees / 2
        ])
    
    def scale_landsat_c2(self, image):
        """
        Apply scaling factors for Landsat Collection 2 Level 2 surface reflectance
        
        Args:
            image: Earth Engine Image
            
        Returns:
            Scaled image
        """
        # Optical bands (scale factor: 0.0000275, offset: -0.2)
        optical_bands = image.select('SR_B.').multiply(0.0000275).add(-0.2)
        
        # Return scaled image
        return image.addBands(optical_bands, None, True)
    
    def get_landsat_collection(self, region, start_date, end_date, cloud_cover=10):
        """
        Get Landsat image collection for the region and time period
        
        Args:
            region: Earth Engine Geometry
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            cloud_cover: Maximum cloud cover percentage
            
        Returns:
            Earth Engine ImageCollection
        """
        # Get Landsat collection path from environment variable or use default
        collection_path = os.environ.get('LANDSAT_COLLECTION', 'LANDSAT/LC08/C02/T1_L2')
        
        # Use Landsat 8 Collection 2, Tier 1, Level 2 (Surface Reflectance) by default
        collection = ee.ImageCollection(collection_path) \
            .filterBounds(region) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUD_COVER', cloud_cover)) \
            .map(self.scale_landsat_c2)
        
        return collection
    
    def get_monthly_images(self, collection, region):
        """
        Get one image per month from the collection
        
        Args:
            collection: Earth Engine ImageCollection
            region: Earth Engine Geometry
            
        Returns:
            List of image info dictionaries
        """
        # Get collection size
        size = collection.size().getInfo()
        
        if size == 0:
            return []
        
        # Get all dates and cloud cover values in batch (more efficient than N+1 queries)
        images_list = collection.toList(size)
        dates = collection.aggregate_array('system:time_start').getInfo()
        cloud_covers = collection.aggregate_array('CLOUD_COVER').getInfo()
        
        # Group by year-month
        monthly_images = {}
        
        for i in range(size):
            # Format date as YYYY-MM
            date_ms = dates[i]
            date_obj = datetime.utcfromtimestamp(date_ms / 1000)
            date_str = date_obj.strftime('%Y-%m')
            
            cloud_cover = cloud_covers[i]
            
            # Keep the image with lowest cloud cover for each month
            if date_str not in monthly_images or cloud_cover < monthly_images[date_str]['cloud_cover']:
                monthly_images[date_str] = {
                    'image': ee.Image(images_list.get(i)),
                    'date': date_str,
                    'cloud_cover': cloud_cover
                }
        
        # Sort by date
        sorted_images = sorted(monthly_images.values(), key=lambda x: x['date'])
        
        return sorted_images
    
    def apply_visualization(self, image, mode='rgb'):
        """
        Apply visualization to image
        
        Args:
            image: Earth Engine Image
            mode: Visualization mode
            
        Returns:
            Visualized image
        """
        vis_config = self.VISUALIZATION_MODES.get(mode, self.VISUALIZATION_MODES['rgb'])
        
        if 'expression' in vis_config:
            # Calculate index using expression
            result = image.expression(
                vis_config['expression'],
                vis_config['bands']
            )
            
            # Apply color palette
            if 'palette' in vis_config:
                result = result.visualize(
                    min=vis_config['min'],
                    max=vis_config['max'],
                    palette=vis_config['palette']
                )
        else:
            # Select bands and visualize
            result = image.select(vis_config['bands']).visualize(
                min=vis_config['min'],
                max=vis_config['max']
            )
        
        return result
    
    def download_image(self, image, region, filename):
        """
        Download image from Earth Engine
        
        Args:
            image: Earth Engine Image
            region: Earth Engine Geometry
            filename: Output filename
        """
        # Get download URL
        url = image.getDownloadURL({
            'region': region,
            'dimensions': 1024,
            'format': 'png'
        })
        
        # Download the image
        filepath = os.path.join(self.output_dir, filename)
        urllib.request.urlretrieve(url, filepath)
        
        return filepath
    
    def create_gif(self, image_files, output_filename, fps=12):
        """
        Create animated GIF from image files
        
        Args:
            image_files: List of image file paths
            output_filename: Output GIF filename
            fps: Frames per second
        """
        images = []
        for filepath in image_files:
            img = imageio.imread(filepath)
            images.append(img)
        
        output_path = os.path.join(self.output_dir, output_filename)
        imageio.mimsave(output_path, images, fps=fps)
        
        return output_path
    
    def generate_animation(self, location, mode='rgb', cloud_cover=10, fps=12):
        """
        Generate animated GIF for location
        
        Args:
            location: City name or "lat,long"
            mode: Visualization mode
            cloud_cover: Maximum cloud cover percentage
            fps: Frames per second for GIF
            
        Returns:
            Path to generated GIF
        """
        click.echo(f"Processing location: {location}")
        
        # Get coordinates
        lat, lon = self.get_coordinates(location)
        click.echo(f"Coordinates: {lat}, {lon}")
        
        # Initialize Earth Engine
        self.initialize_earth_engine()
        
        # Calculate region
        region = self.calculate_region(lat, lon)
        
        # Get Landsat collection (from 2013 when Landsat 8 launched to present)
        start_date = '2013-01-01'
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        click.echo(f"Fetching Landsat images from {start_date} to {end_date}")
        click.echo(f"Cloud cover filter: <{cloud_cover}%")
        click.echo(f"Visualization mode: {mode} - {self.VISUALIZATION_MODES[mode]['description']}")
        
        # Show which collection is being used
        collection_path = os.environ.get('LANDSAT_COLLECTION', 'LANDSAT/LC08/C02/T1_L2')
        click.echo(f"Using collection: {collection_path}")
        
        collection = self.get_landsat_collection(region, start_date, end_date, cloud_cover)
        
        # Get monthly images
        monthly_images = self.get_monthly_images(collection, region)
        
        if not monthly_images:
            click.echo("Error: No images found matching criteria")
            sys.exit(1)
        
        click.echo(f"Found {len(monthly_images)} monthly images")
        
        # Download and process images
        image_files = []
        
        with click.progressbar(monthly_images, label='Processing images') as images:
            for img_info in images:
                # Apply visualization
                vis_image = self.apply_visualization(img_info['image'], mode)
                
                # Download image
                filename = f"landsat_{img_info['date']}.png"
                filepath = self.download_image(vis_image, region, filename)
                image_files.append(filepath)
        
        # Create GIF
        click.echo("Creating animated GIF...")
        location_safe = location.replace(' ', '_').replace(',', '_')
        output_filename = f"landsat_{location_safe}_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif"
        gif_path = self.create_gif(image_files, output_filename, fps)
        
        # Clean up temporary files
        for filepath in image_files:
            os.remove(filepath)
        
        click.echo(f"\nGIF created successfully: {gif_path}")
        click.echo(f"Number of frames: {len(image_files)}")
        click.echo(f"Frame rate: {fps} FPS")
        
        return gif_path


@click.command()
@click.option('--location', '-l', prompt='Enter city name or lat,long coordinates', 
              help='City name or latitude,longitude coordinates')
@click.option('--mode', '-m', 
              type=click.Choice(list(LandsatAnimator.VISUALIZATION_MODES.keys())),
              default='rgb',
              help='Visualization mode')
@click.option('--cloud-cover', '-c', default=10, 
              help='Maximum cloud cover percentage (default: 10)')
@click.option('--fps', '-f', default=12,
              help='Frames per second for GIF (default: 12)')
def main(location, mode, cloud_cover, fps):
    """
    Create animated GIF from Landsat satellite imagery
    
    This tool fetches Landsat images for a specific location, filters by cloud cover,
    selects one image per month from the archive, and creates an animated GIF showing
    changes over time.
    """
    try:
        animator = LandsatAnimator()
        
        # Show available modes
        click.echo("\nAvailable visualization modes:")
        for mode_name, config in LandsatAnimator.VISUALIZATION_MODES.items():
            click.echo(f"  - {mode_name}: {config['description']}")
        click.echo()
        
        animator.generate_animation(location, mode, cloud_cover, fps)
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
