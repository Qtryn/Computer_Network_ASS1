"""HTTP adapter login tests."""

import json
import threading
import unittest

from app.client import CollaborationClient
from app.server.server import CollaborationServer
from app.web.local_web import LocalUIState, handle_request


class FakeConnection:
    def __init__(self, request):
        self.request = request
        self.response = bytearray()

    def settimeout(self, _timeout):
        pass

    def recv(self, _size):
        request, self.request = self.request, b""
        return request

    def sendall(self, data):
        self.response.extend(data)

    def close(self):
        pass


class FakeClient:
    def __init__(self, username):
        self.username = username
        self.running = threading.Event()
        self.running.set()
        self.closed = False

    def get_state(self, _after_id):
        return {"username": self.username, "online": [self.username],
                "connected": True, "events": [], "last_id": 0}

    def close(self):
        self.closed = True
        self.running.clear()


def request(ui, method, path, body=b""):
    raw = (f"{method} {path} HTTP/1.1\r\n"
           f"Content-Length: {len(body)}\r\n\r\n").encode("ascii") + body
    connection = FakeConnection(raw)
    handle_request(connection, ui)
    headers, response_body = bytes(connection.response).split(b"\r\n\r\n", 1)
    return headers.split(b"\r\n", 1)[0], json.loads(response_body)


class LocalWebLoginTests(unittest.TestCase):
    def test_login_from_ui_and_state(self):
        created = []

        def create_client(username):
            client = FakeClient(username)
            created.append(client)
            return client

        ui = LocalUIState(create_client)
        status, initial = request(ui, "GET", "/api/state?after=0")
        self.assertIn(b"200 OK", status)
        self.assertFalse(initial["authenticated"])

        body = json.dumps({"username": "alice"}).encode("utf-8")
        status, result = request(ui, "POST", "/api/login", body)
        self.assertIn(b"200 OK", status)
        self.assertEqual(result["username"], "alice")
        self.assertEqual(len(created), 1)

        _, state = request(ui, "GET", "/api/state?after=0")
        self.assertTrue(state["authenticated"])
        self.assertEqual(state["username"], "alice")
        ui.close()
        self.assertTrue(created[0].closed)

    def test_invalid_login_body_returns_error(self):
        ui = LocalUIState(lambda username: FakeClient(username))
        status, result = request(ui, "POST", "/api/login", b"[]")
        self.assertIn(b"400 Bad Request", status)
        self.assertIn("JSON object", result["error"])
        self.assertIsNone(ui.get_client())

    def test_logout_closes_client_and_returns_to_unauthenticated_state(self):
        created = []

        def create_client(username):
            client = FakeClient(username)
            created.append(client)
            return client

        ui = LocalUIState(create_client)
        ui.login("alice")
        status, result = request(ui, "POST", "/api/logout")
        self.assertIn(b"200 OK", status)
        self.assertTrue(result["ok"])
        self.assertTrue(created[0].closed)
        self.assertIsNone(ui.get_client())
        _, state = request(ui, "GET", "/api/state?after=0")
        self.assertFalse(state["authenticated"])

    def test_ui_login_connects_to_real_collaboration_server(self):
        key = b"k" * 32
        server = CollaborationServer("127.0.0.1", 0, 0, key)
        self.addCleanup(server.close)
        ui = LocalUIState(lambda username: CollaborationClient(
            username, "127.0.0.1", server.tcp_port, server.udp_port, key))
        self.addCleanup(ui.close)

        body = json.dumps({"username": "alice"}).encode("utf-8")
        status, result = request(ui, "POST", "/api/login", body)
        self.assertIn(b"200 OK", status)
        self.assertEqual(result["username"], "alice")
        _, state = request(ui, "GET", "/api/state?after=0")
        self.assertTrue(state["authenticated"])
        self.assertTrue(state["connected"])
        self.assertEqual(state["online"], ["alice"])


if __name__ == "__main__":
    unittest.main()
