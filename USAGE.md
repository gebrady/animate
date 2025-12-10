# Landsat GIF Animator - Usage Guide

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set USGS EarthExplorer Credentials**
   
   Create a free account at https://ers.cr.usgs.gov/register/
   
   Then set your credentials as environment variables:
   ```bash
   export EARTHEXPLORER_USERNAME=your_username
   export EARTHEXPLORER_PASSWORD=your_password
   ```
   
   **Note**: You may need to approve M2M API access in your USGS account settings.

3. **Run the Tool**
   ```bash
   python animate.py --location "Your City" --mode rgb
   ```

## Detailed Examples

### Example 1: Natural Color View of San Francisco
```bash
export EARTHEXPLORER_USERNAME=your_username
export EARTHEXPLORER_PASSWORD=your_password
python animate.py -l "San Francisco" -m rgb -c 10 -f 12
```
Searches for Landsat scenes showing the urban development and seasonal changes.

### Example 2: Vegetation Index of Amazon Rainforest
```bash
python animate.py -l "-3.4653,-62.2159" -m ndvi -c 5
```
Searches for scenes to show vegetation health over time.
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
- **Expression**: (NIR - RED) / (NIR + RED)
- **Use case**: Vegetation health monitoring
- **Good for**: Deforestation tracking, crop health, drought monitoring

## Tips for Best Results

1. **Cloud Cover**: Lower values (5-10%) give cleaner results but may reduce the number of available scenes
2. **Location**: Areas with frequent cloud cover (tropics) may have fewer available scenes
3. **Time Period**: Landsat 8 data starts from 2013
4. **Search Area**: The search uses a ~55km box around the specified coordinates
5. **Monthly Selection**: The tool selects one scene per month with the lowest cloud cover

## Troubleshooting

### "Error authenticating with USGS EarthExplorer"
- Verify your USGS EarthExplorer credentials are correct
- Ensure your account is activated (check your email for activation link)
- Make sure you have approved M2M API access in your account settings at https://ers.cr.usgs.gov/

### "No scenes found matching criteria"
- Try increasing the cloud cover threshold with `-c` option
- Check if the location coordinates are correct
- Some remote areas may have limited coverage
- Try a different date range or location

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
- **Spatial Resolution**: 30m
- **Search Area**: ~55km x 55km box around coordinates
- **Frame Selection**: One per month (lowest cloud cover)
- **File Format**: GIF with configurable frame rate

## API Usage

You can also use the `LandsatAnimator` class in your own Python scripts:

```python
import os
from animate import LandsatAnimator

# Set credentials
os.environ['EARTHEXPLORER_USERNAME'] = 'your_username'
os.environ['EARTHEXPLORER_PASSWORD'] = 'your_password'

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

For more control, you can modify the `animate.py` script:
- Change the date range in `generate_animation()`
- Adjust the search area in `search_scenes()`
- Modify visualization parameters in `VISUALIZATION_MODES`
- Add custom visualization modes

## Resources

- [USGS EarthExplorer](https://earthexplorer.usgs.gov/)
- [USGS M2M API Documentation](https://m2m.cr.usgs.gov/)
- [Landsat 8 Information](https://www.usgs.gov/landsat-missions/landsat-8)
- [USGS Account Registration](https://ers.cr.usgs.gov/register/)
