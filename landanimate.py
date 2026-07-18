#!/usr/bin/env python3
"""Create Landsat crops and prepare authenticated USGS Sentinel-2 downloads."""
from __future__ import annotations

import csv
import json
import math
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
                assets={}, dataset=dataset, entity_id=entity_id,
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
                scenes.append(Scene(
                    item_id=result.get("displayId") or entity_id, source="landsat",
                    acquired=acquired[:10], cloud_cover=float(result.get("cloudCover") or 0),
                    assets={}, dataset=dataset, entity_id=entity_id,
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


def read_band(href: str, bbox_3857: tuple[float, float, float, float], pixels: int) -> np.ndarray:
    """Read one remote COG directly into its final crop; never download whole scenes."""
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF,.tif"):
        try:
            with rasterio.open(href) as src:
                with WarpedVRT(src, crs="EPSG:3857", resampling=Resampling.bilinear) as vrt:
                    window = from_bounds(*bbox_3857, transform=vrt.transform)
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


def render(scene: Scene, bbox_3857: tuple[float, float, float, float], pixels: int,
           mode: str, vibrance: float) -> np.ndarray:
    bands = {name: read_band(url, bbox_3857, pixels) for name, url in scene.assets.items()}
    # Collection 2 Landsat SR is scaled/offset; Sentinel L2A is scaled by 10,000.
    if scene.source == "landsat":
        bands = {name: value * 0.0000275 - 0.2 for name, value in bands.items()}
    else:
        bands = {name: value / 10000.0 for name, value in bands.items()}
    channels = (bands["red"], bands["green"], bands["blue"]) if mode == "rgb" else (bands["swir16"], bands["nir08"], bands["red"])
    image = np.stack(channels, axis=-1)
    # A fixed reflectance stretch avoids inter-frame brightness flicker while adding punch.
    image = np.nan_to_num((image - 0.015) / 0.32, nan=0.0, posinf=1.0, neginf=0.0)
    image = np.clip(image, 0, 1) ** 0.82
    frame = Image.fromarray((image * 255).astype("uint8"), "RGB")
    return np.asarray(ImageEnhance.Color(frame).enhance(vibrance))


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
@click.option("--config", type=click.Path(path_type=Path), default=Path("landanimate.config.json"), show_default=True)
def main(lat: float, lon: float, miles: float, start: str, end: str, source: str, cloud: float,
         per_year: int, mode: str, fps: int, vibrance: float, out_dir: Path, plan_only: bool,
         prepare_downloads: bool, config: Path) -> None:
    """Create Landsat crops or prepare direct USGS Sentinel-2 downloads."""
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
    if prepare_downloads:
        downloads = m2m_download_plan(usgs_session or m2m_session(config), scenes)
        plan = out_dir / "downloads.json"
        plan.write_text(json.dumps(downloads, indent=2) + "\n")
        click.echo(f"USGS download URLs: {plan}")
        return
    if any(not scene.assets for scene in scenes) and not plan_only and not prepare_downloads:
        raise click.ClickException(
            "Direct USGS M2M products are full downloads, not remote COGs. "
            "Use --plan-only for discovery, or --prepare-downloads to write direct USGS download URLs."
        )
    if plan_only: return
    half = miles * MILES_TO_METERS / 2
    x, y = Transformer.from_crs(4326, 3857, always_xy=True).transform(lon, lat)
    pixels = math.ceil((miles * MILES_TO_METERS) / 30)
    gif = out_dir / f"animation_{mode}_{start[:4]}_{end[:4]}.gif"
    with imageio.get_writer(gif, mode="I", duration=1 / fps, loop=0) as writer:
        for number, scene in enumerate(scenes, 1):
            click.echo(f"[{number}/{len(scenes)}] {scene.acquired} {scene.source} {scene.cloud_cover:.1f}%")
            frame = render(scene, (x-half, y-half, x+half, y+half), pixels, mode, vibrance)
            frame_path = scenes_dir / f"{number:04d}_{scene.acquired}_{scene.source}.png"
            imageio.imwrite(frame_path, frame)
            writer.append_data(frame)
    click.echo(f"GIF: {gif}\nFrames: {scenes_dir}\nReport: {report}")


if __name__ == "__main__":
    main()
