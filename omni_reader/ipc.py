"""Zero-latency Unix Domain Socket IPC for OmniReader."""

import json
import os
import socket
import threading
from typing import Any, Callable, Dict, Optional


class DaemonNotRunningError(Exception):
    pass


class IPCServer:
    def __init__(self, socket_path: str, command_handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.socket_path = socket_path
        self.command_handler = command_handler
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self.socket_path)
        # Permissions: only current user can read/write
        os.chmod(self.socket_path, 0o600)
        self._server_sock.listen(10)
        self._running = True

        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="OmniIPCServer")
        self._thread.start()

    def _listen_loop(self) -> None:
        while self._running and self._server_sock:
            try:
                conn, _ = self._server_sock.accept()
            except OSError:
                break

            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            raw_data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw_data += chunk
                if b"\n" in chunk:
                    break

            if raw_data:
                try:
                    payload = json.loads(raw_data.decode("utf-8").strip())
                    response = self.command_handler(payload)
                except Exception as e:
                    response = {"status": "error", "message": str(e)}

                conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
        except Exception:
            pass
        finally:
            conn.close()

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass


class IPCClient:
    def __init__(self, socket_path: str = "/tmp/omni_reader.sock"):
        self.socket_path = socket_path

    def is_running(self) -> bool:
        if not os.path.exists(self.socket_path):
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(self.socket_path)
            s.close()
            return True
        except Exception:
            return False

    def send_command(self, action: str, timeout: float = 2.0, **kwargs) -> Dict[str, Any]:
        if not os.path.exists(self.socket_path):
            raise DaemonNotRunningError("OmniReader daemon is not running.")

        payload = {"action": action, **kwargs}
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(self.socket_path)
            s.sendall(json.dumps(payload).encode("utf-8") + b"\n")

            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break

            if not data:
                return {"status": "error", "message": "Empty response from daemon"}

            return json.loads(data.decode("utf-8").strip())
        except ConnectionRefusedError:
            raise DaemonNotRunningError("Daemon socket refused connection.")
        finally:
            s.close()
