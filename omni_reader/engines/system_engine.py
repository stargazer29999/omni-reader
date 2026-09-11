"""System Native Text-to-Speech Engine (macOS say / Linux espeak/spd-say)."""

import os
import platform
import shutil
import subprocess
import tempfile
import wave
from typing import List, Tuple
import numpy as np

from .base import BaseTTSEngine

DEFAULT_MACOS_VOICES = [
    "Samantha",     # US Female (Classic natural)
    "Alex",         # US Male (Expressive classic)
    "Daniel",       # UK Male
    "Oliver",       # UK Male
    "Ava",          # US Female
    "Zoe",          # US Female
    "Victoria",     # US Female
    "Tom",          # US Male
]


class SystemEngine(BaseTTSEngine):
    def __init__(self):
        self._os_type = platform.system()
        self._voices_cache: List[str] = []

    @property
    def name(self) -> str:
        return "System Native"

    def is_available(self) -> bool:
        if self._os_type == "Darwin":
            return shutil.which("say") is not None
        elif self._os_type == "Linux":
            return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None
        return False

    def get_available_voices(self) -> List[str]:
        if self._voices_cache:
            return self._voices_cache

        voices: List[str] = []
        if self._os_type == "Darwin":
            try:
                res = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True)
                # Parse lines like "Samantha            en_US    # Hello, my name is Samantha..."
                for line in res.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        voice_name = parts[0]
                        lang = parts[1]
                        if lang.startswith("en"):
                            voices.append(voice_name)
            except Exception:
                pass

            if not voices:
                voices = DEFAULT_MACOS_VOICES
            else:
                # Ensure preferred voices are at the top
                pref_set = set(DEFAULT_MACOS_VOICES)
                top = [v for v in DEFAULT_MACOS_VOICES if v in voices]
                rest = [v for v in voices if v not in pref_set]
                voices = top + rest

        elif self._os_type == "Linux":
            voices = ["default", "en", "en-us", "en-gb"]

        self._voices_cache = voices
        return self._voices_cache

    def synthesize(self, text: str, voice: str = "default", speed: float = 1.4) -> Tuple[np.ndarray, int]:
        if not self.is_available():
            raise RuntimeError("System TTS binary not found.")

        # Rate mapping: baseline normal is ~175 wpm. Speed 1.4x is ~245 wpm.
        target_wpm = int(175 * max(0.5, min(3.0, speed)))

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            if self._os_type == "Darwin":
                cmd = [
                    "say",
                    "-r", str(target_wpm),
                    "--file-format=WAVE",
                    "--data-format=LEI16@24000",
                    "-o", tmp_path,
                ]
                if voice and voice != "default":
                    cmd.extend(["-v", voice])
                cmd.append(text)
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            elif self._os_type == "Linux":
                espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
                if not espeak_bin:
                    raise RuntimeError("No espeak binary found on Linux.")
                # espeak default speed is 175 wpm
                cmd = [
                    espeak_bin,
                    "-s", str(target_wpm),
                    "-w", tmp_path,
                ]
                if voice and voice != "default":
                    cmd.extend(["-v", voice])
                cmd.append(text)
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                raise NotImplementedError(f"Unsupported platform: {self._os_type}")

            # Read back generated WAV
            with wave.open(tmp_path, "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)
                # Convert 16-bit PCM to float32 normalized between -1.0 and 1.0
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            return samples, sr

        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
