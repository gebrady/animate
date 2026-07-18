#!/usr/bin/env python3
"""Validate a USGS EROS M2M application token kept in local configuration."""
from __future__ import annotations

import json
from pathlib import Path

import click
import requests

# Match the currently supported USGS M2M test endpoint for application tokens.
M2M_LOGIN_TOKEN = "https://m2m.cr.usgs.gov/api/api/json/experimental/login-token"


def load_config(path: Path) -> dict:
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise click.ClickException(f"Configuration not found: {path}.") from error
    except json.JSONDecodeError as error:
        raise click.ClickException(f"Invalid JSON in {path}: {error}") from error
    return config.get("usgs_eros", {})


@click.command()
@click.option("--config", type=click.Path(path_type=Path), default=Path("landanimate.config.json"), show_default=True)
def main(config: Path) -> None:
    """Exchange a USGS EROS M2M application token for a temporary API key."""
    settings = load_config(config)
    username = settings.get("username")
    token = settings.get("m2m_application_token")
    if not username or username == "your-earth-explorer-username":
        raise click.ClickException("Set usgs_eros.username in the private config.")
    if not token or token == "paste-your-64-character-m2m-application-token-here":
        raise click.ClickException("Set usgs_eros.m2m_application_token in the private config.")
    try:
        response = requests.post(M2M_LOGIN_TOKEN, json={"username": username, "token": token}, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise click.ClickException(f"USGS M2M authentication request failed: {error}") from error
    if payload.get("errorCode") or not payload.get("data"):
        raise click.ClickException(f"USGS M2M authentication failed: {payload.get('errorMessage', payload)}")
    # Deliberately do not print or persist the short-lived API key.
    click.echo("USGS EROS M2M token validated successfully.")


if __name__ == "__main__":
    main()
