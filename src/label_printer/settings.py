"""Per-user settings (the chosen default layout), stored in %APPDATA%."""

import json
import os
from pathlib import Path

from .layouts import DEFAULT_LAYOUT, LAYOUTS

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "LabelPrinter" / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def default_layout() -> str:
    """The user's saved default layout, or the factory default."""
    saved = load_settings().get("default_layout")
    return saved if saved in LAYOUTS else DEFAULT_LAYOUT
