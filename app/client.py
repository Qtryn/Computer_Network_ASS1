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
from app.common.protocol import session_stream
from app.transport.reliable_udp import CHAT_STREAM, ReliableUDP
from app.features.chat import ChatService
from app.features.files import FileReceiver, FileSender
from app.features.outbox import ChatState

def register_account(username, password, server_host="127.0.0.1", tcp_port=TCP_PORT,
                     *, tls_context=None, server_hostname=None):
    """Short-lived verified TLS control connection; never retain credentials."""
    if tls_context is None or not tls_context.check_hostname or tls_context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError("Registration requires verified TLS")
    request = json.dumps({"type": "REGISTER", "username": username, "password": password}).encode() + b"\n"
    if len(request) > 4096:
        raise ValueError("Registration request too large")
    with socket.create_connection((server_host, tcp_port), timeout=4) as raw:
        with tls_context.wrap_socket(raw, server_hostname=server_hostname or server_host) as connection:
            with connection.makefile("rb") as stream:
                connection.sendall(b'{"type":"HELLO","version":1}\n')
                if json.loads(stream.readline(8193)).get("type") != "HELLO_OK":
                    raise ValueError("Server rejected protocol version")
                connection.sendall(request)
                response = json.loads(stream.readline(8193))
                if response.get("type") != "REGISTER_OK":
                    raise ValueError(response.get("message", "Registration rejected"))


