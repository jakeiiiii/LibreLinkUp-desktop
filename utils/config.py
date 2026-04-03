import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# Config lives next to the executable / main.py
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).resolve().parent.parent

CONFIG_FILE = _APP_DIR / "config.json"

DEFAULTS = {
    "region": "Canada",
    "unit": "mmol",              # "mmol" or "mgdl"
    "target_low_mmol": 3.9,
    "target_high_mmol": 10.0,
    "refresh_seconds": 60,       # how often to poll the API (seconds)
    "stale_minutes": 15,         # blink glucose if reading is older than this (minutes)
    "remember_credentials": False,
    "email": "",
    "password": "",
    "low_beep_enabled": True,
    "low_beep_threshold_mmol": 4.0,  # beep when glucose falls below this (0 = disabled)
    "compact_view": False,
}

# Encrypted fields in the config file
_ENCRYPTED_FIELDS = ("email", "password")


def _get_fernet() -> Fernet:
    # Derive a key from the Windows username + machine name.
    # Not unbreakable, but keeps credentials out of plaintext.
    seed = f"LibreLinkUp-{os.getlogin()}-{os.environ.get('COMPUTERNAME', 'desktop')}"
    key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        # If decryption fails (e.g. plaintext from old config), return as-is
        return value


def load_config() -> dict:
    config = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
            config.update(saved)
        except (json.JSONDecodeError, OSError):
            pass

    # Decrypt credential fields for in-memory use
    for field in _ENCRYPTED_FIELDS:
        config[field] = _decrypt(config.get(field, ""))

    return config


def save_config(config: dict) -> None:
    # Copy so we don't mutate the in-memory config
    to_save = dict(config)

    # Encrypt credential fields before writing
    for field in _ENCRYPTED_FIELDS:
        to_save[field] = _encrypt(to_save.get(field, ""))

    with open(CONFIG_FILE, "w") as f:
        json.dump(to_save, f, indent=2)
