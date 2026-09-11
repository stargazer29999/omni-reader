"""Streaming audio player with sample-accurate pause/resume and queue management."""

import queue
import threading
import time
from typing import Callable, Optional, Tuple
import numpy as np
import sounddevice as sd

STATE_IDLE = "idle"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"


class AudioPlayer:
    def __init__(self, on_state_change: Optional[Callable[[str], None]] = None,
                 on_sentence_change: Optional[Callable[[int, int, str], None]] = None):
        self.state = STATE_IDLE
        self.on_state_change = on_state_change
        self.on_sentence_change = on_sentence_change

        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.RLock()
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._skip_requested = threading.Event()
        self._pause_requested = threading.Event()

        # Current playback position tracking
        self._current_samples: Optional[np.ndarray] = None
        self._current_pos = 0
        self._current_sr = 24000
        self._current_text = ""
        self._current_index = 0
        self._total_sentences = 0
        self._stream: Optional[sd.OutputStream] = None

        self._start_worker()

    def _set_state(self, new_state: str) -> None:
        with self._lock:
            if self.state != new_state:
                self.state = new_state
                if self.on_state_change:
                    try:
                        self.on_state_change(new_state)
                    except Exception as e:
                        print(f"[Player] State change callback error: {e}")

    def _start_worker(self) -> None:
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="OmniAudioWorker")
        self._worker_thread.start()

    def set_total_sentences(self, total: int) -> None:
        with self._lock:
            self._total_sentences = total

    def queue_chunk(self, samples: np.ndarray, sr: int, text: str, index: int, total: int) -> None:
        """Pushes a synthesized sentence chunk into the playback queue."""
        with self._lock:
            self._total_sentences = total
            self._queue.put((samples, sr, text, index, total))
            if self.state == STATE_IDLE:
                self._set_state(STATE_PLAYING)

    def mark_stream_end(self) -> None:
        """Notifies player that all chunks for the current job have been generated."""
        self._queue.put(None)

    def pause(self) -> None:
        with self._lock:
            if self.state == STATE_PLAYING:
                self._pause_requested.set()
                if self._stream and self._stream.active:
                    try:
                        self._stream.stop()
                    except Exception:
                        pass
                self._set_state(STATE_PAUSED)

    def resume(self) -> None:
        with self._lock:
            if self.state == STATE_PAUSED:
                self._pause_requested.clear()
                if self._stream:
                    try:
                        self._stream.start()
                    except Exception:
                        pass
                self._set_state(STATE_PLAYING)

    def toggle_pause(self) -> None:
        if self.state == STATE_PLAYING:
            self.pause()
        elif self.state == STATE_PAUSED:
            self.resume()

    def skip(self) -> None:
        """Skips current speaking sentence immediately to the next one."""
        with self._lock:
            self._skip_requested.set()
            if self._stream and self._stream.active:
                try:
                    self._stream.stop()
                except Exception:
                    pass

    def stop(self) -> None:
        """Immediately halts all speech and empties the playback queue."""
        with self._lock:
            self._stop_requested.set()
            if self._stream and self._stream.active:
                try:
                    self._stream.stop()
                except Exception:
                    pass

            # Empty queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break

            self._current_samples = None
            self._current_pos = 0
            self._current_text = ""
            self._current_index = 0
            self._total_sentences = 0
            self._pause_requested.clear()
            self._skip_requested.clear()
            self._set_state(STATE_IDLE)

    def get_status(self) -> dict:
        with self._lock:
            return {
                "state": self.state,
                "current_sentence": self._current_index,
                "total_sentences": self._total_sentences,
                "current_text": self._current_text,
                "queue_size": self._queue.qsize(),
            }

    def _audio_callback(self, outdata, frames, time_info, status):
        with self._lock:
            if self._pause_requested.is_set() or self._stop_requested.is_set() or self._current_samples is None:
                outdata.fill(0)
                return

            remaining = len(self._current_samples) - self._current_pos
            if remaining <= 0:
                outdata.fill(0)
                return

            if remaining < frames:
                chunk = self._current_samples[self._current_pos:]
                outdata[:remaining, 0] = chunk
                outdata[remaining:, 0] = 0
                self._current_pos = len(self._current_samples)
            else:
                outdata[:, 0] = self._current_samples[self._current_pos:self._current_pos + frames]
                self._current_pos += frames

    def _run_loop(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self.state == STATE_PLAYING and (self._current_samples is None or self._current_pos >= len(self._current_samples)):
                    self._set_state(STATE_IDLE)
                continue

            if item is None:
                # End of stream sentinel
                self._queue.task_done()
                with self._lock:
                    if self._queue.empty() and (self._current_samples is None or self._current_pos >= len(self._current_samples)):
                        self._set_state(STATE_IDLE)
                continue

            samples, sr, text, index, total = item
            self._stop_requested.clear()
            self._skip_requested.clear()

            with self._lock:
                self._current_samples = samples.astype(np.float32)
                self._current_pos = 0
                self._current_sr = sr
                self._current_text = text
                self._current_index = index
                self._total_sentences = total
                self._set_state(STATE_PLAYING)

            if self.on_sentence_change:
                try:
                    self.on_sentence_change(index, total, text)
                except Exception as e:
                    print(f"[Player] Sentence callback error: {e}")

            # Initialize or recreate stream if sample rate changed
            try:
                if self._stream is None or self._stream.samplerate != sr:
                    if self._stream:
                        self._stream.close()
                    self._stream = sd.OutputStream(
                        samplerate=sr,
                        channels=1,
                        callback=self._audio_callback,
                        blocksize=1024,
                    )

                self._stream.start()

                # Wait for sentence to finish playing or be interrupted
                while True:
                    if self._stop_requested.is_set():
                        break

                    if self._skip_requested.is_set():
                        self._skip_requested.clear()
                        break

                    if self._pause_requested.is_set():
                        time.sleep(0.05)
                        continue

                    with self._lock:
                        if self._current_samples is not None and self._current_pos >= len(self._current_samples):
                            break

                    time.sleep(0.02)

                # Sentence finished or skipped
                if self._stream and self._stream.active and not self._pause_requested.is_set():
                    self._stream.stop()

                # Add natural inter-sentence pause (e.g. 150ms)
                if not self._stop_requested.is_set() and not self._skip_requested.is_set():
                    time.sleep(0.15)

            except Exception as e:
                print(f"[Player] Audio output error: {e}")
            finally:
                self._queue.task_done()
