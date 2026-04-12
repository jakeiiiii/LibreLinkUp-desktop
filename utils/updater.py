"""Auto-updater: check GitHub Releases for a newer version, download, and apply."""

import logging
import os
import sys
import tempfile
from pathlib import Path
from packaging.version import Version

import requests

from utils.version import __version__

logger = logging.getLogger(__name__)

GITHUB_REPO = "jakeiiiii/LibreLinkUp-desktop"
ASSET_NAME = "LibreLinkUp.zip"


def _get_app_dir() -> Path:
    """Return the directory containing the running exe (frozen) or project root (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def check_for_update() -> tuple[str, str] | None:
    """Check GitHub for a newer release.

    Returns (new_version, download_url) if an update is available, else None.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Update check failed: {e}")
        return None

    data = resp.json()
    tag = data.get("tag_name", "")
    remote_version = tag.lstrip("v")

    try:
        if Version(remote_version) <= Version(__version__):
            return None
    except Exception:
        return None

    # Find the zip asset
    for asset in data.get("assets", []):
        if asset["name"] == ASSET_NAME:
            return (remote_version, asset["browser_download_url"])

    logger.warning("Update found but no %s asset in release", ASSET_NAME)
    return None


def download_and_apply(download_url: str) -> None:
    """Download the update zip and spawn a batch script to apply it, then exit."""
    app_dir = _get_app_dir()
    zip_path = Path(tempfile.gettempdir()) / ASSET_NAME

    # Download
    logger.info("Downloading update from %s", download_url)
    resp = requests.get(download_url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(zip_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info("Downloaded update to %s", zip_path)

    # Write a batch script that waits for us to exit, extracts, and relaunches
    bat_path = Path(tempfile.gettempdir()) / "librelinkup_update.bat"
    exe_name = Path(sys.executable).name if getattr(sys, "frozen", False) else "LibreLinkUp.exe"

    bat_contents = f"""@echo off
echo Updating LibreLinkUp...
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "Expand-Archive -Path '{zip_path}' -DestinationPath '{app_dir}' -Force"
del /f /q "{zip_path}"
start "" "{app_dir / exe_name}"
del /f /q "%~f0"
"""
    with open(bat_path, "w") as f:
        f.write(bat_contents)

    # Launch the updater script and exit
    logger.info("Launching updater script and exiting")
    os.startfile(str(bat_path))
    sys.exit(0)
