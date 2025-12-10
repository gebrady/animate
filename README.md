# Landsat GIF Animator

Animate Landsat satellite scenes as GIF to show the world changing over time using USGS EarthExplorer.

## Features

- **Location Input**: Enter a city name or latitude/longitude coordinates
- **Time Series**: Automatically fetches one image per month from 2013 to present
- **Cloud Filtering**: Filters images with less than specified % cloud cover (configurable)
- **USGS EarthExplorer**: Uses USGS M2M API to search and access Landsat data
- **Multiple Visualization Modes**:
  - `rgb`: Natural color (Red, Green, Blue)
  - `false_color`: False color infrared (NIR, Red, Green)
  - `ndvi`: Normalized Difference Vegetation Index

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Set up USGS EarthExplorer credentials:
   
   Create a free account at https://ers.cr.usgs.gov/register/
   
   Then set your credentials as environment variables:
   ```bash
   export EARTHEXPLORER_USERNAME=your_username
   export EARTHEXPLORER_PASSWORD=your_password
   ```

   **Note**: You may need to approve M2M API access in your USGS account settings.

## Usage

### Basic Usage

Run the script and follow the prompts:
```bash
python animate.py
```

### Command Line Options

```bash
python animate.py --location "San Francisco" --mode rgb --cloud-cover 10 --fps 12
```

Or with coordinates:
```bash
python animate.py --location "37.7749,-122.4194" --mode ndvi
```

### Options

- `--location, -l`: City name or latitude,longitude coordinates (required)
- `--mode, -m`: Visualization mode (default: rgb)
  - `rgb`: Natural color
  - `false_color`: False color infrared
  - `ndvi`: Vegetation index
- `--cloud-cover, -c`: Maximum cloud cover percentage (default: 10)
- `--fps, -f`: Frames per second for output GIF (default: 12)

### Examples

1. Natural color view of New York:
```bash
export EARTHEXPLORER_USERNAME=your_username
export EARTHEXPLORER_PASSWORD=your_password
python animate.py -l "New York" -m rgb
```

2. Vegetation index for Amazon rainforest:
```bash
python animate.py -l "-3.4653,-62.2159" -m ndvi
```

## Output

Generated GIF files are saved in the `output/` directory with the naming format:
```
landsat_{location}_{mode}_{timestamp}.gif
```

## Requirements

- Python 3.7+
- USGS EarthExplorer account (free - register at https://ers.cr.usgs.gov/register/)
- Internet connection for fetching satellite imagery

## How It Works

1. **Location Resolution**: Converts city names to coordinates using geocoding
2. **Authentication**: Authenticates with USGS EarthExplorer M2M API using credentials from environment variables
3. **Scene Search**: Queries USGS EarthExplorer for Landsat 8 Collection 2 scenes from 2013-present
4. **Cloud Filtering**: Filters scenes with cloud cover below threshold
5. **Monthly Selection**: Selects the best (lowest cloud cover) scene for each month
6. **Visualization**: Applies the selected visualization mode to each scene
7. **GIF Creation**: Combines all images into an animated GIF at specified frame rate

## Data Source

This tool uses **Landsat 8 Collection 2** imagery from USGS EarthExplorer:
- Temporal coverage: 2013 to present
- Spatial resolution: 30 meters
- Revisit time: 16 days
- Bands: Multiple spectral bands from visible to thermal infrared
- Access: Via USGS Machine-to-Machine (M2M) API

## Environment Variables

- `EARTHEXPLORER_USERNAME`: Your USGS EarthExplorer username (required)
- `EARTHEXPLORER_PASSWORD`: Your USGS EarthExplorer password (required)

## License

See repository license.
