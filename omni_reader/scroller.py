"""Active Application Window Scroller for OmniReader on macOS.

Tracks speech progress and issues smooth scroll events to the frontmost application
(Safari, Chrome, Preview, Notes, VS Code, etc.) so that the view follows the spoken text
when content exceeds the current visual scope.
"""

import os
import platform
import subprocess
import time
from typing import Optional

try:
    from Quartz import (
        CGEventCreateScrollWheelEvent, kCGScrollEventUnitLine,
        kCGScrollEventUnitPixel, CGEventPost, kCGHIDEventTap
    )
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False


class WindowScroller:
    def __init__(self):
        self.app_name: str = ""
        self.total_sentences: int = 0
        self.last_scrolled_sentence: int = 0
        self.enabled: bool = (platform.system() == "Darwin")

    def attach_frontmost(self) -> str:
        """Captures the name of the application currently focused before speech starts."""
        if not self.enabled:
            return ""
        cmd = 'tell application "System Events" to get name of first application process whose frontmost is true'
        try:
            res = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True, timeout=1)
            self.app_name = res.stdout.strip()
            self.last_scrolled_sentence = 0
        except Exception:
            self.app_name = ""
        return self.app_name

    def on_sentence_progress(self, index: int, total: int, sentence_text: str):
        """Called when sentence `index` begins speaking. Scrolls window down progressively."""
        if not self.enabled or not HAS_QUARTZ:
            return

        self.total_sentences = total

        # Don't scroll on the first sentence (user is already looking at it)
        if index <= 0:
            return

        # Check if we should scroll: scroll every 2 sentences, or if sentence is long (>25 words)
        word_count = len(sentence_text.split())
        sentences_since_last_scroll = index - self.last_scrolled_sentence

        should_scroll = False
        lines_to_scroll = 3

        if sentences_since_last_scroll >= 2:
            should_scroll = True
            lines_to_scroll = 4
        elif word_count > 25 and sentences_since_last_scroll >= 1:
            should_scroll = True
            lines_to_scroll = 3

        if should_scroll:
            self._perform_scroll(lines_to_scroll)
            self.last_scrolled_sentence = index

    def _perform_scroll(self, lines: int):
        """Executes smooth scroll downward in the active application."""
        # Try browser-native smooth scroll if Safari
        if self.app_name == "Safari":
            script = f'tell application "Safari" to do JavaScript "window.scrollBy({{top: {lines * 35}, behavior: \'smooth\'}});" in front document'
            try:
                res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=1)
                if res.returncode == 0:
                    return
            except Exception:
                pass

        # Universal Quartz scroll event (works across Chrome, Preview, VS Code, Notes, Slack, etc.)
        try:
            # Negative delta scrolls downwards
            event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 1, -lines)
            CGEventPost(kCGHIDEventTap, event)
        except Exception:
            pass
