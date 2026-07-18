"""Prepare a direct USGS Landsat Collection 2 download plan for Morristown."""
from click.testing import CliRunner
from landanimate import main

if __name__ == "__main__":
    result = CliRunner().invoke(main, [
        "--lat", "40.7968", "--lon", "-74.4815", "--miles", "20",
        "--start", "1972-07-23", "--end", "2024-12-31", "--source", "landsat", "--cloud", "10", "--per-year", "1",
        "--mode", "rgb", "--fps", "16", "--prepare-downloads", "--out", "out",
    ])
    print(result.output, end="")
    raise SystemExit(result.exit_code)