class CollaborationClient:
    def __init__(self, username, server_host="127.0.0.1", tcp_port=TCP_PORT,
                 udp_port=UDP_PORT, key=None, download_dir=None, *, password=None,
                 tls_context=None, server_hostname=None, chat_state=None):
        if key is None:
            raise ValueError("Client requires a shared AES key")
        if password is not None and tls_context is None:
            raise ValueError("Password login requires verified TLS")
        if tls_context is not None and (not tls_context.check_hostname or
                                       tls_context.verify_mode != ssl.CERT_REQUIRED):
            raise ValueError("TLS must verify the server certificate and hostname")
        self.username = username
        self.chat_state = chat_state or ChatState(username)
        if self.chat_state.username != username:
            raise ValueError("Outbox belongs to another account")
        self.chat_send_lock = threading.Lock()
        self.outbox_wakeup = threading.Event()
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
        self.disconnect_kind = None
        self.token = None
        self.chat_stream = None
        self.chat_ack_stream = None
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
            self.chat_stream = session_stream(self.token)
            if response.get("chat_stream") != str(self.chat_stream):
                raise ValueError("Server lacks session-scoped chat; update server and client together")
            self.chat_ack_stream = session_stream(self.token, "ack")
            self.online = response["users"]
            self.online_version = response.get("version", 0)
            self.server_udp = (self.server_udp[0], response["udp_port"])
            self.tcp.sendall(b'{"type":"GET_USERS"}\n')
        except Exception:
            self.tcp.close()
            self.udp.close()
            raise
        self.tcp.settimeout(1)
        self._emit({"type": "INFO", "message": f"Logged in as {username}"})
        self.heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.heartbeat_thread.start()
        self.outbox_thread = threading.Thread(target=self._outbox_loop, daemon=True)
        self.outbox_thread.start()
        if self.chat_state.pending():
            self.outbox_wakeup.set()

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
                    self.close("Session expired; log in again", kind="expired")
                    return
                if message.get("type") == "USERS":
                    self._on_udp_message(self.server_udp, self.chat_stream, message)
            except socket.timeout:
                continue
            except (OSError, ValueError, ConnectionError) as exc:
                self.close(f"TCP control channel disconnected: {exc}", kind="network")
                return

    def _emit(self, event):
        with self.event_lock:
            if not self.running.is_set():
                return
            self.event_id += 1
            emitted = {"id": self.event_id, **event}
            self.events.append(emitted)
            return emitted.copy()

    def get_state(self, after_id=0):
        with self.event_lock:
            connected = self.running.is_set()
            result = [event.copy() for event in self.events if event["id"] > after_id] if connected else []
            return {"username": self.username, "online": list(self.online) if connected else [],
                    "connected": connected, "events": result,
                    "last_id": self.event_id if connected else 0, "session_id": self.session_id,
                    "disconnect_reason": self.disconnect_reason,
                    "disconnect_kind": self.disconnect_kind,
                    "outbox": self.chat_state.pending() if connected else []}

    def _require_connected(self):
        if not self.running.is_set() or not self.token:
            raise ConnectionError("Logged out or disconnected; log in again")

    def send_chat(self, recipient, text):
        self._require_connected()
        targets = [name for name in self.online if name != self.username] if recipient == "*" else [recipient]
        if not targets:
            raise ValueError("No online recipients for broadcast")
        event = ChatService.build_message(self.username, recipient, text,
                                         message_id=str(uuid.uuid4()), targets=targets)
        self.chat_state.enqueue(event)
        self._emit({**event, "outgoing": True, "delivery": "PENDING"})
        self._send_oldest_chat()

    def _send_oldest_chat(self):
        with self.chat_send_lock:
            self._require_connected()
            pending = self.chat_state.pending()
            if not pending:
                return
            event = pending[0]
            message_id = event["message_id"]
            if not self.chat_state.status(message_id, "SENDING"):
                return
            self._emit({"type": "CHAT_STATUS", "message_id": message_id, "status": "SENDING"})
            try:
                packet = {key: value for key, value in event.items() if key != "status"}
                self.udp.send(self.server_udp, {**packet, "token": self.token}, self.chat_stream)
            except (ValueError, OSError, TimeoutError, ConnectionError):
                self.chat_state.status(message_id, "PENDING")
                self._emit({"type": "CHAT_STATUS", "message_id": message_id, "status": "PENDING"})
                raise

    def _outbox_loop(self):
        delay = 1
        while self.running.is_set():
            self.outbox_wakeup.wait(delay)
            self.outbox_wakeup.clear()
            if not self.running.is_set():
                return
            if not self.chat_state.pending():
                delay = 1
                continue
            try:
                self._send_oldest_chat()
            except (ValueError, OSError, TimeoutError, ConnectionError):
                pass  # Remains PENDING; UI shows outbox and retry is bounded.
            delay = min(delay * 2, 8)

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
        if not self.running.is_set() or not self.token or peer != self.server_udp:
            return
        kind = message.get("type")
        if kind in ("USERS", "CHAT", "CHAT_RECEIPT", "CHAT_STATUS", "ERROR", "FILE_RECEIPT"):
            if stream != getattr(self, "chat_stream", stream):
                return  # Late control/chat datagram from a previous login.
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
        elif kind == "CHAT":
            message_id = message.get("message_id")
            if message_id:
                uuid.UUID(message_id)
                duplicate = self.chat_state.already_received(message)
                if not duplicate:
                    if message.get("sender") != self.username and self._emit(message) is None:
                        return
                    self.chat_state.remember(message)
                self.udp.send(self.server_udp, {
                    "type": "CHAT_ACK", "sender": self.username, "token": self.token,
                    "original_sender": message["sender"], "message_id": message_id,
                }, self.chat_ack_stream)
            elif message.get("sender") != self.username:
                self._emit(message)  # Legacy peer; no application delivery promise.
        elif kind == "CHAT_RECEIPT":
            message_id = message.get("message_id")
            if not message_id:
                self._emit(message)
            elif message.get("status") in ("PENDING", "DELIVERED"):
                # Serialize status events with sends; an early application ACK
                # must not be followed by a stale SENDING event.
                with self.chat_send_lock:
                    if self.chat_state.status(message_id, message["status"]):
                        if message["status"] == "DELIVERED":
                            self.outbox_wakeup.set()
                        self._emit(message)
        elif kind in ("ERROR", "FILE_RECEIPT"):
            self._emit(message)
        elif kind in ("FILE_START", "FILE_CHUNK", "FILE_END"):
            if message.get("recipient") != self.username:
                return
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

    def close(self, reason="Logged out", *, kind="logout"):
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
            self.disconnect_reason = reason
            self.disconnect_kind = kind
            self.running.clear()
            self.chat_state.reset_sending()
            self.outbox_wakeup.set()
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
        worker = getattr(self, "outbox_thread", None)
        if worker and worker is not threading.current_thread():
            worker.join(timeout=1)
