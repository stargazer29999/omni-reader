"""System tray interface for OmniReader using pystray."""

import threading
from typing import Any, Dict, Optional
from PIL import Image, ImageDraw
import pystray

from .daemon import OmniDaemon
from .player import STATE_IDLE, STATE_PAUSED, STATE_PLAYING

# Curated voice labels for user-friendly display
KOKORO_VOICE_LABELS = {
    "af_sky": "Sky (US Female - Natural)",
    "af_sarah": "Sarah (US Female - Warm)",
    "af_bella": "Bella (US Female - Expressive)",
    "af_nicole": "Nicole (US Female - Narrator)",
    "am_adam": "Adam (US Male - Crisp)",
    "am_michael": "Michael (US Male - Deep)",
    "bf_emma": "Emma (UK Female - Articulate)",
    "bf_isabella": "Isabella (UK Female - Refined)",
    "bm_george": "George (UK Male - Warm)",
    "bm_lewis": "Lewis (UK Male - Natural)",
}

AVAILABLE_SPEEDS = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]


def render_icon(state: str = STATE_IDLE) -> Image.Image:
    """Renders a crisp 64x64 status bar icon for macOS / Linux."""
    size = (64, 64)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if state == STATE_PLAYING:
        # Speaker with active sound waves
        # Base speaker body
        draw.polygon([(14, 24), (24, 24), (36, 14), (36, 50), (24, 40), (14, 40)], fill=(50, 205, 50, 255))
        # Sound arc 1
        draw.arc((30, 20, 46, 44), start=-60, end=60, fill=(50, 205, 50, 255), width=4)
        # Sound arc 2
        draw.arc((26, 12, 54, 52), start=-60, end=60, fill=(50, 205, 50, 255), width=4)
    elif state == STATE_PAUSED:
        # Pause bars
        draw.rectangle([18, 16, 28, 48], fill=(255, 165, 0, 255))
        draw.rectangle([36, 16, 46, 48], fill=(255, 165, 0, 255))
    else:
        # Idle: Clean speaker glyph
        draw.polygon([(16, 24), (26, 24), (38, 14), (38, 50), (26, 40), (16, 40)], fill=(200, 200, 200, 255))
        draw.arc((32, 22, 46, 42), start=-45, end=45, fill=(160, 160, 160, 255), width=3)

    return image


class OmniTrayApp:
    def __init__(self, daemon: OmniDaemon):
        self.daemon = daemon
        self.icon: Any = None
        self._current_state = STATE_IDLE
        self._lock = threading.Lock()

        # Connect daemon status callbacks
        self.daemon.on_status_change = self._on_daemon_status

    def _on_daemon_status(self, status: Dict[str, Any]) -> None:
        state = status.get("state", STATE_IDLE)
        if self.icon:
            if state != self._current_state:
                self._current_state = state
                self.icon.icon = render_icon(state)
            self.icon.update_menu()

    def _set_speed_handler(self, speed: float):
        def _handler(icon, item):
            self.daemon.set_speed(speed)
            icon.update_menu()
        return _handler

    def _is_speed_checked(self, speed: float):
        return lambda item: abs(float(self.daemon.config.get("speed", 1.4)) - speed) < 0.05

    def _set_voice_handler(self, voice: str):
        def _handler(icon, item):
            self.daemon.set_voice(voice)
            icon.update_menu()
        return _handler

    def _is_voice_checked(self, voice: str):
        return lambda item: self.daemon.get_active_voice() == voice

    def _set_engine_handler(self, engine_name: str):
        def _handler(icon, item):
            self.daemon.set_engine(engine_name)
            icon.update_menu()
        return _handler

    def _is_engine_checked(self, engine_name: str):
        return lambda item: self.daemon.config.get("engine", "kokoro") == engine_name

    def _build_menu(self) -> pystray.Menu:
        status = self.daemon.get_status()
        state = status.get("state", STATE_IDLE)
        cur_sent = status.get("current_sentence", 0)
        tot_sent = status.get("total_sentences", 0)

        # Dynamic status label
        if state == STATE_PLAYING:
            status_text = f"🔊 Reading {cur_sent}/{tot_sent}..." if tot_sent else "🔊 Speaking..."
        elif state == STATE_PAUSED:
            status_text = f"⏸️ Paused ({cur_sent}/{tot_sent})" if tot_sent else "⏸️ Paused"
        else:
            status_text = "🟢 OmniReader: Ready"

        # Speed sub-items
        speed_items = [
            pystray.MenuItem(
                f"{s}x" + (" (Default)" if s == 1.4 else ""),
                self._set_speed_handler(s),
                checked=self._is_speed_checked(s),
            )
            for s in AVAILABLE_SPEEDS
        ]

        # Voice sub-items
        engine = self.daemon.config.get("engine", "kokoro")
        if engine == "kokoro":
            voice_items = [
                pystray.MenuItem(
                    label,
                    self._set_voice_handler(v_id),
                    checked=self._is_voice_checked(v_id),
                )
                for v_id, label in KOKORO_VOICE_LABELS.items()
            ]
        else:
            system_voices = self.daemon.system_engine.get_available_voices()[:10]
            voice_items = [
                pystray.MenuItem(
                    v,
                    self._set_voice_handler(v),
                    checked=self._is_voice_checked(v),
                )
                for v in system_voices
            ]

        # Pause/Resume item
        if state == STATE_PLAYING:
            pause_resume_item = pystray.MenuItem("⏸️ Pause", lambda icon, item: self.daemon.pause())
        else:
            pause_resume_item = pystray.MenuItem("▶️ Resume", lambda icon, item: self.daemon.resume(), enabled=(state == STATE_PAUSED))

        # Menu assembly
        menu_items = [
            pystray.MenuItem(status_text, lambda icon, item: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔊 Read Active Window / Article", lambda icon, item: self.daemon.read_auto()),
            pystray.MenuItem("📝 Read Selection", lambda icon, item: self.daemon.read_selection()),
            pystray.MenuItem("📋 Read Clipboard", lambda icon, item: self.daemon.read_clipboard()),
            pystray.Menu.SEPARATOR,
            pause_resume_item,
            pystray.MenuItem("⏩ Skip Sentence", lambda icon, item: self.daemon.skip(), enabled=(state == STATE_PLAYING)),
            pystray.MenuItem("⏹️ Stop Speaking", lambda icon, item: self.daemon.stop(), enabled=(state != STATE_IDLE)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⚡ Playback Speed", pystray.Menu(*speed_items)),
            pystray.MenuItem("🎙️ Voice", pystray.Menu(*voice_items)),
            pystray.MenuItem("⚙️ Engine", pystray.Menu(
                pystray.MenuItem("Kokoro Neural (ONNX)", self._set_engine_handler("kokoro"), checked=self._is_engine_checked("kokoro")),
                pystray.MenuItem("System Native", self._set_engine_handler("system"), checked=self._is_engine_checked("system")),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🚪 Quit OmniReader", self._quit_handler),
        ]

        return pystray.Menu(*menu_items)

    def _quit_handler(self, icon, item):
        self.daemon.shutdown()
        icon.stop()

    def run(self) -> None:
        """Starts the tray application (must run on main thread on macOS)."""
        self.icon = pystray.Icon(
            name="omni_reader",
            icon=render_icon(STATE_IDLE),
            title="OmniReader",
            menu=self._build_menu,
        )
        self.icon.run()
