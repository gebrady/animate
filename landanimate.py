#!/usr/bin/env python3
"""Create Landsat crops and prepare authenticated USGS Sentinel-2 downloads."""
from __future__ import annotations

import csv
import json
import math
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import click
import imageio.v2 as imageio
import numpy as np
import requests
from PIL import Image, ImageEnhance
from pyproj import Transformer
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

LANDSAT_STAC = "https://landsatlook.usgs.gov/stac-server"
# USGS's current test interface uses experimental; it accepts application-token login.
M2M_API = "https://m2m.cr.usgs.gov/api/api/json/experimental"
# These catalogs cover the usable Collection 2 record from the first MSS scenes
# through Landsat 8/9.  Level-2 is preferred wherever USGS provides it.
LANDSAT_DATASETS = (
    "landsat_mss_c2_l1",  # Landsat 1-5 MSS, 1972 onward
    "landsat_tm_c2_l2",   # Landsat 4-5 TM, 1982 onward
    "landsat_etm_c2_l2",  # Landsat 7 ETM+, 1999 onward
    "landsat_ot_c2_l2",   # Landsat 8-9 OLI/TIRS, 2013 onward
)
MILES_TO_METERS = 1609.344


@dataclass(frozen=True)
class Scene:
    item_id: str
    source: str
    acquired: str
    cloud_cover: float
    assets: dict[str, str]
    dataset: str | None = None
    entity_id: str | None = None
    spatial_coverage: dict[str, Any] | None = None

    @property
    def year(self) -> int:
        return int(self.acquired[:4])


def bbox_for_square(lat: float, lon: float, miles: float) -> tuple[float, float, float, float]:
    """Return a WGS84 bbox for a square whose side is ``miles``."""
    half = miles * MILES_TO_METERS / 2
    to_3857 = Transformer.from_crs(4326, 3857, always_xy=True)
    to_4326 = Transformer.from_crs(3857, 4326, always_xy=True)
    x, y = to_3857.transform(lon, lat)
    west, south = to_4326.transform(x - half, y - half)
    east, north = to_4326.transform(x + half, y + half)
    return west, south, east, north


