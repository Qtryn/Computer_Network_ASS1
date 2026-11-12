"""Shared client application. Member 4 can call these methods without touching sockets."""
import json
import select
import socket
import ssl
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from app.common.config import TCP_PORT, UDP_PORT
from app.transport.reliable_udp import CHAT_STREAM, ReliableUDP
from app.features.chat import ChatService
from app.features.files import FileReceiver, FileSender


class CollaborationClient:
    def __init__(self, username, server_host="127.0.0.1", tcp_port=TCP_PORT,
                 udp_port=UDP_PORT, key=None, download_dir=None, *, password=None,
                 tls_context=None, server_hostname=None):
        if key is None:
            raise ValueError("Client requires a shared AES key")
        if password is not None and tls_context is None:
            raise ValueError("Password login requires verified TLS")
        if tls_context is not None and (not tls_context.check_hostname or
                                       tls_context.verify_mode != ssl.CERT_REQUIRED):
            raise ValueError("TLS must verify the server certificate and hostname")
        self.username = username
        self.online = []
        self.online_version = -1
        self.events = deque(maxlen=500)
        self.event_id = 0
        self.event_lock = threading.Lock()
        self.file_lock = threading.Lock()
        self.close_lock = threading.Lock()
        self.control_lock = threading.Lock()
        self.closed = False
        self.disconnect_reason = ""
        self.token = None
        self.session_id = uuid.uuid4().hex
        self.control_buffer = b""
        self.running = threading.Event()
        self.running.set()
        download_dir = download_dir or Path("downloads") / username
        self.file_receiver = FileReceiver(download_dir)
        self.file_sender = FileSender()
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.settimeout(4)
        self.udp = ReliableUDP("0.0.0.0", 0, key, self._on_udp_message)
        try:
            self.tcp.connect((server_host, tcp_port))
            if tls_context is not None:
                self.tcp = tls_context.wrap_socket(
                    self.tcp, server_hostname=server_hostname or server_host)
            self.server_udp = (self.tcp.getpeername()[0], udp_port)
            self.tcp.sendall(b'{"type":"HELLO","version":1}\n')
            if self._read_control_line().get("type") != "HELLO_OK":
                raise ValueError("Server rejected protocol version")
            login = {"type": "LOGIN", "username": username, "udp_port": self.udp.port}
            if password is not None:
                login["password"] = password
            self.tcp.sendall((json.dumps(login) + "\n").encode("utf-8"))
            response = self._read_control_line()
            if response.get("type") != "LOGIN_OK":
                reason = response.get("message") or {
                    "LOGIN_FAIL": "Invalid username or password",
                    "LOGIN_LOCKED": "Account temporarily locked; try again later",
                }.get(response.get("type"), "Login rejected")
                raise ValueError(reason)
            self.token = response["token"]
            self.online = response["users"]
            self.online_version = response.get("version", 0)
            self.server_udp = (self.server_udp[0], response["udp_port"])
        except Exception:
            self.tcp.close()
            self.udp.close()
            raise
        self.tcp.settimeout(1)
        self._emit({"type": "INFO", "message": f"Logged in as {username}"})
        self.heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def _read_control_line(self):
        while b"\n" not in self.control_buffer:
            part = self.tcp.recv(4096)
            if not part:
                raise ConnectionError("Server closed the connection before login")
            self.control_buffer += part
            if len(self.control_buffer) > 8192:
                raise ValueError("Oversized login response")
        raw, self.control_buffer = self.control_buffer.split(b"\n", 1)
        message = json.loads(raw)
        if not isinstance(message, dict):
            raise ValueError("Invalid control response")
        return message

    def _heartbeat(self):
        """One owner for SSL reads/writes; close uses the same control lock."""
        next_ping = 0
        while self.running.is_set():
            try:
                now = time.monotonic()
                if now >= next_ping:
                    with self.control_lock:
                        if not self.running.is_set():
                            return
                        self.tcp.sendall(b'{"type":"PING"}\n')
                    next_ping = now + 3
                    with self.file_lock:
                        expired = self.file_receiver.cleanup_expired()
                    for file_id in expired:
                        self._emit({"type": "ERROR", "message": f"File {file_id}: transfer timed out"})
                with self.control_lock:
                    if not self.running.is_set():
                        return
                    # TLS can have decrypted bytes when the OS socket is idle.
                    pending = isinstance(self.tcp, ssl.SSLSocket) and self.tcp.pending()
                    if not pending and not self.control_buffer and not select.select([self.tcp], [], [], 0.2)[0]:
                        continue
                    message = self._read_control_line()
                if message.get("type") == "AUTH_REQUIRED":
                    raise ConnectionError("Session expired; log in again")
            except socket.timeout:
                continue
            except (OSError, ValueError, ConnectionError) as exc:
                self.close(f"TCP control channel disconnected: {exc}")
                return

    def _emit(self, event):
        with self.event_lock:
            if not self.running.is_set():
                return
            self.event_id += 1
            self.events.append({"id": self.event_id, **event})

    def get_state(self, after_id=0):
        with self.event_lock:
            connected = self.running.is_set()
            result = [event.copy() for event in self.events if event["id"] > after_id] if connected else []
            return {"username": self.username, "online": list(self.online) if connected else [],
                    "connected": connected, "events": result,
                    "last_id": self.event_id if connected else 0, "session_id": self.session_id,
                    "disconnect_reason": self.disconnect_reason}

    def _require_connected(self):
        if not self.running.is_set() or not self.token:
            raise ConnectionError("Logged out or disconnected; log in again")

    def send_chat(self, recipient, text):
        self._require_connected()
        event = ChatService.build_message(self.username, recipient, text)
        self.udp.send(self.server_udp, {**event, "token": self.token}, CHAT_STREAM)
        self._emit({**event, "outgoing": True, "delivery": "server_acknowledged"})

    def send_file(self, path, recipient, display_name=None):
        """Blocking transfer; call in a background thread from HTTP/UI."""
        self._require_connected()
        file_id, packet_count, packets = self.file_sender.prepare(
            path, self.username, recipient, display_name=display_name)
        stream = uuid.UUID(file_id)
        self._emit({"type": "UPLOAD_PROGRESS", "file_id": file_id, "percent": 0})

        def authenticated_packets():
            for message in packets:
                self._require_connected()
                yield {**message, "token": self.token}

        def progress(acked):
            self._emit({"type": "UPLOAD_PROGRESS", "file_id": file_id,
                        "percent": round(100 * acked / packet_count)})

        self.udp.send_many(self.server_udp, authenticated_packets(), stream, progress)
        self._emit({"type": "UPLOAD_SENT", "file_id": file_id,
                    "message": "All chunks acknowledged by server; awaiting receiver receipt"})
        return file_id

    def _on_udp_message(self, peer, stream, message):
        if not self.running.is_set() or peer != self.server_udp:
            return
        kind = message.get("type")
        if kind == "USERS":
            with self.event_lock:
                if not self.running.is_set():
                    return
                version = message.get("version", -1)
                if version < self.online_version:
                    return  # Ignore stale roster pushed from overlapping login threads.
                self.online_version = version
                self.online = sorted(message.get("users", []))
            self._emit({"type": "USERS", "users": list(self.online)})
        elif kind == "FILE_ABORT":
            with self.file_lock:
                self.file_receiver.abort(message.get("file_id"))
            self._emit({"type": "ERROR", "message": message.get("message", "File transfer aborted")})
        elif kind in ("CHAT", "ERROR", "FILE_RECEIPT", "CHAT_RECEIPT"):
            self._emit(message)
        elif kind in ("FILE_START", "FILE_CHUNK", "FILE_END"):
            file_id = message.get("file_id")
            try:
                with self.file_lock:
                    if not self.running.is_set():
                        return
                    result = self.file_receiver.process(message)
                if result:
                    self._emit(result)
                    if result["type"] == "FILE_COMPLETE":
                        self._send_file_receipt(file_id, "ok", "SHA-256 verified")
            except Exception as exc:
                self._emit({"type": "ERROR", "message": f"File {file_id}: {exc}"})
                self._send_file_receipt(file_id, "error", str(exc))

    def _send_file_receipt(self, file_id, status, message):
        event = {"type": "FILE_RECEIPT", "file_id": file_id, "sender": self.username,
                 "token": self.token, "status": status, "message": message}
        try:
            self.udp.send(self.server_udp, event, uuid.UUID(file_id))
        except (ValueError, OSError, TimeoutError, ConnectionError) as exc:
            self._emit({"type": "ERROR", "message": f"Could not send receipt: {exc}"})

    def close(self, reason="Logged out"):
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
            self.disconnect_reason = reason
            self.running.clear()
        try:
            with self.control_lock:
                self.tcp.sendall(b'{"type":"LOGOUT"}\n')
        except OSError:
            pass
        try:
            self.tcp.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.tcp.close()
        self.udp.close()
        with self.file_lock:
            self.file_receiver.close()
        with self.event_lock:
            self.events.clear()
            self.event_id = 0
            self.online = []
            self.online_version = -1
            self.token = None
        worker = getattr(self, "heartbeat_thread", None)
        if worker and worker is not threading.current_thread():
            worker.join(timeout=1)
