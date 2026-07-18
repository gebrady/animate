"""Download and render an annual 10-mile Landsat record centered on Claremont, CA."""
from click.testing import CliRunner
from landanimate import main


if __name__ == "__main__":
    result = CliRunner().invoke(main, [
        "--lat", "34.0967", "--lon", "-117.7198", "--miles", "10",
        "--start", "1972-07-23", "--end", "2024-12-31", "--source", "landsat",
        "--cloud", "20", "--per-year", "1", "--mode", "rgb", "--fps", "2",
        "--download-bands", "--clean-out", "--out", "out/claremont",
    ])
    print(result.output, end="")
    raise SystemExit(result.exit_code)
