# Landanimate

Create an animated Landsat crop or prepare direct USGS M2M scene downloads.

## Installation

```bash
pip install -r requirements.txt
```

## USGS EarthExplorer authentication

Landsat catalog discovery is anonymous, but USGS access-gates full-resolution
Landsat pixels. In the [USGS EROS Registration System](https://ers.cr.usgs.gov/),
create an M2M application token and enter it together with your ERS username in
the private, Git-ignored `landanimate.config.json`. Validate it without printing
or saving the temporary API key:

```bash
python usgs_auth.py
```

USGS now authenticates M2M applications through `login-token`; its legacy
password-based M2M login has been retired. See the official [M2M application
token documentation](https://www.usgs.gov/media/files/m2m-application-token-documentation).

## Morristown test

`test_morristown.py` prepares an authenticated USGS M2M Landsat Collection 2
download plan for Morristown, New Jersey (`40.7968,-74.4815`): a 20-mile square,
the 1972-present Landsat record, maximum 10% cloud, and one scene target per year.

```bash
python test_morristown.py
```

For a no-pixel Landsat discovery pass that writes the selected-date report only:

```bash
python landanimate.py --lat 40.7968 --lon -74.4815 --miles 20 \
  --start 1972-07-23 --source landsat --cloud 10 --per-year 1 --plan-only
```

Landsat searches and downloads go directly through USGS M2M using the
EarthExplorer application token in `landanimate.config.json`; no Google or
third-party cloud catalog is used. `--prepare-downloads` writes temporary USGS
download URLs to `out/downloads.json`. The search combines MSS (1972+), TM
(1982+), ETM+ (1999+), and Landsat 8/9 (2013+) Collection 2 inventories. M2M
products are full archives, so this command deliberately prepares downloads
rather than streaming their bands as remote COGs.

For a rendered Landsat RGB test, `--download-bands` fetches only the three
needed GeoTIFFs per selected scene, crops them locally, and builds a GIF.
It supports the 1972-present MSS, TM, ETM+, and Landsat 8/9 record. MSS has no
blue band, so its frames use a B5/B4/B4 pseudo-RGB composite and a per-scene
stretch. The full Claremont test downloads roughly three bands for each annual
frame and can require several gigabytes of local storage.

All rendered crops use the local UTM grid rather than Web Mercator. Candidates
must fully contain the AOI footprint; Landsat 7 scenes after its 2003 SLC failure
are excluded. Rendered crops with under 90% usable coverage are also rejected.
