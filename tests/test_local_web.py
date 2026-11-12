"""Member 4 HTTP tests adapted to ClientSession and send_chat -> None."""
import json
import threading
import unittest

from app.client import CollaborationClient
from app.server.server import CollaborationServer
from app.web.local_web import ClientSession, handle_request


class FakeConnection:
    def __init__(self, request):
        self.request, self.response = request, bytearray()

    def settimeout(self, _): pass
    def close(self): pass

    def recv(self, _):
        request, self.request = self.request, b""
        return request

    def sendall(self, data): self.response.extend(data)


class FakeClient:
    def __init__(self, username):
        self.username = username
        self.running = threading.Event()
        self.running.set()
        self.closed = False
        self.sent = []

    def get_state(self, _):
        return {"username": self.username, "online": [self.username],
                "connected": self.running.is_set(), "events": [], "last_id": 0}

    def send_chat(self, recipient, text):
        self.sent.append((recipient, text))  # Deliberately returns None.

    def close(self):
        self.closed = True
        self.running.clear()


def request(ui, method, path, body=b""):
    raw = (f"{method} {path} HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body
    connection = FakeConnection(raw)
    handle_request(connection, ui)
    headers, body = bytes(connection.response).split(b"\r\n\r\n", 1)
    return int(headers.split()[1]), json.loads(body)


class LocalWebLoginTests(unittest.TestCase):
    def test_login_from_ui_and_state(self):
        ui = ClientSession(lambda name, password: FakeClient(name))
        self.addCleanup(ui.close)
        self.assertFalse(request(ui, "GET", "/api/state")[1]["connected"])
        status, result = request(ui, "POST", "/api/login", b'{"username":"alice"}')
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(request(ui, "GET", "/api/state")[1]["username"], "alice")

    def test_invalid_login_body_returns_error(self):
        ui = ClientSession(lambda name, password: FakeClient(name))
        status, result = request(ui, "POST", "/api/login", b"[]")
        self.assertEqual(status, 400)
        self.assertIn("JSON object", result["error"])
        self.assertIsNone(ui.client)

    def test_logout_closes_client_and_returns_to_unauthenticated_state(self):
        ui = ClientSession(lambda name, password: FakeClient(name))
        ui.login("alice")
        old = ui.client
        status, result = request(ui, "POST", "/api/logout")
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertTrue(old.closed)
        self.assertIsNone(ui.client)
        self.assertFalse(request(ui, "GET", "/api/state")[1]["connected"])

    def test_ui_login_connects_to_real_collaboration_server(self):
        key = b"k" * 32
        server = CollaborationServer("127.0.0.1", 0, 0, key)
        self.addCleanup(server.close)
        ui = ClientSession(lambda name, password: CollaborationClient(
            name, "127.0.0.1", server.tcp_port, server.udp_port, key))
        self.addCleanup(ui.close)
        self.assertEqual(request(ui, "POST", "/api/login", b'{"username":"alice"}')[0], 200)
        state = request(ui, "GET", "/api/state")[1]
        self.assertTrue(state["connected"])
        self.assertEqual(state["online"], ["alice"])

    def test_successful_chat_with_none_return_is_not_reported_as_error(self):
        client = FakeClient("alice")
        ui = ClientSession(lambda *_: client, client=client)
        self.addCleanup(ui.close)
        status, body = request(ui, "POST", "/api/chat", b'{"recipient":"bob","text":"sent once"}')
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(client.sent, [("bob", "sent once")])
