"""Unified visual follower and auto-scroller coordinator for OmniReader."""

import json
import os
import platform
import subprocess
import sys
import threading
from typing import List, Optional

from .scroller import WindowScroller


class ReadingFollower:
    def __init__(self, enable_hud: bool = True, enable_scroll: bool = True):
        self.enable_hud = enable_hud and (platform.system() == "Darwin")
        self.enable_scroll = enable_scroll and (platform.system() == "Darwin")

        self.scroller = WindowScroller() if self.enable_scroll else None
        self._hud_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self.sentences: List[str] = []

    def start(self, sentences: List[str]) -> None:
        """Starts visual tracking for the provided sentences."""
        with self._lock:
            self.sentences = sentences

            # 1. Attach frontmost app for window scrolling
            if self.scroller:
                self.scroller.attach_frontmost()

            # 2. Launch HUD process if enabled
            if self.enable_hud and sentences:
                self._stop_hud_locked()
                try:
                    # Resolve python binary in virtual environment
                    python_bin = sys.executable
                    self._hud_proc = subprocess.Popen(
                        [python_bin, "-m", "omni_reader.hud"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        bufsize=1
                    )
                    # Initialize HUD with sentence list
                    init_payload = json.dumps({"action": "init", "sentences": sentences}) + "\n"
                    self._hud_proc.stdin.write(init_payload)
                    self._hud_proc.stdin.flush()
                except Exception as e:
                    self._hud_proc = None

    def on_sentence(self, index: int, total: int, sentence_text: str) -> None:
        """Called as each sentence begins playing to highlight and scroll."""
        with self._lock:
            # 1. Update HUD highlight and auto-scroll
            if self._hud_proc and self._hud_proc.poll() is None:
                try:
                    msg = json.dumps({"action": "highlight", "index": index}) + "\n"
                    self._hud_proc.stdin.write(msg)
                    self._hud_proc.stdin.flush()
                except Exception:
                    pass

            # 2. Auto-scroll background application window
            if self.scroller:
                try:
                    self.scroller.on_sentence_progress(index, total, sentence_text)
                except Exception:
                    pass

    def stop(self) -> None:
        """Closes HUD and stops scrolling."""
        with self._lock:
            self._stop_hud_locked()

    def _stop_hud_locked(self) -> None:
        if self._hud_proc:
            try:
                if self._hud_proc.poll() is None:
                    self._hud_proc.stdin.write(json.dumps({"action": "stop"}) + "\n")
                    self._hud_proc.stdin.flush()
                    self._hud_proc.wait(timeout=0.5)
            except Exception:
                try:
                    self._hud_proc.terminate()
                except Exception:
                    pass
            finally:
                self._hud_proc = None