def local_utm_crs(lat: float, lon: float) -> str:
    """Return the local UTM CRS, avoiding Web Mercator's variable scale."""
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def local_square(lat: float, lon: float, miles: float) -> tuple[str, tuple[float, float, float, float]]:
    """Return an exact square in the local UTM grid for stable cross-year crops."""
    crs = local_utm_crs(lat, lon)
    x, y = Transformer.from_crs(4326, crs, always_xy=True).transform(lon, lat)
    half = miles * MILES_TO_METERS / 2
    return crs, (x - half, y - half, x + half, y + half)


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Return whether a WGS84 point lies within a GeoJSON polygon ring."""
    inside = False
    for index, (x1, y1) in enumerate(ring):
        x2, y2 = ring[index - 1]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def coverage_contains_bbox(coverage: dict[str, Any] | None,
                           bbox: tuple[float, float, float, float]) -> bool:
    """Require every AOI corner to fall within the scene footprint, not just intersect it."""
    if not coverage or coverage.get("type") != "Polygon":
        return True  # Rendering's no-data check remains the fallback for incomplete metadata.
    rings = coverage.get("coordinates") or []
    if not rings:
        return True
    west, south, east, north = bbox
    return all(point_in_ring(lon, lat, rings[0]) for lon, lat in (
        (west, south), (west, north), (east, south), (east, north),
    ))


def stac_search(endpoint: str, collection: str, bbox: tuple[float, float, float, float],
                start: str, end: str, cloud: float) -> list[dict[str, Any]]:
    """Fetch every matching STAC item. Both catalogs are public and need no login."""
    payload = {
        "collections": [collection], "bbox": list(bbox),
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 500,
        "query": {"eo:cloud_cover": {"lte": cloud}},
    }
    session = requests.Session()
    response = session.post(f"{endpoint}/search", json=payload, timeout=90)
    response.raise_for_status()
    found: list[dict[str, Any]] = []
    while True:
        body = response.json()
        found.extend(body.get("features", []))
        next_link = next((link for link in body.get("links", []) if link.get("rel") == "next"), None)
        if not next_link:
            return found
        # STAC pagination links may be either GET URLs or a POST body.
        method = next_link.get("method", "GET").upper()
        if method == "POST":
            response = session.post(next_link["href"], json=next_link.get("body", payload), timeout=90)
        else:
            response = session.get(next_link["href"], timeout=90)
        response.raise_for_status()


def load_m2m_credentials(config: Path) -> tuple[str, str]:
    """Read, but never print, the long-lived M2M application credentials."""
    try:
        settings = json.loads(config.read_text())
    except FileNotFoundError as error:
        raise click.ClickException(
            f"USGS Sentinel access needs {config}. Copy landanimate.config.json.example and add your M2M token."
        ) from error
    except json.JSONDecodeError as error:
        raise click.ClickException(f"Invalid JSON in {config}: {error}") from error
    usgs = settings.get("usgs_eros", {})
    username = usgs.get("username")
    token = usgs.get("m2m_application_token")
    if not username or username == "your-earth-explorer-username":
        raise click.ClickException("Set usgs_eros.username in the private config.")
    if not token or token == "paste-your-64-character-m2m-application-token-here":
        raise click.ClickException("Set usgs_eros.m2m_application_token in the private config.")
    return username, token


def m2m_call(session: requests.Session, endpoint: str, payload: dict[str, Any]) -> Any:
    """Call M2M and turn its JSON error envelope into a useful CLI error."""
    try:
        response = session.post(f"{M2M_API}/{endpoint}", json=payload, timeout=90)
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as error:
        raise click.ClickException(f"USGS M2M {endpoint} request failed: {error}") from error
    if body.get("errorCode"):
        raise click.ClickException(f"USGS M2M {endpoint} failed: {body.get('errorMessage', body['errorCode'])}")
    return body.get("data")


def m2m_session(config: Path) -> requests.Session:
    session = requests.Session()
    username, token = load_m2m_credentials(config)
    api_key = m2m_call(session, "login-token", {"username": username, "token": token})
    if not api_key:
        raise click.ClickException("USGS M2M did not return an API key.")
    session.headers["X-Auth-Token"] = api_key
    return session


def m2m_acquired(result: dict[str, Any]) -> str | None:
    """Return the acquisition date from either M2M response shape."""
    return result.get("acquisitionDate") or result.get("temporalCoverage", {}).get("startDate")


def is_landsat_7_slc_off(item_id: str, acquired: str) -> bool:
    """Landsat 7 imagery acquired after the SLC failure has systematic data gaps."""
    return item_id.startswith("LE07") and acquired >= "2003-05-31"


def m2m_sentinel_search(session: requests.Session, bbox: tuple[float, float, float, float],
                        start: str, end: str, cloud: float) -> list[Scene]:
    """Search the USGS EarthExplorer Sentinel-2 inventories, not a third party STAC."""
    west, south, east, north = bbox
    scene_filter = {
        "spatialFilter": {
            "filterType": "mbr",
            "lowerLeft": {"latitude": south, "longitude": west},
            "upperRight": {"latitude": north, "longitude": east},
        },
        "acquisitionFilter": {"start": start, "end": end},
        "cloudCoverFilter": {"min": 0, "max": cloud},
    }
    catalog = m2m_call(session, "dataset-search", {}) or []
    datasets = []
    for item in catalog:
        alias = item.get("datasetAlias")
        description = " ".join(str(item.get(field, "")) for field in (
            "datasetName", "collectionName", "collectionLongName", "shortName", "keywords",
        )).lower()
        if alias and "sentinel" in description and ("2" in description or "s2" in description):
            datasets.append(alias)
    if not datasets:
        raise click.ClickException(
            "Your authenticated USGS M2M catalog has no Sentinel-2 dataset. "
            "USGS cannot prepare a direct M2M Sentinel download for this account at present."
        )
    scenes: list[Scene] = []
    for dataset in sorted(set(datasets)):
        data = m2m_call(session, "scene-search", {
            "datasetName": dataset, "sceneFilter": scene_filter,
            "maxResults": 500, "startingNumber": 1,
        }) or {}
        for result in data.get("results", []):
            acquired = m2m_acquired(result)
            entity_id = result.get("entityId")
            if not acquired or not entity_id:
                continue
            scenes.append(Scene(
                item_id=result.get("displayId") or entity_id, source="sentinel",
                acquired=acquired[:10], cloud_cover=float(result.get("cloudCover") or 0),
                assets={}, dataset=dataset, entity_id=entity_id, spatial_coverage=result.get("spatialCoverage"),
            ))
    return scenes


def m2m_landsat_search(session: requests.Session, bbox: tuple[float, float, float, float],
                       start: str, end: str, cloud: float) -> list[Scene]:
    """Search the full available USGS Landsat Collection 2 record through M2M."""
    west, south, east, north = bbox
    scenes: list[Scene] = []
    scene_filter = {
        "spatialFilter": {
            "filterType": "mbr",
            "lowerLeft": {"latitude": south, "longitude": west},
            "upperRight": {"latitude": north, "longitude": east},
        },
        "acquisitionFilter": {"start": start, "end": end},
        "cloudCoverFilter": {"min": 0, "max": cloud},
    }
    for dataset in LANDSAT_DATASETS:
        data = m2m_call(session, "scene-search", {
            "datasetName": dataset, "sceneFilter": scene_filter,
            "maxResults": 500, "startingNumber": 1,
        }) or {}
        for result in data.get("results", []):
            acquired = m2m_acquired(result)
            entity_id = result.get("entityId")
            if acquired and entity_id:
                item_id = result.get("displayId") or entity_id
                if is_landsat_7_slc_off(item_id, acquired[:10]):
                    continue
                if not coverage_contains_bbox(result.get("spatialCoverage"), bbox):
                    continue
                scenes.append(Scene(
                    item_id=item_id, source="landsat",
                    acquired=acquired[:10], cloud_cover=float(result.get("cloudCover") or 0),
                    assets={}, dataset=dataset, entity_id=entity_id, spatial_coverage=result.get("spatialCoverage"),
                ))
    return scenes


def m2m_download_plan(session: requests.Session, scenes: list[Scene]) -> list[dict[str, str]]:
    """Request USGS download URLs for selected full satellite products."""
    requested: list[dict[str, str]] = []
    by_dataset: dict[str, list[Scene]] = defaultdict(list)
    for scene in scenes:
        if scene.dataset and scene.entity_id:
            by_dataset[scene.dataset].append(scene)
    for dataset, dataset_scenes in by_dataset.items():
        options = m2m_call(session, "download-options", {
            "datasetName": dataset, "entityIds": [scene.entity_id for scene in dataset_scenes],
        }) or []
        options_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for option in options:
            if option.get("entityId"):
                options_by_entity[option["entityId"]].append(option)
        for scene in dataset_scenes:
            option = next((item for item in options_by_entity[scene.entity_id] if item.get("available") and item.get("id")), None)
            if option:
                requested.append({"entityId": scene.entity_id, "productId": option["id"]})
    if not requested:
        raise click.ClickException("USGS reported no downloadable product for the selected scenes.")
    data = m2m_call(session, "download-request", {
        "downloads": requested, "label": "landanimate-scenes",
    }) or {}
    downloads = data.get("availableDownloads", [])
    if not downloads:
        raise click.ClickException("USGS accepted no immediate downloads; try again later.")
    return [
        {"entity_id": item.get("entityId", ""), "product_id": item.get("productId", ""), "url": item["url"]}
        for item in downloads if item.get("url")
    ]


def download_file(url: str, destination: Path) -> None:
    """Stream one signed USGS URL to disk without buffering its full image."""
    try:
        with requests.get(url, stream=True, timeout=(30, 300)) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as error:
        raise click.ClickException(f"USGS band download failed for {destination.name}: {error}") from error


def m2m_download_rgb_bands(session: requests.Session, scenes: list[Scene], destination: Path) -> list[Scene]:
    """Download only the red, green, and blue Level-2 files for Landsat scenes."""
    destination.mkdir(parents=True, exist_ok=True)
    rendered: list[Scene] = []
    rgb_bands = {
        # MSS has no blue channel.  B4 is repeated as blue for a pseudo-RGB frame.
        "landsat_mss_c2_l1": {"red": "_B5.TIF", "green": "_B4.TIF", "blue": "_B4.TIF"},
        "landsat_ot_c2_l2": {"red": "_SR_B4.TIF", "green": "_SR_B3.TIF", "blue": "_SR_B2.TIF"},
        "landsat_etm_c2_l2": {"red": "_SR_B3.TIF", "green": "_SR_B2.TIF", "blue": "_SR_B1.TIF"},
        "landsat_tm_c2_l2": {"red": "_SR_B3.TIF", "green": "_SR_B2.TIF", "blue": "_SR_B1.TIF"},
    }
    for number, scene in enumerate(scenes, 1):
        required = rgb_bands.get(scene.dataset or "")
        if not required or not scene.entity_id:
            raise click.ClickException(
                "--download-bands supports the USGS Collection 2 MSS, TM, ETM+, and Landsat 8/9 inventories."
            )
        options = m2m_call(session, "download-options", {
            "datasetName": scene.dataset, "entityIds": [scene.entity_id],
        }) or []
        available = {
            name: secondary for option in options for secondary in option.get("secondaryDownloads", [])
            for name, suffix in required.items()
            if secondary.get("available") and secondary.get("displayId", "").upper().endswith(suffix)
        }
        if not available:
            click.echo(f"Skipping {scene.item_id}: USGS offered no visible image bands.", err=True)
            continue
        fallback = next(iter(available.values()))
        available = {name: available.get(name, fallback) for name in required}
        request = list({item["entityId"]: {"entityId": item["entityId"], "productId": item["id"]}
                        for item in available.values()}.values())
        data = m2m_call(session, "download-request", {
            "downloads": request, "label": f"landanimate-rgb-{number:04d}",
        }) or {}
        urls = {item.get("entityId"): item.get("url") for item in data.get("availableDownloads", [])}
        assets: dict[str, str] = {}
        downloaded_paths: dict[str, str] = {}
        for name, item in available.items():
            if item["entityId"] in downloaded_paths:
                assets[name] = downloaded_paths[item["entityId"]]
                continue
            url = urls.get(item["entityId"])
            if not url:
                raise click.ClickException(f"USGS is still preparing {name} for {scene.item_id}; retry shortly.")
            path = destination / f"{number:04d}_{scene.item_id}_{name}.tif"
            if path.exists() and path.stat().st_size > 0:
                click.echo(f"Reusing {number}/{len(scenes)} {scene.item_id} {name}…")
                assets[name] = str(path)
                continue
            click.echo(f"Downloading {number}/{len(scenes)} {scene.item_id} {name}…")
            download_file(url, path)
            assets[name] = str(path)
            downloaded_paths[item["entityId"]] = str(path)
        rendered.append(Scene(scene.item_id, scene.source, scene.acquired, scene.cloud_cover,
                              assets, scene.dataset, scene.entity_id, scene.spatial_coverage))
    return rendered


def normalize_item(item: dict[str, Any], source: str) -> Scene | None:
    props = item["properties"]
    acquired = props.get("datetime") or props.get("start_datetime")
    if not acquired:
        return None
    cloud = props.get("eo:cloud_cover")
    if cloud is None:
        return None
    assets = {name: value["href"] for name, value in item.get("assets", {}).items() if "href" in value}
    # Common STAC asset names differ by catalogue/product generation.
    if source == "landsat":
        needed = {"red": assets.get("red"), "green": assets.get("green"), "blue": assets.get("blue"),
                  "nir08": assets.get("nir08") or assets.get("nir"), "swir16": assets.get("swir16")}
    else:
        needed = {"red": assets.get("red"), "green": assets.get("green"), "blue": assets.get("blue"),
                  "nir08": assets.get("nir") or assets.get("nir08"), "swir16": assets.get("swir16")}
    if not all(needed.values()):
        return None
    return Scene(item["id"], source, acquired[:10], float(cloud), needed)  # type: ignore[arg-type]


def choose_scenes(scenes: Iterable[Scene], per_year: int) -> list[Scene]:
    """Choose low-cloud scenes, preferring different months for a useful animation."""
    groups: dict[int, list[Scene]] = defaultdict(list)
    for scene in scenes:
        groups[scene.year].append(scene)
    chosen: list[Scene] = []
    for year in sorted(groups):
        ranked = sorted(groups[year], key=lambda s: (s.cloud_cover, s.acquired, s.source))
        months: set[str] = set()
        selected: list[Scene] = []
        for scene in ranked:
            month = scene.acquired[:7]
            if month not in months:
                selected.append(scene); months.add(month)
            if len(selected) == per_year:
                break
        if len(selected) < per_year:
            for scene in ranked:
                if scene not in selected:
                    selected.append(scene)
                if len(selected) == per_year:
                    break
        chosen.extend(sorted(selected, key=lambda s: s.acquired))
    return sorted(chosen, key=lambda s: s.acquired)


def read_band(href: str, bounds: tuple[float, float, float, float], target_crs: str, pixels: int) -> np.ndarray:
    """Read one remote COG directly into its final crop; never download whole scenes."""
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF,.tif"):
        try:
            with rasterio.open(href) as src:
                with WarpedVRT(src, crs=target_crs, resampling=Resampling.bilinear) as vrt:
                    window = from_bounds(*bounds, transform=vrt.transform)
                    data = vrt.read(1, window=window, out_shape=(pixels, pixels), masked=True,
                                    resampling=Resampling.bilinear)
                    # Cast before filling: integer source bands cannot represent NaN directly.
                    return data.astype("float32").filled(np.nan)
        except rasterio.errors.RasterioIOError as error:
            if "landsatlook.usgs.gov" in href:
                raise click.ClickException(
                    "USGS STAC search is public, but Landsat pixel downloads are access-gated. "
                    "Provide a USGS/EROS bulk-download credential so an authenticated Landsat "
                    "backend can be configured, or use --source sentinel for credential-free 2015+ imagery."
                ) from error
            raise


def render(scene: Scene, bounds: tuple[float, float, float, float], target_crs: str, pixels: int,
           mode: str, vibrance: float) -> np.ndarray:
    bands = {name: read_band(url, bounds, target_crs, pixels) for name, url in scene.assets.items()}
    # Collection 2 Landsat SR is scaled/offset. MSS Level-1 frames are raw DNs.
    if scene.source == "landsat":
        if scene.dataset != "landsat_mss_c2_l1":
            bands = {name: value * 0.0000275 - 0.2 for name, value in bands.items()}
    else:
        bands = {name: value / 10000.0 for name, value in bands.items()}
    channels = (bands["red"], bands["green"], bands["blue"]) if mode == "rgb" else (bands["swir16"], bands["nir08"], bands["red"])
    image = np.stack(channels, axis=-1)
    # A fixed reflectance stretch avoids inter-frame brightness flicker. MSS raw
    # digital numbers use a robust scene-local stretch instead.
    if scene.dataset == "landsat_mss_c2_l1":
        low, high = np.nanpercentile(image, (2, 98))
        image = (image - low) / max(high - low, 1e-6)
    else:
        image = (image - 0.015) / 0.32
    image = np.nan_to_num(image, nan=0.0, posinf=1.0, neginf=0.0)
    image = np.clip(image, 0, 1) ** 0.82
    frame = Image.fromarray((image * 255).astype("uint8"), "RGB")
    return np.asarray(ImageEnhance.Color(frame).enhance(vibrance))


def usable_frame_fraction(frame: np.ndarray) -> float:
    """Estimate crop coverage, treating only near-black no-data pixels as missing."""
    return float(np.mean(np.max(frame, axis=2) > 4))


def write_report(scenes: list[Scene], path: Path, requested_per_year: int) -> None:
    counts: dict[int, int] = defaultdict(int)
    for scene in scenes: counts[scene.year] += 1
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "source", "cloud_cover_percent", "scene_id", "frame"])
        for i, scene in enumerate(scenes, 1):
            writer.writerow([scene.acquired, scene.source, f"{scene.cloud_cover:.2f}", scene.item_id, f"{i:04d}"])
    summary = {str(year): {"selected": count, "target": requested_per_year} for year, count in sorted(counts.items())}
    path.with_suffix(".json").write_text(json.dumps({"frames": len(scenes), "years": summary}, indent=2) + "\n")


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--lat", type=float, required=True)
@click.option("--lon", type=float, required=True)
@click.option("--miles", type=click.FloatRange(min=0.1), default=20, show_default=True)
@click.option("--start", default="1972-07-23", show_default=True)
@click.option("--end", default=lambda: date.today().isoformat(), show_default="today")
@click.option("--source", type=click.Choice(["landsat", "sentinel", "both"]), default="landsat", show_default=True)
@click.option("--cloud", type=click.FloatRange(0, 100), default=10, show_default=True)
@click.option("--per-year", type=click.IntRange(1), default=8, show_default=True)
@click.option("--mode", type=click.Choice(["rgb", "built-up"]), default="rgb", show_default=True)
@click.option("--fps", type=click.IntRange(1), default=16, show_default=True)
@click.option("--vibrance", type=click.FloatRange(0.0), default=1.35, show_default=True)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("out"), show_default=True)
@click.option("--plan-only", is_flag=True, help="Query, select, and report scenes without downloading pixels.")
@click.option("--prepare-downloads", is_flag=True, help="Request USGS M2M URLs for selected Sentinel products and write downloads.json.")
@click.option("--download-bands", is_flag=True, help="Download Landsat Collection 2 RGB bands from USGS M2M and render a GIF.")
@click.option("--clean-out", is_flag=True, help="Delete the selected output directory before writing new files.")
@click.option("--min-coverage", type=click.FloatRange(0.0, 1.0), default=0.90, show_default=True,
              help="Reject rendered crops with less usable, non-black coverage.")
@click.option("--config", type=click.Path(path_type=Path), default=Path("landanimate.config.json"), show_default=True)
def main(lat: float, lon: float, miles: float, start: str, end: str, source: str, cloud: float,
         per_year: int, mode: str, fps: int, vibrance: float, out_dir: Path, plan_only: bool,
         prepare_downloads: bool, download_bands: bool, clean_out: bool, min_coverage: float,
         config: Path) -> None:
    """Create Landsat crops or prepare direct USGS Sentinel-2 downloads."""
    if clean_out and out_dir.exists():
        shutil.rmtree(out_dir)
    bbox = bbox_for_square(lat, lon, miles)
    all_scenes: list[Scene] = []
    sources = ["landsat", "sentinel"] if source == "both" else [source]
    usgs_session: requests.Session | None = None
    for name in sources:
        if name == "sentinel":
            click.echo("Searching USGS EarthExplorer Sentinel-2 catalog…")
            usgs_session = m2m_session(config)
            all_scenes.extend(m2m_sentinel_search(usgs_session, bbox, start, end, cloud))
        else:
            click.echo("Searching USGS Landsat Collection 2 catalogs…")
            usgs_session = m2m_session(config)
            all_scenes.extend(m2m_landsat_search(usgs_session, bbox, start, end, cloud))
    scenes = choose_scenes(all_scenes, per_year)
    if not scenes:
        raise click.ClickException("No scenes match the requested location, dates, and cloud limit.")
    scenes_dir = out_dir / "scenes"; scenes_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "report.csv"; write_report(scenes, report, per_year)
    click.echo(f"Selected {len(scenes)} frames; report: {report}")
    short_years = [str(year) for year in range(int(start[:4]), int(end[:4]) + 1) if sum(s.year == year for s in scenes) < per_year]
    if short_years: click.echo("Fewer than target low-cloud scenes: " + ", ".join(short_years), err=True)
    if prepare_downloads and download_bands:
        raise click.ClickException("Use either --prepare-downloads or --download-bands, not both.")
    if prepare_downloads:
        downloads = m2m_download_plan(usgs_session or m2m_session(config), scenes)
        plan = out_dir / "downloads.json"
        plan.write_text(json.dumps(downloads, indent=2) + "\n")
        click.echo(f"USGS download URLs: {plan}")
        return
    if download_bands:
        if source != "landsat" or mode != "rgb":
            raise click.ClickException("--download-bands requires --source landsat and --mode rgb.")
        scenes = m2m_download_rgb_bands(usgs_session or m2m_session(config), scenes, out_dir / "downloads")
        if not scenes:
            raise click.ClickException("USGS did not provide any downloadable visible-band scenes.")
    if any(not scene.assets for scene in scenes) and not plan_only and not prepare_downloads:
        raise click.ClickException(
            "Direct USGS M2M products are full downloads, not remote COGs. "
            "Use --plan-only for discovery, or --prepare-downloads to write direct USGS download URLs."
        )
    if plan_only: return
    target_crs, bounds = local_square(lat, lon, miles)
    pixels = math.ceil((miles * MILES_TO_METERS) / 30)
    gif = out_dir / f"animation_{mode}_{start[:4]}_{end[:4]}.gif"
    accepted: list[Scene] = []
    with imageio.get_writer(gif, mode="I", duration=1 / fps, loop=0) as writer:
        for number, scene in enumerate(scenes, 1):
            click.echo(f"[{number}/{len(scenes)}] {scene.acquired} {scene.source} {scene.cloud_cover:.1f}%")
            frame = render(scene, bounds, target_crs, pixels, mode, vibrance)
            coverage = usable_frame_fraction(frame)
            if coverage < min_coverage:
                click.echo(f"Skipping {scene.item_id}: only {coverage:.0%} usable coverage.", err=True)
                continue
            frame_path = scenes_dir / f"{len(accepted) + 1:04d}_{scene.acquired}_{scene.source}.png"
            imageio.imwrite(frame_path, frame)
            writer.append_data(frame)
            accepted.append(scene)
    if not accepted:
        gif.unlink(missing_ok=True)
        raise click.ClickException("All downloaded scenes were rejected for insufficient usable coverage.")
    write_report(accepted, report, per_year)
    click.echo(f"GIF: {gif}\nFrames: {scenes_dir}\nReport: {report}")


if __name__ == "__main__":
    main()
