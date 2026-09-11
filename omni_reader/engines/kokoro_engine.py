"""Kokoro ONNX Neural Text-to-Speech Engine."""

import os
import urllib.request
from pathlib import Path
from typing import Any, List, Optional, Tuple
import numpy as np

from .base import BaseTTSEngine

DEFAULT_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
DEFAULT_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

# Curated priority voices
FEATURED_VOICES = [
    "af_sky",       # US Female - Natural & balanced (Default)
    "af_sarah",     # US Female - Warm & articulate
    "af_bella",     # US Female - Expressive
    "af_nicole",    # US Female - Clear narrator
    "am_adam",      # US Male - Rich & crisp
    "am_michael",   # US Male - Deep & authoritative
    "bf_emma",      # UK Female - Articulate & refined
    "bf_isabella",  # UK Female - Sophisticated
    "bm_george",    # UK Male - Warm narrator
    "bm_lewis",     # UK Male - Natural
]


class KokoroEngine(BaseTTSEngine):
    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = Path(models_dir) if models_dir else Path.home() / ".local" / "share" / "omni_reader" / "models"
        self._kokoro: Any = None
        self._model_path: Optional[Path] = None
        self._voices_path: Optional[Path] = None
        self._voices_cache: List[str] = []

    @property
    def name(self) -> str:
        return "Kokoro Neural (ONNX)"

    def _locate_files(self) -> bool:
        if not self.models_dir.exists():
            return False

        # Look for model weights
        candidate_models = [
            self.models_dir / "kokoro-v1.0.int8.onnx",
            self.models_dir / "kokoro-v1.0.onnx",
            self.models_dir / "kokoro-v0_19.onnx",
        ]
        for c in candidate_models:
            if c.exists() and c.stat().st_size > 10_000_000:
                self._model_path = c
                break

        # Look for voices binary
        candidate_voices = [
            self.models_dir / "voices-v1.0.bin",
            self.models_dir / "voices.bin",
        ]
        for v in candidate_voices:
            if v.exists() and v.stat().st_size > 1_000_000:
                self._voices_path = v
                break

        return bool(self._model_path and self._voices_path)

    def is_available(self) -> bool:
        return self._locate_files()

    def download_models_if_missing(self, progress_callback=None) -> bool:
        """Downloads Kokoro model files if not already present."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        model_target = self.models_dir / "kokoro-v1.0.int8.onnx"
        voices_target = self.models_dir / "voices-v1.0.bin"

        def _report(chunk_idx, chunk_size, total_size):
            if progress_callback and total_size > 0:
                percent = min(100.0, (chunk_idx * chunk_size / total_size) * 100.0)
                progress_callback(percent)

        if not model_target.exists() or model_target.stat().st_size < 10_000_000:
            print(f"[KokoroEngine] Downloading {DEFAULT_MODEL_URL}...")
            urllib.request.urlretrieve(DEFAULT_MODEL_URL, model_target, reporthook=_report)

        if not voices_target.exists() or voices_target.stat().st_size < 1_000_000:
            print(f"[KokoroEngine] Downloading {DEFAULT_VOICES_URL}...")
            urllib.request.urlretrieve(DEFAULT_VOICES_URL, voices_target)

        return self._locate_files()

    def _ensure_loaded(self):
        if self._kokoro is None:
            if not self._locate_files():
                self.download_models_if_missing()

            if not self._model_path or not self._voices_path:
                raise RuntimeError("Kokoro model files not found and download failed.")

            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro(str(self._model_path), str(self._voices_path))
            raw_voices = self._kokoro.get_voices()

            # Order voices: featured first, then rest sorted alphabetically
            featured_set = set(FEATURED_VOICES)
            rest = [v for v in raw_voices if v not in featured_set]
            rest.sort()
            self._voices_cache = [v for v in FEATURED_VOICES if v in raw_voices] + rest

    def get_available_voices(self) -> List[str]:
        try:
            self._ensure_loaded()
            return self._voices_cache
        except Exception:
            return FEATURED_VOICES

    def synthesize(self, text: str, voice: str = "af_sky", speed: float = 1.4) -> Tuple[np.ndarray, int]:
        self._ensure_loaded()
        if not voice or voice not in self._voices_cache:
            voice = "af_sky"

        # Determine language code based on voice prefix (af/am -> en-us, bf/bm -> en-gb)
        lang = "en-gb" if voice.startswith("b") else "en-us"
        samples, sr = self._kokoro.create(text, voice=voice, speed=speed, lang=lang)
        return samples, sr
