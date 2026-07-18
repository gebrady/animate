# Landanimate

Create animated 30 m crops from low-cloud Landsat and Sentinel-2 scenes.
The tool streams only the selected crop from each remote COG, writes each
rendered PNG under `out/scenes`, then builds a GIF and date/scene report.

## Installation

```bash
pip install -r requirements.txt
```

## USGS EarthExplorer authentication

Landsat catalog discovery is anonymous, but USGS access-gates full-resolution
Landsat pixels. In the [USGS EROS Registration System](https://ers.cr.usgs.gov/),
create an M2M application token and paste it into the private, Git-ignored
`landanimate.config.json`. Validate it without printing or saving the temporary
API key:

```bash
python usgs_auth.py
```

USGS now authenticates M2M applications through `login-token`; its legacy
password-based M2M login has been retired. See the official [M2M application
token documentation](https://www.usgs.gov/media/files/m2m-application-token-documentation).

## Morristown test

`test_morristown.py` is prepared for Morristown, New Jersey (`40.7968,-74.4815`):
a 20-mile square, Landsat archive beginning `1982-08-22`, maximum 10% cloud,
eight scenes/year target, RGB, and 16 FPS.

```bash
python test_morristown.py
```

For a no-pixel discovery pass that writes the selected-date report only:

```bash
python landanimate.py --lat 40.7968 --lon -74.4815 --miles 20 \
  --start 1982-08-22 --cloud 10 --per-year 8 --mode rgb --fps 16 --plan-only
```

Use `--source sentinel` for anonymous Sentinel-2 imagery (2015 onward) or
`--source both` to combine sources. `--mode built-up` renders SWIR, NIR, and
red to emphasize impervious and built surfaces.
