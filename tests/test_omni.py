"""Automated test suite for OmniReader."""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omni_reader.config import Config
from omni_reader.engines.kokoro_engine import KokoroEngine
from omni_reader.engines.system_engine import SystemEngine
from omni_reader.ipc import IPCClient
from omni_reader.daemon import OmniDaemon
from omni_reader.text_splitter import clean_markdown_and_text, split_sentences


def test_text_splitter():
    print("--- Testing Text Splitter ---")
    raw = """
# Chapter 1: Introduction to AI

Dr. Smith visited the U.S. lab on Jan. 15th at 3.14 PM. He stated: "Local execution is fast."
Check out [this link](https://example.com/research) for details!

- Bullet item one
- Bullet item two with **bold text** and `code sample`.

Furthermore, another full sentence appears right here.
"""
    cleaned = clean_markdown_and_text(raw)
    sentences = split_sentences(raw)
    print(f"Split into {len(sentences)} sentences:")
    for idx, s in enumerate(sentences, 1):
        print(f"  [{idx}] {s}")

    assert len(sentences) >= 3, f"Expected at least 3 sentences, got {len(sentences)}"
    # Verify Dr. Smith and 3.14 PM were not split into separate sentences
    assert any("Dr. Smith" in s and "3.14 PM" in s for s in sentences), "Abbreviation or decimal was split incorrectly!"
    print("✓ Text splitter passed!\n")


def test_system_engine():
    print("--- Testing System TTS Engine ---")
    engine = SystemEngine()
    assert engine.is_available(), "System engine should be available"
    voices = engine.get_available_voices()
    print(f"System voices count: {len(voices)}")

    t0 = time.perf_counter()
    samples, sr = engine.synthesize("System engine test.", voice="Samantha", speed=1.4)
    t1 = time.perf_counter()
    duration = len(samples) / sr
    print(f"System synthesis: {len(samples)} samples @ {sr}Hz ({duration:.2f}s audio) in {(t1-t0)*1000:.1f}ms")
    assert len(samples) > 0
    assert sr > 0
    print("✓ System engine passed!\n")


def test_kokoro_engine():
    print("--- Testing Kokoro Neural Engine ---")
    engine = KokoroEngine()
    if not engine.is_available():
        print("Kokoro model files missing, skipping Kokoro test.")
        return

    voices = engine.get_available_voices()
    print(f"Kokoro voices count: {len(voices)}")
    assert "af_sky" in voices

    t0 = time.perf_counter()
    samples, sr = engine.synthesize("Kokoro neural speech synthesis test.", voice="af_sky", speed=1.4)
    t1 = time.perf_counter()
    duration = len(samples) / sr
    print(f"Kokoro synthesis: {len(samples)} samples @ {sr}Hz ({duration:.2f}s audio) in {(t1-t0)*1000:.1f}ms")
    assert len(samples) > 0
    assert sr == 24000
    print("✓ Kokoro engine passed!\n")


def test_daemon_and_ipc():
    print("--- Testing Daemon and IPC ---")
    test_socket = "/tmp/test_omni_daemon.sock"
    config = Config()
    config.set("socket_path", test_socket)
    config.set("speed", 1.4)

    daemon = OmniDaemon(config=config)
    client = IPCClient(socket_path=test_socket)

    try:
        time.sleep(0.1)
        assert client.is_running(), "Daemon socket should be reachable"

        # Check status
        status = client.send_command("status")
        assert status.get("status") == "ok"
        print("Initial status:", status.get("data", {}).get("state"))

        # Set speed
        res = client.send_command("set_speed", speed=1.6)
        assert res.get("status") == "ok"
        assert res.get("speed") == 1.6

        # Set voice
        res = client.send_command("set_voice", voice="af_sarah")
        assert res.get("status") == "ok"

        # Trigger speech
        res = client.send_command("speak", text="First test sentence. Second test sentence.")
        assert res.get("status") == "ok"

        time.sleep(0.5)
        status = client.send_command("status")
        print("Status while playing:", status.get("data", {}).get("state"))

        # Test pause
        res = client.send_command("pause")
        assert res.get("status") == "ok"
        print("Pause state:", res.get("state"))

        # Test resume
        res = client.send_command("resume")
        assert res.get("status") == "ok"
        print("Resume state:", res.get("state"))

        # Test stop
        res = client.send_command("stop")
        assert res.get("status") == "ok"
        print("Stop state:", res.get("state"))

        print("✓ Daemon and IPC passed!\n")

    finally:
        daemon.shutdown()
        if os.path.exists(test_socket):
            os.remove(test_socket)


if __name__ == "__main__":
    test_text_splitter()
    test_system_engine()
    test_kokoro_engine()
    test_daemon_and_ipc()
    print("==========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==========================================")
