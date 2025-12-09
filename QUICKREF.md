# Landsat GIF Animator - Quick Reference

## Installation
```bash
pip install -r requirements.txt
earthengine authenticate
```

## Basic Usage
```bash
python animate.py -l "New York" -m rgb
```

## Visualization Modes

| Mode | Description | Best For |
|------|-------------|----------|
| `rgb` | Natural color | General landscapes, cities |
| `false_color` | Infrared false color | Vegetation, forests |
| `ndvi` | Vegetation index | Deforestation, crop health |
| `panchromatic` | High-res grayscale | Infrastructure details |
| `built_up` | Urban areas | Urban development |
| `snow` | Snow/ice coverage | Glaciers, seasonal snow |

## Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--location` | `-l` | (prompt) | City name or "lat,long" |
| `--mode` | `-m` | `rgb` | Visualization mode |
| `--cloud-cover` | `-c` | `10` | Max cloud cover % |
| `--fps` | `-f` | `12` | GIF frame rate |

## Examples

### Natural Color View
```bash
python animate.py -l "San Francisco" -m rgb
```

### Vegetation Monitoring
```bash
python animate.py -l "-3.4653,-62.2159" -m ndvi -c 5
```

### Urban Growth
```bash
python animate.py -l "Dubai" -m built_up
```

### Snow Coverage
```bash
python animate.py -l "Chamonix, France" -m snow
```

## Python API
```python
from animate import LandsatAnimator

animator = LandsatAnimator()
animator.generate_animation(
    location="Tokyo",
    mode="rgb",
    cloud_cover=10,
    fps=12
)
```

## Output
Files saved to: `output/landsat_{location}_{mode}_{timestamp}.gif`

## Requirements
- Python 3.7+
- Google Earth Engine account
- Internet connection

## Technical Details
- **Data**: Landsat 8 Collection 2 (2013-present)
- **Resolution**: 30m (15m panchromatic)
- **Scale**: 1:60000
- **Output**: 1024x1024 pixels
- **Selection**: Best monthly image (lowest cloud cover)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Error initializing Earth Engine" | Run `earthengine authenticate` |
| "No images found" | Increase cloud cover threshold |
| "Location not found" | Use coordinates instead of city name |

For detailed documentation, see [USAGE.md](USAGE.md)
