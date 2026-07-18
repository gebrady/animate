"""Reproducible no-credentials test configuration for Morristown, New Jersey."""
from click.testing import CliRunner
from landanimate import main

if __name__ == "__main__":
    result = CliRunner().invoke(main, [
        "--lat", "40.7968", "--lon", "-74.4815", "--miles", "20",
        "--start", "1982-08-22", "--cloud", "10", "--per-year", "8",
        "--mode", "rgb", "--fps", "16", "--out", "out",
    ])
    print(result.output, end="")
    raise SystemExit(result.exit_code)
