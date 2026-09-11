"""Configuration management for OmniReader."""

import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "engine": "kokoro",  # "kokoro" or "system"
    "kokoro_voice": "af_sky",  # Default high-fidelity Kokoro voice
    "system_voice": "default",
    "speed": 1.4,  # Default 1.4x for efficient, natural listening
    "sentence_pause": 0.20,  # Pause between sentences in seconds
    "hotkey_read": "<ctrl>+<alt>+r",
    "hotkey_stop": "<ctrl>+<alt>+s",
    "models_dir": str(Path.home() / ".local" / "share" / "omni_reader" / "models"),
    "socket_path": "/tmp/omni_reader.sock",
}

CONFIG_DIR = Path.home() / ".config" / "omni_reader"
CONFIG_FILE = CONFIG_DIR / "config.json"


class Config:
    def __init__(self):
        self.data: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as e:
                print(f"[Config] Error loading {CONFIG_FILE}: {e}")
        else:
            self.save()

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving {CONFIG_FILE}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def update(self, **kwargs) -> None:
        self.data.update(kwargs)
        self.save()
