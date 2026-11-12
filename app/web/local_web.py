"""Minimal localhost HTTP interface built on raw TCP sockets.

This is not a web framework. It supports only the routes required by the
assignment UI: GET /, GET /api/state, POST /api/login, /api/logout, /api/chat,
and /api/file. Account login uses the same raw sockets wrapped with TLS.
The browser's JavaScript talks to this local server; the Python client sends
chat and files to the collaboration server using the team's UDP transport.
"""
import json
import socket
import ssl
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from app.server.auth import USERNAME

HTML_PATH = Path(__file__).parent / "static" / "index.html"
MAX_HEADERS = 16 * 1024
MAX_CHAT_REQUEST = 4096


class ClientSession:
    """Keep the local HTTP listener alive across network login/logout."""
    def __init__(self, factory, *, client=None, account_mode=False, username="",
                 registration_factory=None, auto_reconnect=False):
        self.factory = factory
        self.client = client
        self.account_mode = account_mode
        self.username = username
        self.lock = threading.Lock()
        self.registration_factory = registration_factory
        self.chat_states = {}
        if client is not None and hasattr(client, "chat_state"):
            self.chat_states[client.username] = client.chat_state
        self.reconnect_user = client.username if client else None
        self.reconnect_error = ""
        self.next_retry = 0
        self.retry_delay = 1
        self.stop = threading.Event()
        self.reconnect_thread = None
        if auto_reconnect:
            self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self.reconnect_thread.start()

    def _connect(self, username, password):
        client = self.factory(username, password)
        if hasattr(client, "chat_state"):
            state = self.chat_states.setdefault(username, client.chat_state)
            if state.username != username:
                client.close()
                raise ValueError("Outbox identity mismatch")
            client.chat_state = state
            client.outbox_wakeup.set()
        self.client = client
        self.reconnect_user = username
        self.username = username
        self.reconnect_error = ""
        self.retry_delay = 1

    def login(self, username, password=None):
        with self.lock:
            if not isinstance(username, str) or not USERNAME.fullmatch(username):
                raise ValueError("Username: 1-20 letters, digits or underscores")
            if self.client and self.client.running.is_set():
                raise ValueError("Already logged in; log out first")
            if self.client:
                self.client.close()
                self.client = None
            if self.account_mode and not password:
                raise ValueError("Password is required in account mode")
            if not self.account_mode and password:
                raise ValueError("Demo mode does not use passwords")
            self.reconnect_user = None
            self._connect(username, password if self.account_mode else None)

    def register(self, username, password):
        if not self.account_mode or self.registration_factory is None:
            raise ValueError("Registration requires TLS account mode")
        self.registration_factory(username, password)

    def logout(self):
        with self.lock:
            self.reconnect_user = None  # Explicit logout must never auto-login.
            if self.client:
                self.client.close()
                self.client = None

    def close(self):
        self.stop.set()
        self.logout()
        if self.reconnect_thread:
            self.reconnect_thread.join(timeout=5)

    def _reconnect_loop(self):
        while not self.stop.wait(0.2):
            with self.lock:
                # Accounts require fresh user-entered credentials; none are saved.
                if (self.account_mode or not self.reconnect_user or
                        (self.client and getattr(self.client, "disconnect_kind", None) == "expired") or
                        (self.client and self.client.running.is_set()) or time.monotonic() < self.next_retry):
                    continue
                name = self.reconnect_user
                if self.client:
                    self.client.close()
                    self.client = None
                try:
                    self._connect(name, None)
                except (OSError, ValueError, RuntimeError) as exc:
                    self.reconnect_error = str(exc)
                    self.next_retry = time.monotonic() + self.retry_delay
                    self.retry_delay = min(8, self.retry_delay * 2)

    def active_client(self):
        with self.lock:
            client = self.client
        if client is None or not client.running.is_set():
            raise ConnectionError("Log in before sending messages or files")
        return client

    def get_state(self, after_id=0):
        with self.lock:
            state = self.client.get_state(after_id) if self.client else {
                "username": self.username, "connected": False, "online": [],
                "events": [], "last_id": 0, "session_id": None}
            expired = self.client and getattr(self.client, "disconnect_kind", None) == "expired"
            reauth = bool((self.account_mode or expired) and self.reconnect_user and not state["connected"])
            retry = bool(not reauth and self.reconnect_user and not state["connected"])
        return {**state, "account_mode": self.account_mode,
                "registration_enabled": self.account_mode and self.registration_factory is not None,
                "reauth_required": reauth, "reconnecting": retry,
                "reconnect_error": self.reconnect_error}


def send_response(connection, status, content, content_type="application/json; charset=utf-8"):
    """Write one small HTTP response. Each request uses a separate connection."""
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False).encode("utf-8")
    reason = {200: "OK", 202: "Accepted", 400: "Bad Request", 404: "Not Found",
              503: "Service Unavailable"}[status]
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(content)}\r\n"
        "Cache-Control: no-store\r\n"
        "X-Content-Type-Options: nosniff\r\n"
        "Connection: close\r\n\r\n"
    )
    connection.sendall(headers.encode("ascii") + content)


