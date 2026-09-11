"""Command-Line Interface and IPC client for OmniReader."""

import argparse
import sys
from typing import List, Optional

from .config import Config
from .extractor import get_auto_context_text, get_clipboard_text, get_selected_text
from .ipc import DaemonNotRunningError, IPCClient


def direct_speak_fallback(text: str, enable_hud: bool = True, enable_scroll: bool = True) -> None:
    """Speaks directly if daemon is not active."""
    from .daemon import OmniDaemon
    config = Config()
    if not enable_hud:
        config.set("enable_hud", False)
    if not enable_scroll:
        config.set("enable_scroll", False)
    daemon = OmniDaemon(config=config)
    daemon.speak(text)
    # Block until playback completes
    import time
    while daemon.player.state != "idle":
        time.sleep(0.1)
    daemon.shutdown()


def run_cli(args: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omnisay",
        description="OmniReader: Universal Low-Latency Local Screen & Document Reader",
    )

    parser.add_argument("text", nargs="*", help="Text to read aloud (reads from stdin if omitted and piped)")
    parser.add_argument("--window", "-w", action="store_true", help="Read entire text of active window/article")
    parser.add_argument("--selection", "-s", action="store_true", help="Read highlighted text selection")
    parser.add_argument("--clipboard", "-c", action="store_true", help="Read clipboard text")
    parser.add_argument("--pause", action="store_true", help="Pause speech")
    parser.add_argument("--resume", action="store_true", help="Resume speech")
    parser.add_argument("--toggle", action="store_true", help="Toggle pause/resume")
    parser.add_argument("--stop", "-x", action="store_true", help="Stop speech immediately")
    parser.add_argument("--next", "--skip", dest="skip", action="store_true", help="Skip to next sentence")
    parser.add_argument("--speed", type=float, help="Set playback speed (e.g. 1.0, 1.4, 2.0)")
    parser.add_argument("--voice", type=str, help="Set voice identifier (e.g. af_sky, am_adam, Samantha)")
    parser.add_argument("--engine", choices=["kokoro", "system"], help="Set TTS engine")
    parser.add_argument("--status", action="store_true", help="Show current playback status")
    parser.add_argument("--daemon", action="store_true", help="Launch the OmniReader background tray daemon")
    parser.add_argument("--no-hud", action="store_true", help="Disable floating teleprompter HUD overlay")
    parser.add_argument("--no-scroll", action="store_true", help="Disable active window auto-scroll")

    parsed = parser.parse_args(args)
    client = IPCClient()
    text_to_speak = ""

    if parsed.daemon:
        from .daemon import OmniDaemon
        from .tray import OmniTrayApp
        daemon = OmniDaemon()
        tray = OmniTrayApp(daemon)
        print("[OmniReader] Starting tray daemon...")
        tray.run()
        return 0

    # Read action queries
    try:
        if parsed.status:
            res = client.send_command("status")
            data = res.get("data", {})
            print(f"State: {data.get('state', 'unknown')}")
            print(f"Engine: {data.get('engine', 'unknown')}")
            print(f"Voice: {data.get('voice', 'unknown')} @ {data.get('speed', 1.0)}x")
            print(f"Progress: Sentence {data.get('current_sentence', 0)} of {data.get('total_sentences', 0)}")
            return 0

        if parsed.pause:
            client.send_command("pause")
            print("Paused.")
            return 0

        if parsed.resume:
            client.send_command("resume")
            print("Resumed.")
            return 0

        if parsed.toggle:
            client.send_command("toggle_pause")
            return 0

        if parsed.stop:
            client.send_command("stop")
            print("Stopped.")
            return 0

        if parsed.skip:
            client.send_command("skip")
            print("Skipped to next sentence.")
            return 0

        if parsed.speed is not None:
            client.send_command("set_speed", speed=parsed.speed)
            print(f"Speed set to {parsed.speed}x")
            return 0

        if parsed.voice:
            client.send_command("set_voice", voice=parsed.voice)
            print(f"Voice set to {parsed.voice}")
            return 0

        if parsed.engine:
            client.send_command("set_engine", engine=parsed.engine)
            print(f"Engine set to {parsed.engine}")
            return 0

        # Read text trigger
        text_to_speak = ""

        if parsed.window:
            if client.is_running():
                client.send_command("read_window")
                return 0
            else:
                text_to_speak = get_auto_context_text()

        elif parsed.selection:
            if client.is_running():
                client.send_command("read_selection")
                return 0
            else:
                text_to_speak = get_selected_text()

        elif parsed.clipboard:
            if client.is_running():
                client.send_command("read_clipboard")
                return 0
            else:
                text_to_speak = get_clipboard_text()

        elif parsed.text:
            text_to_speak = " ".join(parsed.text).strip()

        elif not sys.stdin.isatty():
            # Reading from pipe
            text_to_speak = sys.stdin.read().strip()

        else:
            # No args and no pipe: default to smart context (selection if present, otherwise active window)
            if client.is_running():
                client.send_command("read_auto")
                return 0
            else:
                text_to_speak = get_auto_context_text()

        if not text_to_speak:
            print("No text provided or selected.", file=sys.stderr)
            return 1

        if client.is_running():
            client.send_command("speak", text=text_to_speak)
        else:
            direct_speak_fallback(
                text_to_speak,
                enable_hud=not parsed.no_hud,
                enable_scroll=not parsed.no_scroll
            )

        return 0

    except DaemonNotRunningError:
        # If client command was a control command like pause/stop, report daemon not running
        if parsed.pause or parsed.resume or parsed.stop or parsed.skip:
            print("OmniReader daemon is not currently running.", file=sys.stderr)
            return 1

        # If it was a speak command, fall back to direct speak
        if text_to_speak:
            direct_speak_fallback(
                text_to_speak,
                enable_hud=not parsed.no_hud,
                enable_scroll=not parsed.no_scroll
            )
            return 0

        print("OmniReader daemon is not currently running.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_cli())
