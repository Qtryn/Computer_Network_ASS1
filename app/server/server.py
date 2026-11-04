"""Member 1: minimal server combining a TCP control channel and UDP data routing.

TCP = handshake/login/heartbeat. UDP = chat/file payloads via Member 2.
The server does not store user files or decrypt them to disk; it relays chunks.
"""
import json
import socket
import threading
import time
import uuid

from app.server.registry import UserRegistry
from app.transport.reliable_udp import CHAT_STREAM, ReliableUDP
from app.features.chat import ChatService

FILE_TYPES = {"FILE_START", "FILE_CHUNK", "FILE_END"}


class CollaborationServer:
    def __init__(self, host, tcp_port, udp_port, key):
        self.host = host
        self.registry = UserRegistry()
        self.running = threading.Event()
        self.running.set()
        self.transfer_lock = threading.Lock()
        self.transfers = {}  # file_id -> (original sender, receiving username)
        self.udp = ReliableUDP(host, udp_port, key, self._handle_udp)
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp.bind((host, tcp_port))
        self.tcp.listen(32)
        self.tcp.settimeout(0.3)
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()
        print(f"[server] TCP {self.tcp.getsockname()} | UDP {host}:{self.udp.port}")

    @property
    def tcp_port(self):
        return self.tcp.getsockname()[1]

    @property
    def udp_port(self):
        return self.udp.port

    def _accept_loop(self):
        while self.running.is_set():
            try:
                connection, address = self.tcp.accept()
                threading.Thread(target=self._handle_connection,
                                 args=(connection, address), daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                return

    @staticmethod
    def _send_control(connection, data):
        connection.sendall((json.dumps(data, separators=(",", ":")) + "\n").encode("utf-8"))

    def _handle_connection(self, connection, address):
        session = None
        try:
            connection.settimeout(1.0)
            raw = b""
            last_seen = time.monotonic()
            while self.running.is_set():
                try:
                    block = connection.recv(4096)
                except socket.timeout:
                    if time.monotonic() - last_seen > 12:
                        break  # Client likely crashed or lost network.
                    continue
                if not block:
                    break
                last_seen = time.monotonic()
                raw += block
                if len(raw) > 8192:
                    raise ValueError("Control message too long")
                while b"\n" in raw:
                    line, raw = raw.split(b"\n", 1)
                    if not line:
                        continue
                    incoming = json.loads(line)
                    if session is None:
                        if incoming.get("type") != "LOGIN":
                            raise ValueError("LOGIN is required first")
                        session = self.registry.login(incoming.get("username"), address[0],
                                                      incoming.get("udp_port"), connection)
                        revision, names = self.registry.snapshot()
                        self._send_control(connection, {"type": "LOGIN_OK", "token": session.token,
                                                        "users": names, "version": revision,
                                                        "udp_port": self.udp.port})
                        self._publish_users()
                        print(f"[server] {session.username} logged in from {session.udp_addr}")
                    elif incoming.get("type") == "LOGOUT":
                        return
                    elif incoming.get("type") != "PING":
                        self._send_control(connection, {"type": "ERROR", "message": "Unknown control command"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            try:
                self._send_control(connection, {"type": "ERROR", "message": str(exc)})
            except OSError:
                pass
        except OSError:
            pass
        finally:
            try:
                connection.close()
            except OSError:
                pass
            if session and self.registry.logout(session.username, session.token):
                print(f"[server] {session.username} disconnected")
                self._publish_users()

    def _publish_users(self):
        revision, online = self.registry.snapshot()
        for session in self.registry.all_sessions():
            try:
                self.udp.send(session.udp_addr, {"type": "USERS", "users": online,
                                                      "version": revision}, CHAT_STREAM)
            except (TimeoutError, OSError, ConnectionError):
                pass

    def _send_error(self, username, message):
        session = self.registry.get(username)
        if session:
            try:
                self.udp.send(session.udp_addr,
                              {"type": "ERROR", "message": str(message)}, CHAT_STREAM)
            except (TimeoutError, OSError, ConnectionError):
                pass

    def _forward(self, recipient, stream, message):
        session = self.registry.get(recipient)
        if not session:
            raise ValueError(f"User '{recipient}' is offline")
        self.udp.send(session.udp_addr, message, stream)

    def _handle_udp(self, peer, stream, message):
        kind = message.get("type")
        username = message.get("sender")
        session = self.registry.authenticate(username, message.get("token"), peer)
        if not session:
            return  # Ignore UDP datagrams from unknown/unauthenticated sessions.
        try:
            if kind == "CHAT":
                recipients = ChatService.recipients(username, message.get("recipient"),
                                                    self.registry.names())
                clean = ChatService.build_message(username, message["recipient"], message["text"])
                for dest in recipients:
                    self._forward(dest, CHAT_STREAM, clean)
            elif kind in FILE_TYPES:
                file_id = str(message.get("file_id", ""))
                stream_id = uuid.UUID(file_id)
                if stream != stream_id:
                    raise ValueError("File transfer stream ID mismatch")
                with self.transfer_lock:
                    if kind == "FILE_START":
                        target = message.get("recipient")
                        if target == username or not self.registry.get(target):
                            raise ValueError("File recipient must be a different online user")
                        if file_id in self.transfers:
                            raise ValueError("Duplicate transfer ID")
                        self.transfers[file_id] = (username, target)
                    transfer = self.transfers.get(file_id)
                    if not transfer or transfer[0] != username:
                        raise ValueError("Unknown file transfer")
                    target = transfer[1]
                clean = {key: value for key, value in message.items() if key != "token"}
                self._forward(target, stream_id, clean)
                # Keep transfer until receiver sends its final FILE_RECEIPT.
            elif kind == "FILE_RECEIPT":
                file_id = str(message.get("file_id", ""))
                with self.transfer_lock:
                    transfer = self.transfers.get(file_id)
                    if not transfer or transfer[1] != username:
                        raise ValueError("Invalid file receipt")
                    sender = transfer[0]
                    del self.transfers[file_id]
                self._forward(sender, CHAT_STREAM, {
                    "type": "FILE_RECEIPT", "file_id": file_id,
                    "sender": username, "status": message.get("status", "error"),
                    "message": message.get("message", "")})
            else:
                raise ValueError(f"Unknown application event: {kind}")
        except (ValueError, KeyError, TypeError, TimeoutError, OSError) as exc:
            self._send_error(username, exc)

    def close(self):
        self.running.clear()
        self.tcp.close()
        for session in self.registry.all_sessions():
            try:
                session.control_socket.shutdown(socket.SHUT_RDWR)
                session.control_socket.close()
            except OSError:
                pass
        self.udp.close()
        self.accept_thread.join(timeout=1.0)
