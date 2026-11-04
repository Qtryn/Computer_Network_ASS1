"""Shared client application. Member 4 can call these methods without touching sockets."""
import json
import socket
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
                 udp_port=UDP_PORT, key=None, download_dir=None):
        if key is None:
            raise ValueError("Client requires a shared AES key")
        self.username = username
        self.online = []
        self.online_version = -1
        self.events = deque(maxlen=500)
        self.event_id = 0
        self.event_lock = threading.Lock()
        self.file_lock = threading.Lock()
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
            self.server_udp = (self.tcp.getpeername()[0], udp_port)
            login = {"type": "LOGIN", "username": username, "udp_port": self.udp.port}
            self.tcp.sendall((json.dumps(login) + "\n").encode("utf-8"))
            response = self._read_control_line()
            if response.get("type") != "LOGIN_OK":
                raise ValueError(response.get("message", "Login rejected"))
            self.token = response["token"]
            self.online = response["users"]
            self.online_version = response.get("version", 0)
            self.server_udp = (self.server_udp[0], response["udp_port"])
        except Exception:
            self.tcp.close()
            self.udp.close()
            raise
        self.tcp.settimeout(None)
        self._emit({"type": "INFO", "message": f"Logged in as {username}"})
        self.heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def _read_control_line(self):
        raw = b""
        while not raw.endswith(b"\n"):
            part = self.tcp.recv(4096)
            if not part:
                raise ConnectionError("Server closed the connection before login")
            raw += part
            if len(raw) > 8192:
                raise ValueError("Oversized login response")
        return json.loads(raw)

    def _heartbeat(self):
        while self.running.is_set():
            try:
                self.tcp.sendall(b'{"type":"PING"}\n')
            except OSError:
                self._emit({"type": "ERROR", "message": "TCP control channel disconnected"})
                self.running.clear()
                return
            # Event.wait would return immediately if set; sleep instead.
            time.sleep(3)

    def _emit(self, event):
        with self.event_lock:
            self.event_id += 1
            self.events.append({"id": self.event_id, **event})

    def get_state(self, after_id=0):
        with self.event_lock:
            result = [event.copy() for event in self.events if event["id"] > after_id]
            return {"username": self.username, "online": list(self.online),
                    "connected": self.running.is_set(), "events": result,
                    "last_id": self.event_id}

    def send_chat(self, recipient, text):
        event = ChatService.build_message(self.username, recipient, text)
        self.udp.send(self.server_udp, {**event, "token": self.token}, CHAT_STREAM)
        self._emit({**event, "outgoing": True})

    def send_file(self, path, recipient, display_name=None):
        """Blocking transfer; call in a background thread from HTTP/UI."""
        file_id, packet_count, packets = self.file_sender.prepare(
            path, self.username, recipient, display_name=display_name)
        stream = uuid.UUID(file_id)
        self._emit({"type": "UPLOAD_PROGRESS", "file_id": file_id, "percent": 0})

        def authenticated_packets():
            for message in packets:
                yield {**message, "token": self.token}

        def progress(acked):
            self._emit({"type": "UPLOAD_PROGRESS", "file_id": file_id,
                        "percent": round(100 * acked / packet_count)})

        self.udp.send_many(self.server_udp, authenticated_packets(), stream, progress)
        self._emit({"type": "UPLOAD_SENT", "file_id": file_id,
                    "message": "All chunks acknowledged by server; awaiting receiver receipt"})
        return file_id

    def _on_udp_message(self, peer, stream, message):
        if peer != self.server_udp:
            return
        kind = message.get("type")
        if kind == "USERS":
            with self.event_lock:
                version = message.get("version", -1)
                if version < self.online_version:
                    return  # Ignore stale roster pushed from overlapping login threads.
                self.online_version = version
                self.online = sorted(message.get("users", []))
            self._emit({"type": "USERS", "users": list(self.online)})
        elif kind in ("CHAT", "ERROR", "FILE_RECEIPT"):
            self._emit(message)
        elif kind in ("FILE_START", "FILE_CHUNK", "FILE_END"):
            file_id = message.get("file_id")
            try:
                with self.file_lock:
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

    def close(self):
        if not self.running.is_set():
            # Still clean up when heartbeat detected lost control channel.
            pass
        self.running.clear()
        try:
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