def read_request(connection):
    """Read request headers and return already-received body bytes too."""
    received = bytearray()
    while b"\r\n\r\n" not in received:
        block = connection.recv(4096)
        if not block:
            raise ValueError("Incomplete HTTP request")
        received.extend(block)
        if len(received) > MAX_HEADERS:
            raise ValueError("HTTP headers too large")
    head, body = bytes(received).split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3 or parts[2] not in ("HTTP/1.0", "HTTP/1.1"):
        raise ValueError("Invalid HTTP request line")
    method, target, _ = parts
    headers = {}
    for line in lines[1:]:
        if ":" not in line:
            raise ValueError("Invalid HTTP header")
        name, value = line.split(":", 1)
        headers[name.lower().strip()] = value.strip()
    if "transfer-encoding" in headers:
        raise ValueError("Chunked HTTP uploads are not supported")
    return method, urlsplit(target), headers, body


def read_body(connection, first_bytes, length, destination=None):
    """Read exactly Content-Length bytes; stream uploads directly to a file."""
    remaining = length
    current = first_bytes[:remaining]
    if destination is None:
        result = bytearray()
    while remaining:
        if current:
            data = current[:remaining]
            current = current[len(data):]
        else:
            data = connection.recv(min(64 * 1024, remaining))
            if not data:
                raise ValueError("Upload ended before Content-Length")
        if destination is None:
            result.extend(data)
        else:
            destination.write(data)
        remaining -= len(data)
    if destination is None:
        return bytes(result)


def handle_request(connection, client):
    connection.settimeout(30)
    try:
        method, url, headers, first_bytes = read_request(connection)
        if method == "GET" and url.path in ("/", "/index.html"):
            return send_response(connection, 200, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        if method == "GET" and url.path == "/api/state":
            after = int(parse_qs(url.query).get("after", ["0"])[0])
            return send_response(connection, 200, client.get_state(after))
        if method != "POST" or url.path not in ("/api/chat", "/api/file", "/api/login", "/api/logout", "/api/register"):
            return send_response(connection, 404, {"error": "Endpoint not found"})

        size = int(headers.get("content-length", "-1"))
        if size < 0:
            raise ValueError("Content-Length is required")

        if url.path in ("/api/login", "/api/logout", "/api/register"):
            if size > MAX_CHAT_REQUEST:
                raise ValueError("Login request too large")
            body = read_body(connection, first_bytes, size)
            if url.path == "/api/logout":
                client.logout()
            else:
                if client.account_mode and not isinstance(connection, ssl.SSLSocket):
                    raise ValueError("Account login requires local HTTPS")
                credentials = json.loads(body)
                if not isinstance(credentials, dict):
                    raise ValueError("Login body must be a JSON object")
                if url.path == "/api/register":
                    client.register(credentials.get("username"), credentials.get("password"))
                else:
                    client.login(credentials.get("username"), credentials.get("password"))
            return send_response(connection, 200, {"ok": True})

        if isinstance(client, ClientSession):
            client = client.active_client()

        if url.path == "/api/chat":
            if size > MAX_CHAT_REQUEST:
                raise ValueError("Chat request too large")
            message = json.loads(read_body(connection, first_bytes, size))
            client.send_chat(message["recipient"], message["text"])
            return send_response(connection, 200, {"ok": True})

        recipient = parse_qs(url.query).get("to", [""])[0]
        if not recipient or recipient == "*":
            raise ValueError("Choose an online recipient for the file")
        filename = unquote(headers.get("x-filename", "upload.bin"))
        # An uploaded file is staged on disk, not kept in memory.
        with tempfile.NamedTemporaryFile(prefix="collab_upload_", delete=False) as temporary:
            path = Path(temporary.name)
            try:
                read_body(connection, first_bytes, size, destination=temporary)
            except Exception:
                temporary.close()
                path.unlink(missing_ok=True)
                raise

        def send_file():
            try:
                client.send_file(path, recipient, display_name=filename)
            except Exception as error:
                client._emit({"type": "ERROR", "message": f"Upload failed: {error}"})
            finally:
                path.unlink(missing_ok=True)

        threading.Thread(target=send_file, daemon=True).start()
        return send_response(connection, 202, {"ok": True, "message": "Upload started"})
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as error:
        try:
            send_response(connection, 400, {"error": str(error)})
        except OSError:
            pass
    except (OSError, TimeoutError, ConnectionError) as error:
        try:
            send_response(connection, 503, {"error": str(error) or "Network request failed"})
        except OSError:
            pass
    finally:
        connection.close()


def run_local_ui(client, port, tls_context=None):
    """Start the browser HTTP adapter; listen on 127.0.0.1 only."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(16)
    listener.settimeout(0.5)
    scheme = "https" if tls_context else "http"
    print(f"[client] Open {scheme}://127.0.0.1:{port}")

    def serve(connection):
        try:
            connection.settimeout(5)
            if tls_context:
                connection = tls_context.wrap_socket(connection, server_side=True)
            handle_request(connection, client)
        except OSError:
            connection.close()
    try:
        while True:
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            threading.Thread(target=serve, args=(connection,), daemon=True).start()
    finally:
        listener.close()
