"""Member 1: minimal server combining a TCP control channel and UDP data routing.

TCP = handshake/login/heartbeat. UDP = chat/file payloads via Member 2.
The server does not store user files or decrypt them to disk; it relays chunks.
"""
import json
import math
import socket
import threading
import time
import uuid
from collections import OrderedDict

from app.common.config import PROTOCOL_VERSION
from app.common.protocol import session_stream
from app.server.auth import USERNAME
from app.server.registry import UserRegistry
from app.transport.reliable_udp import CHAT_STREAM, ReliableUDP
from app.features.chat import ChatService
from app.features.outbox import chat_digest

FILE_TYPES = {"FILE_START", "FILE_CHUNK", "FILE_END"}
MAX_CONTROL_LINE = 4096
MAX_CONNECTIONS = 64
CONTROL_IDLE_SECONDS = 12


class CollaborationServer:
    def __init__(self, host, tcp_port, udp_port, key, *, accounts=None,
                 tls_context=None, session_seconds=3600, clock=time.monotonic,
                 transfer_timeout=60):
        if (accounts is None) != (tls_context is None):
            raise ValueError("Password accounts and a server TLS context are required together")
        self.host = host
        self.accounts = accounts
        self.tls_context = tls_context
        self.clock = clock
        self.registry = UserRegistry(session_seconds=session_seconds, clock=clock)
        self.running = threading.Event()
        self.running.set()
        self.connections_lock = threading.Lock()
        self.connections = {}  # worker thread -> current socket, including pre-login
        self.roster_changed = threading.Event()
        self.transfer_lock = threading.Lock()
        self.transfers = {}  # file_id -> (original sender, receiving username)
        self.transfer_activity = {}
        self.transfer_sessions = {}
        self.transfer_timeout = transfer_timeout
        self.chat_lock = threading.Lock()
        self.chat_deliveries = OrderedDict()  # (sender, message_id) -> routing/ACK state
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp.bind((host, tcp_port))
            self.tcp.listen(32)
            self.tcp.settimeout(0.3)
            self.udp = ReliableUDP(host, udp_port, key, self._handle_udp)
        except Exception:
            self.tcp.close()
            raise
        self.roster_thread = threading.Thread(target=self._roster_loop, daemon=True)
        self.roster_thread.start()
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
            except socket.timeout:
                continue
            except OSError:
                return
            with self.connections_lock:
                if not self.running.is_set() or len(self.connections) >= MAX_CONNECTIONS:
                    connection.close()
                    continue
                worker = threading.Thread(target=self._handle_connection,
                                          args=(connection, address), daemon=True)
                self.connections[worker] = connection
                worker.start()

    @staticmethod
    def _send_control(connection, data):
        connection.sendall((json.dumps(data, separators=(",", ":")) + "\n").encode("utf-8"))

    def _handle_connection(self, connection, address):
        worker = threading.current_thread()
        try:
            if self.tls_context is not None:
                with self.connections_lock:
                    if not self.running.is_set():
                        return
                    connection = self.tls_context.wrap_socket(
                        connection, server_side=True, do_handshake_on_connect=False)
                    self.connections[worker] = connection
                connection.settimeout(4.0)
                connection.do_handshake()
            connection.settimeout(1.0)
            self._serve_control(connection, address)
        except OSError:
            pass
        finally:
            connection.close()
            with self.connections_lock:
                self.connections.pop(worker, None)

    def _serve_control(self, connection, address):
        session = None
        hello_seen = False
        legacy = False
        raw = b""
        last_seen = time.monotonic()
        try:
            while self.running.is_set():
                if time.monotonic() - last_seen >= CONTROL_IDLE_SECONDS:
                    return
                if session is not None and self.clock() >= session.expires_at:
                    self.registry.logout(session.username, session.token)
                    self.roster_changed.set()
                    session = None
                    if legacy:
                        return

                end = raw.find(b"\n")
                if (end == -1 and len(raw) > MAX_CONTROL_LINE) or end > MAX_CONTROL_LINE:
                    raise ValueError("Control message too long")
                if end == -1:
                    try:
                        block = connection.recv(4096)
                    except socket.timeout:
                        continue
                    if not block:
                        return
                    raw += block
                    continue
                line, raw = raw[:end], raw[end + 1:]
                incoming = json.loads(line.decode("utf-8"))
                if not isinstance(incoming, dict) or not isinstance(incoming.get("type"), str):
                    raise ValueError("Expected a JSON object with a type")
                kind = incoming["type"]
                last_seen = time.monotonic()
                if not hello_seen and not legacy:
                    if kind == "HELLO":
                        version = incoming.get("version")
                        if type(version) is not int:
                            raise ValueError("HELLO requires an integer version")
                        if version != PROTOCOL_VERSION:
                            self._protocol_error(connection, "UNSUPPORTED_VERSION")
                            return
                        self._send_control(connection, {"type": "HELLO_OK", "version": PROTOCOL_VERSION})
                        hello_seen = True
                        continue
                    if kind != "LOGIN" or self.accounts is not None:
                        self._protocol_error(connection, "HELLO_REQUIRED")
                        continue
                    legacy = True

                if kind == "LOGOUT":
                    return
                if session is None:
                    if kind == "REGISTER":
                        try:
                            if self.accounts is None or self.tls_context is None:
                                raise ValueError("Registration requires TLS account mode")
                            self.accounts.register(incoming.get("username"), incoming.get("password"))
                            self._send_control(connection, {"type": "REGISTER_OK"})
                        except (ValueError, OSError) as exc:
                            self._send_control(connection, {"type": "ERROR", "message": str(exc)})
                        return
                    if kind != "LOGIN":
                        self._send_control(connection, {"type": "AUTH_REQUIRED"})
                        continue
                    try:
                        session = self._login(connection, address[0], incoming)
                    except ValueError as exc:
                        self._send_control(connection, {"type": "ERROR", "code": "LOGIN_REJECTED",
                                                        "message": str(exc)})
                        if legacy:
                            return
                        continue
                    if session is None:
                        continue
                    revision, names = self.registry.snapshot()
                    self._send_control(connection, {"type": "LOGIN_OK", "token": session.token,
                                                    "chat_stream": str(session.chat_stream),
                                                    "users": names, "version": revision,
                                                    "udp_port": self.udp.port,
                                                    "expires_in_seconds": math.ceil(max(
                                                        0, session.expires_at - self.clock()))})
                    self.roster_changed.set()
                    print(f"[server] {session.username} logged in from {session.udp_addr}")
                elif kind == "GET_USERS":
                    revision, names = self.registry.snapshot()
                    self._send_control(connection, {"type": "USERS", "users": names, "version": revision})
                elif kind != "PING":
                    self._protocol_error(connection, "UNEXPECTED_MESSAGE")
        except (ValueError, RecursionError):
            self._protocol_error(connection, "INVALID_MESSAGE")
        finally:
            if session and self.registry.logout(session.username, session.token):
                self.roster_changed.set()
                print(f"[server] {session.username} disconnected")

    def _protocol_error(self, connection, code):
        self._send_control(connection, {"type": "PROTOCOL_ERROR", "code": code})

    def _login(self, connection, ip, incoming):
        username = incoming.get("username")
        port = incoming.get("udp_port")
        if not isinstance(username, str) or not USERNAME.fullmatch(username):
            raise ValueError("Username: 1-20 letters, digits or underscores")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid UDP port")
        if self.accounts is None:
            if "password" in incoming:
                raise ValueError("Password login requires the TLS account mode")
        else:
            failure = self.accounts.verify(username, incoming.get("password"))
            if failure is not None:
                self._send_control(connection, failure)
                return None
        return self.registry.login(username, ip, port, connection)

    def _roster_loop(self):
        sent_revision = -1
        while self.running.is_set():
            self.roster_changed.wait(timeout=0.25)
            self.roster_changed.clear()
            if not self.running.is_set():
                return
            revision, online = self.registry.snapshot()
            self._cleanup_transfers()
            if revision != sent_revision:
                sent_revision = revision
                self._publish_users(revision, online)

    def _publish_users(self, revision, online):
        for session in self.registry.all_sessions():
            try:
                self.udp.send(session.udp_addr, {"type": "USERS", "users": online,
                                                      "version": revision}, session.chat_stream)
            except (TimeoutError, OSError, ConnectionError):
                pass

    def _send_error(self, username, message):
        session = self.registry.get(username)
        if session:
            try:
                self.udp.send(session.udp_addr,
                              {"type": "ERROR", "message": str(message)}, session.chat_stream)
            except (TimeoutError, OSError, ConnectionError):
                pass

    def _forward(self, recipient, stream, message):
        session = self.registry.get(recipient)
        if not session:
            raise ValueError(f"User '{recipient}' is offline")
        self.udp.send(session.udp_addr, message, session.chat_stream if stream == CHAT_STREAM else stream)

    def _transfer_stale(self, file_id, users):
        sessions = [self.registry.get(name) for name in users]
        return (any(session is None for session in sessions)
                or tuple(session.token for session in sessions) != self.transfer_sessions[file_id]
                or self.clock() - self.transfer_activity[file_id] >= self.transfer_timeout)

    def _abort_transfer(self, file_id, reason, stale_only=False):
        with self.transfer_lock:
            users = self.transfers.get(file_id)
            if stale_only and (not users or not self._transfer_stale(file_id, users)):
                return
            transfer = self.transfers.pop(file_id, None)
            self.transfer_activity.pop(file_id, None)
            tokens = self.transfer_sessions.pop(file_id, None)
        if transfer:
            for username, token in zip(transfer, tokens):
                session = self.registry.get(username)
                if session is None or session.token != token:
                    continue
                try:
                    self._forward(username, uuid.UUID(file_id), {
                        "type": "FILE_ABORT", "file_id": file_id, "message": reason})
                except (ValueError, TimeoutError, OSError, ConnectionError):
                    pass  # Offline peers also clean partial files locally.

    def _cleanup_transfers(self):
        with self.transfer_lock:
            expired = [file_id for file_id, users in self.transfers.items()
                       if self._transfer_stale(file_id, users)]
        for file_id in expired:
            self._abort_transfer(file_id, "File transfer interrupted or timed out", stale_only=True)

    def _handle_udp(self, peer, stream, message):
        kind = message.get("type")
        username = message.get("sender")
        session = self.registry.authenticate(username, message.get("token"), peer)
        if not session:
            return  # Ignore UDP datagrams from unknown/unauthenticated sessions.
        try:
            if kind == "CHAT":
                if message.get("message_id"):
                    if stream != session.chat_stream:
                        raise ValueError("Chat session stream mismatch")
                    self._route_chat(username, message)
                    return
                recipients = ChatService.recipients(username, message.get("recipient"),
                                                    self.registry.names())
                clean = ChatService.build_message(username, message["recipient"], message["text"])
                for dest in recipients:
                    self._forward(dest, CHAT_STREAM, clean)
                self._forward(username, CHAT_STREAM, {
                    "type": "CHAT_RECEIPT", "message": "Recipient transport acknowledged chat",
                    "recipients": recipients})
            elif kind == "CHAT_ACK":
                if stream != session_stream(session.token, "ack"):
                    raise ValueError("Chat ACK session stream mismatch")
                key = (message.get("original_sender"), message.get("message_id"))
                with self.chat_lock:
                    delivery = self.chat_deliveries.get(key)
                    if delivery is None or username not in delivery["targets"]:
                        raise ValueError("Invalid chat application acknowledgement")
                    delivery["acked"].add(username)
                self._chat_receipt(key)
            elif kind in FILE_TYPES:
                file_id = str(message.get("file_id", ""))
                stream_id = uuid.UUID(file_id)
                if stream != stream_id:
                    raise ValueError("File transfer stream ID mismatch")
                with self.transfer_lock:
                    if not self.registry.authenticate(username, message.get("token"), peer):
                        return
                    if kind == "FILE_START":
                        target = message.get("recipient")
                        target_session = self.registry.get(target)
                        if target == username or not target_session:
                            raise ValueError("File recipient must be a different online user")
                        if file_id in self.transfers:
                            raise ValueError("Duplicate transfer ID")
                        self.transfers[file_id] = (username, target)
                        self.transfer_sessions[file_id] = (session.token, target_session.token)
                        self.transfer_activity[file_id] = self.clock()
                    transfer = self.transfers.get(file_id)
                    if not transfer or transfer[0] != username:
                        raise ValueError("Unknown file transfer")
                    if self.transfer_sessions[file_id][0] != session.token:
                        raise ValueError("File sender session changed")
                    target = transfer[1]
                    self.transfer_activity[file_id] = self.clock()
                clean = {key: value for key, value in message.items() if key != "token"}
                self._forward(target, stream_id, clean)
                # Keep transfer until receiver sends its final FILE_RECEIPT.
            elif kind == "FILE_RECEIPT":
                file_id = str(message.get("file_id", ""))
                with self.transfer_lock:
                    transfer = self.transfers.get(file_id)
                    if not transfer or transfer[1] != username:
                        raise ValueError("Invalid file receipt")
                    if self.transfer_sessions[file_id][1] != session.token:
                        raise ValueError("File recipient session changed")
                    sender = transfer[0]
                    del self.transfers[file_id]
                    self.transfer_activity.pop(file_id, None)
                    self.transfer_sessions.pop(file_id, None)
                self._forward(sender, CHAT_STREAM, {
                    "type": "FILE_RECEIPT", "file_id": file_id,
                    "sender": username, "status": message.get("status", "error"),
                    "message": message.get("message", "")})
            else:
                raise ValueError(f"Unknown application event: {kind}")
        except (ValueError, KeyError, TypeError, TimeoutError, OSError) as exc:
            if kind in FILE_TYPES:
                file_id = str(message.get("file_id", ""))
                with self.transfer_lock:
                    owned = self.transfers.get(file_id, (None,))[0] == username
                if owned:
                    self._abort_transfer(file_id, f"File relay failed: {exc}")
            self._send_error(username, exc)

    def _chat_receipt(self, key):
        with self.chat_lock:
            delivery = self.chat_deliveries.get(key)
            if delivery is None:
                return
            targets = delivery["targets"]
            status = "DELIVERED" if set(targets) <= delivery["acked"] else "PENDING"
        try:
            self._forward(key[0], CHAT_STREAM, {
                "type": "CHAT_RECEIPT", "message_id": key[1], "status": status,
                "recipients": targets,
                "message": "Recipient application acknowledged" if status == "DELIVERED"
                           else "Waiting for recipient application acknowledgement"})
        except (ValueError, OSError, TimeoutError, ConnectionError):
            pass  # Sender replays its stable message ID after reconnecting.

    def _route_chat(self, username, message):
        message_id = str(uuid.UUID(message["message_id"]))
        recipient, targets = message.get("recipient"), message.get("targets")
        if (not isinstance(targets, list) or len(targets) > MAX_CONNECTIONS or
                any(not isinstance(name, str) or not USERNAME.fullmatch(name) for name in targets)
                or len(set(targets)) != len(targets)):
            raise ValueError("Invalid chat targets")
        if recipient != "*" and targets != [recipient]:
            raise ValueError("Private chat target mismatch")
        if recipient == "*" and username in targets:
            raise ValueError("Broadcast must exclude sender")
        clean = ChatService.build_message(username, recipient, message.get("text"),
                                          message_id=message_id, targets=targets)
        key = (username, message_id)
        with self.chat_lock:
            delivery = self.chat_deliveries.get(key)
            if delivery is not None and chat_digest(clean) != chat_digest(delivery["message"]):
                raise ValueError("Message ID reused with different content")
            if delivery is None:
                if len(self.chat_deliveries) >= 5000:
                    completed = next((k for k, d in self.chat_deliveries.items()
                                      if set(d["targets"]) <= d["acked"]), None)
                    if completed is None:
                        raise ValueError("Server pending chat limit reached")
                    del self.chat_deliveries[completed]
                delivery = {"message": clean, "targets": targets, "acked": set()}
                self.chat_deliveries[key] = delivery
            remaining = [name for name in targets if name not in delivery["acked"]]
        for target in remaining:
            try:
                self._forward(target, CHAT_STREAM, clean)
            except (ValueError, OSError, TimeoutError, ConnectionError) as exc:
                self._send_error(username, f"Chat remains pending: {exc}")
        self._chat_receipt(key)

    def close(self):
        self.running.clear()
        self.roster_changed.set()
        self.tcp.close()
        with self.connections_lock:
            connections = list(self.connections.items())
        for _, connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                connection.close()
        self.udp.close()
        self.accept_thread.join(timeout=1.0)
        self.roster_thread.join(timeout=1.0)
        deadline = time.monotonic() + 2.0
        for worker, _ in connections:
            worker.join(timeout=max(0, deadline - time.monotonic()))
        with self.transfer_lock:
            self.transfers.clear()
            self.transfer_activity.clear()
            self.transfer_sessions.clear()
