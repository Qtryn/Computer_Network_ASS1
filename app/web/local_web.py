"""Minimal localhost HTTP interface built on raw TCP sockets.

This is not a web framework. It supports only the routes required by the
assignment UI: GET /, GET /api/state, POST /api/chat and POST /api/file.
The browser's JavaScript talks to this local server; the Python client sends
chat and files to the collaboration server using the team's UDP transport.
"""
import json
import socket
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HTML_PATH = Path(__file__).parent / "static" / "index.html"
MAX_HEADERS = 16 * 1024
MAX_CHAT_REQUEST = 4096


def send_response(connection, status, content, content_type="application/json; charset=utf-8"):
    """Write one small HTTP response. Each request uses a separate connection."""
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False).encode("utf-8")
    reason = {200: "OK", 202: "Accepted", 400: "Bad Request", 404: "Not Found"}[status]
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
        if method != "POST" or url.path not in ("/api/chat", "/api/file"):
            return send_response(connection, 404, {"error": "Endpoint not found"})

        size = int(headers.get("content-length", "-1"))
        if size < 0:
            raise ValueError("Content-Length is required")

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
    except OSError:
        pass
    finally:
        connection.close()


def run_local_ui(client, port):
    """Start the browser HTTP adapter; listen on 127.0.0.1 only."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(16)
    listener.settimeout(0.5)
    print(f"[client:{client.username}] Open http://127.0.0.1:{port}")
    try:
        while client.running.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            threading.Thread(target=handle_request, args=(connection, client), daemon=True).start()
    finally:
        listener.close()
