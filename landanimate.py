#!/usr/bin/env python3
"""Download low-cloud Landsat/Sentinel crops and animate them without credentials."""
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
SENTINEL_STAC = "https://earth-search.aws.element84.com/v1"
MILES_TO_METERS = 1609.344


@dataclass(frozen=True)
class Scene:
    item_id: str
    source: str
    acquired: str
    cloud_cover: float
    assets: dict[str, str]

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
@click.option("--start", default="1982-08-22", show_default=True)
@click.option("--end", default=lambda: date.today().isoformat(), show_default="today")
@click.option("--source", type=click.Choice(["landsat", "sentinel", "both"]), default="landsat", show_default=True)
@click.option("--cloud", type=click.FloatRange(0, 100), default=10, show_default=True)
@click.option("--per-year", type=click.IntRange(1), default=8, show_default=True)
@click.option("--mode", type=click.Choice(["rgb", "built-up"]), default="rgb", show_default=True)
@click.option("--fps", type=click.IntRange(1), default=16, show_default=True)
@click.option("--vibrance", type=click.FloatRange(0.0), default=1.35, show_default=True)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("out"), show_default=True)
@click.option("--plan-only", is_flag=True, help="Query, select, and report scenes without downloading pixels.")
def main(lat: float, lon: float, miles: float, start: str, end: str, source: str, cloud: float,
         per_year: int, mode: str, fps: int, vibrance: float, out_dir: Path, plan_only: bool) -> None:
    """Create a 30 m animated GIF from public Landsat and/or Sentinel-2 COGs."""
    bbox = bbox_for_square(lat, lon, miles)
    all_scenes: list[Scene] = []
    sources = ["landsat", "sentinel"] if source == "both" else [source]
    configs = {"landsat": (LANDSAT_STAC, "landsat-c2l2-sr"), "sentinel": (SENTINEL_STAC, "sentinel-2-c1-l2a")}
    for name in sources:
        endpoint, collection = configs[name]
        click.echo(f"Searching public {name} catalog…")
        all_scenes.extend(filter(None, (normalize_item(item, name) for item in stac_search(endpoint, collection, bbox, start, end, cloud))))
    scenes = choose_scenes(all_scenes, per_year)
    if not scenes:
        raise click.ClickException("No scenes match the requested location, dates, and cloud limit.")
    scenes_dir = out_dir / "scenes"; scenes_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "report.csv"; write_report(scenes, report, per_year)
    click.echo(f"Selected {len(scenes)} frames; report: {report}")
    short_years = [str(year) for year in range(int(start[:4]), int(end[:4]) + 1) if sum(s.year == year for s in scenes) < per_year]
    if short_years: click.echo("Fewer than target low-cloud scenes: " + ", ".join(short_years), err=True)
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
