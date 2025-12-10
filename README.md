# Landsat GIF Animator

Animate Landsat satellite scenes as GIF to show the world changing over time.

## Features

- **Location Input**: Enter a city name or latitude/longitude coordinates
- **Time Series**: Automatically fetches one image per month from 2013 to present
- **Cloud Filtering**: Filters images with less than 10% cloud cover (configurable)
- **Multiple Visualization Modes**:
  - `rgb`: Natural color (Red, Green, Blue)
  - `false_color`: False color infrared (NIR, Red, Green)
  - `ndvi`: Normalized Difference Vegetation Index
  - `panchromatic`: High-resolution grayscale
  - `built_up`: Built-up area index
  - `snow`: Normalized Difference Snow Index
- **High Quality Output**: 1024x1024 pixel GIF at 12 FPS (configurable)
- **1:60000 Scale**: Provides consistent scale across all images

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Authenticate with Google Earth Engine:

   **Option 1: User Authentication (Default)**
   ```bash
   earthengine authenticate
   ```

   **Option 2: Service Account with JSON Key**
   
   Set the path to your service account credentials file:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ```

   **Option 3: Service Account with Environment Variables**
   
   Set your service account email and private key directly:
   ```bash
   export EE_SERVICE_ACCOUNT=your-service-account@project.iam.gserviceaccount.com
   export EE_PRIVATE_KEY='{"type": "service_account", "project_id": "your-project", ...}'
   ```

3. (Optional) Configure Landsat Collection:
   
   By default, the tool uses Landsat 8 Collection 2. You can override this:
   ```bash
   export LANDSAT_COLLECTION=LANDSAT/LC08/C02/T1_L2
   ```

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
  - `panchromatic`: Grayscale
  - `built_up`: Built-up area index
  - `snow`: Snow index
- `--cloud-cover, -c`: Maximum cloud cover percentage (default: 10)
- `--fps, -f`: Frames per second for output GIF (default: 12)

### Examples

1. Natural color view of New York:
```bash
python animate.py -l "New York" -m rgb
```

2. Vegetation index for Amazon rainforest:
```bash
python animate.py -l "-3.4653,-62.2159" -m ndvi
```

3. Snow coverage in the Alps:
```bash
python animate.py -l "Chamonix, France" -m snow -c 5
```

4. Urban development in Dubai:
```bash
python animate.py -l "Dubai" -m built_up
```

## Output

Generated GIF files are saved in the `output/` directory with the naming format:
```
landsat_{location}_{mode}_{timestamp}.gif
```

## Requirements

- Python 3.7+
- Google Earth Engine account (free)
- Internet connection for fetching satellite imagery

## How It Works

1. **Location Resolution**: Converts city names to coordinates using geocoding
2. **Region Calculation**: Calculates a bounding box at 1:60000 scale (approximately 60km x 60km)
3. **Image Collection**: Queries Landsat 8 Collection 2 imagery from 2013-present
4. **Cloud Filtering**: Filters images with cloud cover below threshold
5. **Monthly Selection**: Selects the best (lowest cloud cover) image for each month
6. **Visualization**: Applies the selected visualization mode to each image
7. **GIF Creation**: Combines all images into an animated GIF at specified frame rate

## Data Source

This tool uses **Landsat 8 Collection 2, Tier 1** imagery from Google Earth Engine:
- Temporal coverage: 2013 to present
- Spatial resolution: 30 meters (15m for panchromatic)
- Revisit time: 16 days
- Bands: Multiple spectral bands from visible to thermal infrared

## License

See repository license.
