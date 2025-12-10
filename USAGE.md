# Landsat GIF Animator - Usage Guide

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Authenticate with Google Earth Engine**
   
   **Option 1: User Authentication (Interactive)**
   ```bash
   earthengine authenticate
   ```
   This will open a browser window to authenticate with your Google account.

   **Option 2: Service Account Authentication (Automated)**
   
   Using a credentials file:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ```
   
   Or using environment variables:
   ```bash
   export EE_SERVICE_ACCOUNT=your-service-account@project.iam.gserviceaccount.com
   export EE_PRIVATE_KEY='{"type": "service_account", "project_id": "your-project", ...}'
   ```

3. **(Optional) Configure Landsat Collection**
   ```bash
   export LANDSAT_COLLECTION=LANDSAT/LC08/C02/T1_L2
   ```

4. **Run the Tool**
   ```bash
   python animate.py --location "Your City" --mode rgb
   ```

## Detailed Examples

### Example 1: Natural Color View of San Francisco
```bash
python animate.py -l "San Francisco" -m rgb -c 10 -f 12
```
Creates a natural color time-lapse showing the urban development and seasonal changes.

### Example 2: Vegetation Index of Amazon Rainforest
```bash
python animate.py -l "-3.4653,-62.2159" -m ndvi -c 5
```
Shows vegetation health over time. Green indicates healthy vegetation, while brown/red shows deforestation.

### Example 3: Snow Coverage in Swiss Alps
```bash
python animate.py -l "Zermatt, Switzerland" -m snow -c 5
```
Tracks snow coverage changes throughout the seasons and years.

### Example 4: Urban Development in Dubai
```bash
python animate.py -l "Dubai, UAE" -m built_up -c 10
```
Highlights urban expansion with red/yellow colors showing built-up areas.

### Example 5: False Color Infrared of Agricultural Area
```bash
python animate.py -l "Iowa City" -m false_color -c 10
```
Shows vegetation in red/pink tones, useful for monitoring crops and forests.

### Example 6: High-Resolution Panchromatic View
```bash
python animate.py -l "37.7749,-122.4194" -m panchromatic -c 10
```
Uses the high-resolution panchromatic band for detailed grayscale imagery.

## Understanding Visualization Modes

### RGB (Natural Color)
- **Bands**: Red, Green, Blue
- **Use case**: Natural appearance, similar to what human eye sees
- **Good for**: Urban areas, water bodies, general landscapes

### False Color Infrared
- **Bands**: Near-Infrared, Red, Green
- **Use case**: Vegetation appears in shades of red/pink
- **Good for**: Forest monitoring, agricultural assessment

### NDVI (Normalized Difference Vegetation Index)
- **Range**: -1 to 1
- **Colors**: Blue (water/no vegetation) → White → Green (healthy vegetation)
- **Use case**: Vegetation health monitoring
- **Good for**: Deforestation tracking, crop health, drought monitoring

### Panchromatic
- **Band**: High-resolution grayscale (15m resolution)
- **Use case**: Detailed structural features
- **Good for**: Urban planning, infrastructure monitoring

### Built-up Index
- **Range**: -1 to 1
- **Colors**: White → Yellow → Red (built-up areas)
- **Use case**: Urban development tracking
- **Good for**: Urbanization studies, construction monitoring

### Snow Index (NDSI)
- **Range**: -1 to 1
- **Colors**: Black → Cyan → White (snow/ice)
- **Use case**: Snow and ice coverage
- **Good for**: Glaciers, seasonal snow, climate studies

## Tips for Best Results

1. **Cloud Cover**: Lower values (5-10%) give cleaner results but may reduce the number of available images
2. **Location**: Areas with frequent cloud cover (tropics) may have fewer available images
3. **Time Period**: Landsat 8 data starts from 2013. Earlier data would require Landsat 5/7
4. **Scale**: 1:60000 scale provides ~60km x 60km view, good for cities and large features
5. **FPS**: 12 FPS is good for smooth playback, but you can increase for faster playback

## Troubleshooting

### "Error initializing Earth Engine"
- **Default authentication**: Run `earthengine authenticate` to set up user credentials
- **Service account**: Set `GOOGLE_APPLICATION_CREDENTIALS` to your service account key file
- **Environment variables**: Set both `EE_SERVICE_ACCOUNT` and `EE_PRIVATE_KEY`
- Make sure you have a Google account with Earth Engine access

### "No images found matching criteria"
- Try increasing the cloud cover threshold
- Check if the location is correct
- Some remote areas may have limited coverage

### "Location not found"
- Use coordinates (lat,long) instead of city name
- Make sure city name is spelled correctly
- Try adding country name: "Paris, France"

## Output Files

Generated GIFs are saved in the `output/` directory with this naming format:
```
landsat_{location}_{mode}_{timestamp}.gif
```

Example:
```
landsat_San_Francisco_rgb_20231209_143022.gif
```

## Technical Details

- **Data Source**: Landsat 8 Collection 2, Tier 1, Level 2
- **Temporal Coverage**: April 2013 to present
- **Spatial Resolution**: 30m (15m panchromatic)
- **Output Size**: 1024 x 1024 pixels
- **Map Scale**: 1:60000
- **Frame Selection**: One per month (lowest cloud cover)
- **File Format**: GIF with configurable frame rate

## API Usage

You can also use the `LandsatAnimator` class in your own Python scripts:

```python
from animate import LandsatAnimator

# Create animator
animator = LandsatAnimator()

# Generate animation
animator.generate_animation(
    location="New York",
    mode="rgb",
    cloud_cover=10,
    fps=12
)
```

## Advanced Options

### Environment Variables

The tool supports the following environment variables:

- **`LANDSAT_COLLECTION`**: Override the default Landsat collection path
  - Default: `LANDSAT/LC08/C02/T1_L2` (Landsat 8 Collection 2)
  - Example: `export LANDSAT_COLLECTION=LANDSAT/LC09/C02/T1_L2` (for Landsat 9)

- **`GOOGLE_APPLICATION_CREDENTIALS`**: Path to service account credentials file
  - Example: `export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json`

- **`EE_SERVICE_ACCOUNT`**: Service account email address
  - Example: `export EE_SERVICE_ACCOUNT=your-sa@project.iam.gserviceaccount.com`

- **`EE_PRIVATE_KEY`**: Service account private key as JSON string
  - Example: `export EE_PRIVATE_KEY='{"type": "service_account", ...}'`

### Programmatic Usage

For more control, you can modify the `animate.py` script:
- Change the date range in `generate_animation()`
- Adjust the scale in `calculate_region()`
- Modify visualization parameters in `VISUALIZATION_MODES`
- Add custom visualization modes

## Resources

- [Google Earth Engine](https://earthengine.google.com/)
- [Landsat 8 Information](https://www.usgs.gov/landsat-missions/landsat-8)
- [Earth Engine Data Catalog](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2)
