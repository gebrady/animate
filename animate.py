#!/usr/bin/env python3
"""
Landsat GIF Animator - Creates animated GIFs from Landsat satellite imagery using USGS EarthExplorer
"""

import os
import sys
import click
import requests
from geopy.geocoders import Nominatim
import imageio
import numpy as np
from datetime import datetime, timedelta
import json


class LandsatAnimator:
    """Creates animated GIFs from Landsat satellite imagery using USGS EarthExplorer M2M API"""
    
    # USGS M2M API endpoint
    M2M_API_URL = "https://m2m.cr.usgs.gov/api/api/json/stable/"
    
    # Landsat 8 Collection 2 dataset
    LANDSAT_DATASET = "landsat_ot_c2_l2"
    
    # Visualization modes and their band configurations
    VISUALIZATION_MODES = {
        'rgb': {
            'bands': ['B4', 'B3', 'B2'],  # Red, Green, Blue
            'description': 'Natural color (RGB)'
        },
        'false_color': {
            'bands': ['B5', 'B4', 'B3'],  # NIR, Red, Green
            'description': 'False color infrared'
        },
        'ndvi': {
            'expression': '(NIR - RED) / (NIR + RED)',
            'bands': {'NIR': 'B5', 'RED': 'B4'},
            'description': 'Normalized Difference Vegetation Index'
        }
    }
    
    def __init__(self):
        """Initialize the animator"""
        self.output_dir = 'output'
        os.makedirs(self.output_dir, exist_ok=True)
        self.api_key = None
        
    def authenticate_earthexplorer(self):
        """Authenticate with USGS EarthExplorer M2M API using environment variables"""
        username = os.environ.get('EARTHEXPLORER_USERNAME')
        password = os.environ.get('EARTHEXPLORER_PASSWORD')
        
        if not username or not password:
            click.echo("Error: EARTHEXPLORER_USERNAME and EARTHEXPLORER_PASSWORD environment variables are required")
            click.echo("\nPlease set your USGS EarthExplorer credentials:")
            click.echo("  export EARTHEXPLORER_USERNAME=your_username")
            click.echo("  export EARTHEXPLORER_PASSWORD=your_password")
            click.echo("\nCreate an account at: https://ers.cr.usgs.gov/register/")
            sys.exit(1)
        
        try:
            click.echo("Authenticating with USGS EarthExplorer M2M API...")
            
            # Login to M2M API
            login_payload = {
                "username": username,
                "password": password
            }
            
            response = requests.post(
                f"{self.M2M_API_URL}login",
                json=login_payload,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
            
            data = response.json()
            
            if data.get('errorCode'):
                raise Exception(f"Authentication failed: {data.get('errorMessage', 'Unknown error')}")
            
            self.api_key = data.get('data')
            
            if not self.api_key:
                raise Exception("No API key returned from authentication")
            
            click.echo("Successfully authenticated with USGS EarthExplorer.")
            
        except requests.exceptions.RequestException as e:
            click.echo(f"Network error during authentication: {e}")
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error authenticating with USGS EarthExplorer: {e}")
            click.echo("\nPlease verify:")
            click.echo("  1. Your USGS EarthExplorer credentials are correct")
            click.echo("  2. Your account is activated")
            click.echo("  3. You have approved Machine-to-Machine API access in your account settings")
            sys.exit(1)
    
    def logout(self):
        """Logout from USGS M2M API"""
        if self.api_key:
            try:
                requests.post(
                    f"{self.M2M_API_URL}logout",
                    headers={"X-Auth-Token": self.api_key},
                    timeout=10
                )
            except:
                pass  # Best effort logout
    
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
    
    def search_scenes(self, lat, lon, start_date, end_date, max_cloud_cover=10):
        """
        Search for Landsat scenes using USGS M2M API
        
        Args:
            lat: Latitude
            lon: Longitude
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            max_cloud_cover: Maximum cloud cover percentage
            
        Returns:
            List of scene IDs
        """
        click.echo(f"Searching for Landsat scenes from {start_date} to {end_date}")
        click.echo(f"Location: {lat}, {lon}")
        click.echo(f"Max cloud cover: {max_cloud_cover}%")
        
        # Create spatial filter (bounding box around point)
        # Approximately 0.5 degree box (~55km at equator)
        bbox_size = 0.25
        spatial_filter = {
            "filterType": "mbr",
            "lowerLeft": {
                "latitude": lat - bbox_size,
                "longitude": lon - bbox_size
            },
            "upperRight": {
                "latitude": lat + bbox_size,
                "longitude": lon + bbox_size
            }
        }
        
        # Create temporal filter
        temporal_filter = {
            "start": start_date,
            "end": end_date
        }
        
        # Create cloud cover filter
        cloud_cover_filter = {
            "filterType": "value",
            "filterId": "5e83d08fd0458",  # Cloud cover filter ID
            "value": max_cloud_cover,
            "operand": "<=",
        }
        
        # Search request
        search_payload = {
            "datasetName": self.LANDSAT_DATASET,
            "spatialFilter": spatial_filter,
            "temporalFilter": temporal_filter,
            "maxResults": 500,
        }
        
        try:
            response = requests.post(
                f"{self.M2M_API_URL}scene-search",
                json=search_payload,
                headers={"X-Auth-Token": self.api_key},
                timeout=60
            )
            
            if response.status_code != 200:
                raise Exception(f"Search failed with status code {response.status_code}")
            
            data = response.json()
            
            if data.get('errorCode'):
                raise Exception(f"Search failed: {data.get('errorMessage', 'Unknown error')}")
            
            results = data.get('data', {}).get('results', [])
            
            # Filter by cloud cover manually if needed and sort by date
            scenes = []
            for result in results:
                cloud_cover = result.get('cloudCover', 100)
                if cloud_cover <= max_cloud_cover:
                    scenes.append({
                        'entity_id': result.get('entityId'),
                        'display_id': result.get('displayId'),
                        'acquisition_date': result.get('temporalCoverage', {}).get('startDate', ''),
                        'cloud_cover': cloud_cover
                    })
            
            # Sort by acquisition date
            scenes.sort(key=lambda x: x['acquisition_date'])
            
            click.echo(f"Found {len(scenes)} scenes matching criteria")
            return scenes
            
        except requests.exceptions.RequestException as e:
            click.echo(f"Network error during scene search: {e}")
            return []
        except Exception as e:
            click.echo(f"Error searching for scenes: {e}")
            return []
    
    def get_monthly_scenes(self, scenes):
        """
        Select one scene per month (lowest cloud cover)
        
        Args:
            scenes: List of scene dictionaries
            
        Returns:
            List of selected scenes
        """
        monthly_scenes = {}
        
        for scene in scenes:
            # Extract year-month from acquisition date
            date_str = scene['acquisition_date'][:7]  # YYYY-MM
            
            if date_str not in monthly_scenes or scene['cloud_cover'] < monthly_scenes[date_str]['cloud_cover']:
                monthly_scenes[date_str] = scene
        
        # Sort by date
        selected_scenes = sorted(monthly_scenes.values(), key=lambda x: x['acquisition_date'])
        
        click.echo(f"Selected {len(selected_scenes)} scenes (one per month)")
        return selected_scenes
    
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
        Generate animated GIF for location using USGS EarthExplorer
        
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
        
        # Authenticate with USGS EarthExplorer
        self.authenticate_earthexplorer()
        
        try:
            # Search for Landsat scenes (from 2013 when Landsat 8 launched to present)
            start_date = '2013-01-01'
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            click.echo(f"Visualization mode: {mode} - {self.VISUALIZATION_MODES[mode]['description']}")
            
            scenes = self.search_scenes(lat, lon, start_date, end_date, cloud_cover)
            
            if not scenes:
                click.echo("Error: No scenes found matching criteria")
                sys.exit(1)
            
            # Select monthly scenes
            monthly_scenes = self.get_monthly_scenes(scenes)
            
            if not monthly_scenes:
                click.echo("Error: No monthly scenes available")
                sys.exit(1)
            
            # Note: Full implementation would download and process scene data here
            # This requires additional logic to download scene files, extract bands, and create visualizations
            # For now, we demonstrate the authentication and search functionality
            
            click.echo("\nNote: Scene download and processing is not yet fully implemented.")
            click.echo("Found the following scenes that would be processed:")
            
            for i, scene in enumerate(monthly_scenes[:10]):  # Show first 10
                click.echo(f"  {i+1}. {scene['display_id']} - {scene['acquisition_date'][:10]} - {scene['cloud_cover']:.1f}% clouds")
            
            if len(monthly_scenes) > 10:
                click.echo(f"  ... and {len(monthly_scenes) - 10} more")
            
            click.echo("\nTo complete the implementation, scene download and image processing logic is needed.")
            click.echo("This would involve downloading GeoTIFF files and processing bands locally.")
            
        finally:
            # Logout
            self.logout()
        
        return None


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
    Create animated GIF from Landsat satellite imagery using USGS EarthExplorer
    
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
