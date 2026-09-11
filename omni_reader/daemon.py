"""Core Daemon orchestrating TTS engines, audio player, and IPC commands."""

import threading
import time
from typing import Any, Dict, List, Optional
import numpy as np

from .config import Config
from .engines.base import BaseTTSEngine
from .engines.kokoro_engine import KokoroEngine
from .engines.system_engine import SystemEngine
from .extractor import get_auto_context_text, get_clipboard_text, get_selected_text
from .follower import ReadingFollower
from .ipc import IPCServer
from .player import AudioPlayer, STATE_IDLE, STATE_PAUSED, STATE_PLAYING
from .text_splitter import split_sentences


class OmniDaemon:
    def __init__(self, config: Optional[Config] = None, on_status_change: Optional[Any] = None):
        self.config = config or Config()
        self.on_status_change = on_status_change

        # Initialize engines
        self.kokoro_engine = KokoroEngine(models_dir=self.config.get("models_dir"))
        self.system_engine = SystemEngine()

        # Initialize player
        self.player = AudioPlayer(
            on_state_change=self._handle_player_state,
            on_sentence_change=self._handle_sentence_change,
        )

        # Initialize visual follower & auto-scroller
        self.follower = ReadingFollower(
            enable_hud=self.config.get("enable_hud", True),
            enable_scroll=self.config.get("enable_scroll", True),
        )

        # Active synthesis state
        self._generation_id = 0
        self._lock = threading.RLock()
        self._synthesis_thread: Optional[threading.Thread] = None

        # IPC Server
        socket_path = self.config.get("socket_path", "/tmp/omni_reader.sock")
        self.ipc_server = IPCServer(socket_path, self.handle_ipc_command)
        self.ipc_server.start()

        # Hotkey listener
        self._hotkey_listener = None
        self._setup_hotkeys()

    def get_current_engine(self) -> BaseTTSEngine:
        engine_name = self.config.get("engine", "kokoro")
        if engine_name == "kokoro" and self.kokoro_engine.is_available():
            return self.kokoro_engine
        return self.system_engine

    def get_active_voice(self) -> str:
        engine_name = self.config.get("engine", "kokoro")
        if engine_name == "kokoro":
            return self.config.get("kokoro_voice", "af_sky")
        return self.config.get("system_voice", "default")

    def _handle_player_state(self, state: str) -> None:
        if state == STATE_IDLE:
            self.follower.stop()
        if self.on_status_change:
            try:
                self.on_status_change(self.get_status())
            except Exception:
                pass

    def _handle_sentence_change(self, index: int, total: int, text: str) -> None:
        self.follower.on_sentence(index - 1, total, text)
        if self.on_status_change:
            try:
                self.on_status_change(self.get_status())
            except Exception:
                pass

    def _setup_hotkeys(self) -> None:
        """Sets up global hotkey listener with pynput (non-blocking, tolerant of permission errors)."""
        try:
            from pynput import keyboard

            read_combo = self.config.get("hotkey_read", "<ctrl>+<alt>+r")
            stop_combo = self.config.get("hotkey_stop", "<ctrl>+<alt>+s")

            def on_read_triggered():
                self.read_auto()

            def on_stop_triggered():
                self.stop()

            hotkeys = keyboard.GlobalHotKeys({
                read_combo: on_read_triggered,
                stop_combo: on_stop_triggered,
            })
            hotkeys.start()
            self._hotkey_listener = hotkeys
            print(f"[Daemon] Hotkeys registered: Read ({read_combo}), Stop ({stop_combo})")
        except Exception as e:
            print(f"[Daemon] Global hotkey registration note: {e}")

    def speak(self, text: str) -> bool:
        """Initiates streaming synthesis and playback of text."""
        if not text or not text.strip():
            return False

        with self._lock:
            # Stop existing playback
            self.stop()
            sentences = split_sentences(text)
            if not sentences:
                return False

            self.follower.start(sentences)
            self._generation_id += 1
            gen_id = self._generation_id

            self._synthesis_thread = threading.Thread(
                target=self._synthesis_worker,
                args=(text, gen_id),
                daemon=True,
                name=f"OmniSynth-{gen_id}",
            )
            self._synthesis_thread.start()

        return True

    def _synthesis_worker(self, raw_text: str, gen_id: int) -> None:
        sentences = split_sentences(raw_text)
        if not sentences:
            return

        total = len(sentences)
        self.player.set_total_sentences(total)

        engine = self.get_current_engine()
        voice = self.get_active_voice()
        speed = float(self.config.get("speed", 1.4))

        for idx, sentence in enumerate(sentences, start=1):
            with self._lock:
                if self._generation_id != gen_id:
                    # New generation job superseded this one
                    break

            try:
                samples, sr = engine.synthesize(sentence, voice=voice, speed=speed)
                with self._lock:
                    if self._generation_id != gen_id:
                        break
                    self.player.queue_chunk(samples, sr, sentence, idx, total)
            except Exception as e:
                print(f"[Daemon] Synthesis error for sentence '{sentence[:30]}...': {e}")
                # Fallback to system engine if Kokoro fails
                if engine != self.system_engine and self.system_engine.is_available():
                    try:
                        samples, sr = self.system_engine.synthesize(sentence, voice="default", speed=speed)
                        with self._lock:
                            if self._generation_id != gen_id:
                                break
                            self.player.queue_chunk(samples, sr, sentence, idx, total)
                    except Exception as err2:
                        print(f"[Daemon] Fallback synthesis also failed: {err2}")

        with self._lock:
            if self._generation_id == gen_id:
                self.player.mark_stream_end()

    def read_auto(self) -> bool:
        text = get_auto_context_text()
        if text:
            return self.speak(text)
        return False

    def read_selection(self) -> bool:
        text = get_selected_text()
        if text:
            return self.speak(text)
        return False

    def read_clipboard(self) -> bool:
        text = get_clipboard_text()
        if text:
            return self.speak(text)
        return False

    def pause(self) -> None:
        self.player.pause()

    def resume(self) -> None:
        self.player.resume()

    def toggle_pause(self) -> None:
        self.player.toggle_pause()

    def skip(self) -> None:
        self.player.skip()

    def stop(self) -> None:
        with self._lock:
            self._generation_id += 1  # Invalidate current synthesis worker
            self.player.stop()
            self.follower.stop()

    def set_speed(self, speed: float) -> None:
        speed = max(0.5, min(3.0, round(float(speed), 2)))
        self.config.set("speed", speed)

    def set_voice(self, voice: str) -> None:
        engine_name = self.config.get("engine", "kokoro")
        if engine_name == "kokoro":
            self.config.set("kokoro_voice", voice)
        else:
            self.config.set("system_voice", voice)

    def set_engine(self, engine_name: str) -> None:
        if engine_name in ("kokoro", "system"):
            self.config.set("engine", engine_name)

    def get_status(self) -> Dict[str, Any]:
        player_status = self.player.get_status()
        current_engine = self.get_current_engine()
        return {
            **player_status,
            "engine": self.config.get("engine", "kokoro"),
            "voice": self.get_active_voice(),
            "speed": self.config.get("speed", 1.4),
            "kokoro_ready": self.kokoro_engine.is_available(),
            "system_ready": self.system_engine.is_available(),
        }

    def handle_ipc_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = payload.get("action", "")

        if action == "speak":
            text = payload.get("text", "")
            success = self.speak(text)
            return {"status": "ok" if success else "error", "message": "Speaking started" if success else "Empty text"}

        elif action in ("read_auto", "read_window"):
            success = self.read_auto()
            return {"status": "ok" if success else "error", "message": "Reading active window/selection" if success else "No text found in active window"}

        elif action == "read_selection":
            success = self.read_selection()
            return {"status": "ok" if success else "error", "message": "Reading selection" if success else "No selection found"}

        elif action == "read_clipboard":
            success = self.read_clipboard()
            return {"status": "ok" if success else "error", "message": "Reading clipboard" if success else "Clipboard is empty"}

        elif action == "pause":
            self.pause()
            return {"status": "ok", "state": self.player.state}

        elif action == "resume":
            self.resume()
            return {"status": "ok", "state": self.player.state}

        elif action == "toggle_pause":
            self.toggle_pause()
            return {"status": "ok", "state": self.player.state}

        elif action == "skip":
            self.skip()
            return {"status": "ok", "message": "Skipped to next sentence"}

        elif action == "stop":
            self.stop()
            return {"status": "ok", "state": "idle"}

        elif action == "set_speed":
            speed = float(payload.get("speed", 1.4))
            self.set_speed(speed)
            return {"status": "ok", "speed": speed}

        elif action == "set_voice":
            voice = str(payload.get("voice", "af_sky"))
            self.set_voice(voice)
            return {"status": "ok", "voice": voice}

        elif action == "set_engine":
            eng = str(payload.get("engine", "kokoro"))
            self.set_engine(eng)
            return {"status": "ok", "engine": eng}

        elif action == "status":
            return {"status": "ok", "data": self.get_status()}

        return {"status": "error", "message": f"Unknown action: {action}"}

    def shutdown(self) -> None:
        self.stop()
        self.follower.stop()
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
        self.ipc_server.stop()
