"""Real socket regressions for TLS, local HTTP sessions and interrupted files."""
import hashlib
import json
import os
import socket
import ssl
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from app.client import CollaborationClient
from app.features.files import FileReceiver, FileSender
from app.server.auth import PasswordAccounts, hash_password
from app.server.server import CollaborationServer
from app.web.local_web import ClientSession, handle_request
from tests.test_server_control import tls_contexts


def until(predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def http(session, path, body=None, *, raw=None, headers=None):
    left, right = socket.socketpair()
    local_tls = getattr(session, "test_local_tls", None)

    def serve():
        connection = local_tls[0].wrap_socket(right, server_side=True) if local_tls else right
        handle_request(connection, session)

    worker = threading.Thread(target=serve)
    worker.start()
    if local_tls:
        left = local_tls[1].wrap_socket(left, server_hostname="localhost")
    try:
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
        method = "POST" if body is not None or raw is not None else "GET"
        extra = "".join(f"{key}: {value}\r\n" for key, value in (headers or {}).items())
        left.sendall((f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
                      f"Content-Length: {len(data)}\r\n{extra}\r\n").encode() + data)
        response = b""
        while True:
            try:
                block = left.recv(65536)
            except ConnectionResetError:
                if response:
                    break  # Windows may reset after rejecting an unread body.
                raise
            if not block:
                break
            response += block
        head, content = response.split(b"\r\n\r\n", 1)
        return int(head.split()[1]), json.loads(content)
    finally:
        left.close()
        worker.join(2)


class ClientSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.key = os.urandom(32)

    def server(self, **kwargs):
        server = CollaborationServer("127.0.0.1", 0, 0, self.key, **kwargs)
        self.addCleanup(server.close)
        return server

    def client(self, server, name, **kwargs):
        client = CollaborationClient(name, tcp_port=server.tcp_port,
                                     udp_port=server.udp_port, key=self.key,
                                     download_dir=self.root / name, **kwargs)
        self.addCleanup(client.close)
        return client

    def test_http_login_chat_file_logout_relogin_and_revoked_token(self):
        server = self.server()
        bob = self.client(server, "bob")
        session = ClientSession(lambda name, password: self.client(server, name), username="alice")
        self.addCleanup(session.logout)
        self.assertEqual(http(session, "/api/chat", {"recipient": "bob", "text": "blocked"})[0], 503)
        self.assertEqual(http(session, "/api/login", {"username": "alice"})[0], 200)
        alice = session.client
        old_token, peer = alice.token, ("127.0.0.1", alice.udp.port)
        self.assertEqual(http(session, "/api/chat", {"recipient": "bob", "text": "old chat"})[0], 200)
        self.assertTrue(until(lambda: any(e.get("text") == "old chat" for e in bob.get_state()["events"])))
        for name, data in (("empty.txt", b""), ("text.txt", "Xin chào".encode()),
                           ("binary.bin", os.urandom(10000))):
            with self.subTest(name=name):
                self.assertEqual(http(session, "/api/file?to=bob", raw=data,
                                      headers={"X-Filename": name})[0], 202)
                self.assertTrue(until(lambda: (self.root / "bob" / name).exists()))
                self.assertEqual(hashlib.sha256((self.root / "bob" / name).read_bytes()).digest(),
                                 hashlib.sha256(data).digest())
        self.assertEqual(http(session, "/api/logout", {})[0], 200)
        self.assertTrue(until(lambda: "alice" not in bob.get_state()["online"]))
        self.assertEqual(alice.get_state()["events"], [])
        self.assertEqual(alice.event_id, 0)
        self.assertFalse(alice.heartbeat_thread.is_alive())
        self.assertFalse(alice.udp.recv_thread.is_alive())
        self.assertIsNone(server.registry.authenticate("alice", old_token, peer))
        for action in (lambda: alice.send_chat("bob", "stale"),
                       lambda: alice.send_file(self.root / "missing", "bob")):
            with self.assertRaises(ConnectionError):
                action()
        # Replaying a correctly encrypted message with the old token is ignored.
        count = len(bob.get_state()["events"])
        server._handle_udp(peer, uuid.uuid4(), {"type": "CHAT", "sender": "alice",
                           "recipient": "bob", "text": "stale", "token": old_token})
        self.assertEqual(len(bob.get_state()["events"]), count)
        self.assertEqual(http(session, "/api/logout", {})[0], 200)
        self.assertTrue(until(lambda: server.registry.get("alice") is None))
        self.assertEqual(http(session, "/api/login", {"username": "alice"})[0], 200)
        self.assertNotEqual(session.client.token, old_token)
        state = http(session, "/api/state")[1]
        self.assertFalse(any(e.get("type") == "CHAT" for e in state["events"]))
        self.assertTrue(any(e.get("text") == "old chat" for e in bob.get_state()["events"]))
        self.assertTrue((self.root / "bob" / "binary.bin").exists())

    def test_tls_password_login_http_errors_and_certificate_validation(self):
        tls_server, tls_client = tls_contexts(self.root)
        records = {}
        for name in ("alice", "bob"):
            salt = os.urandom(16)
            records[name] = {"salt": salt.hex(), "hash": hash_password("demo-secret", salt).hex()}
        server = self.server(accounts=PasswordAccounts(records), tls_context=tls_server)
        session = ClientSession(lambda name, password: self.client(
            server, name, password=password, tls_context=tls_client, server_hostname="localhost"),
            account_mode=True)
        self.addCleanup(session.logout)
        self.assertIn("HTTPS", http(session, "/api/login", {"username": "alice"})[1]["error"])
        session.test_local_tls = (tls_server, tls_client)
        self.assertEqual(http(session, "/api/login", {"username": "alice"})[0], 400)
        status, error = http(session, "/api/login", {"username": "alice", "password": "wrong"})
        self.assertEqual(status, 400)
        self.assertIn("Invalid username or password", error["error"])
        self.assertEqual(http(session, "/api/login", {"username": "alice", "password": "demo-secret"})[0], 200)
        bob = self.client(server, "bob", password="demo-secret", tls_context=tls_client,
                          server_hostname="localhost")
        session.client.send_chat("bob", "TLS authenticated")
        self.assertTrue(until(lambda: any(e.get("text") == "TLS authenticated"
                                         for e in bob.get_state()["events"])))
        self.assertNotIn("demo-secret", json.dumps(http(session, "/api/state")[1]))
        with self.assertRaisesRegex(ValueError, "already online"):
            self.client(server, "alice", password="demo-secret", tls_context=tls_client,
                        server_hostname="localhost")
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.client(server, "charlie", password="x", tls_context=tls_client,
                        server_hostname="wrong-host")
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.client(server, "charlie", password="x", tls_context=ssl.create_default_context(),
                        server_hostname="localhost")
        with self.assertRaisesRegex(ValueError, "verified TLS"):
            self.client(server, "charlie", password="never-send-this")

    def test_abrupt_tcp_loss_closes_udp_and_clears_history(self):
        server = self.server()
        alice = self.client(server, "alice")
        connection = server.registry.get("alice").control_socket
        connection.shutdown(socket.SHUT_RDWR)
        connection.close()
        self.assertTrue(until(lambda: alice.closed and not alice.udp.running.is_set()))
        self.assertTrue(until(lambda: alice.get_state()["events"] == []))
        alice.close()

    def test_disconnected_state_never_exposes_events_during_cleanup(self):
        server = self.server()
        alice = self.client(server, "alice")
        alice._emit({"type": "CHAT", "text": "old private history"})
        alice.running.clear()  # Window before socket/file cleanup finishes.
        state = alice.get_state()
        self.assertEqual(state["events"], [])
        self.assertEqual(state["online"], [])
        self.assertEqual(state["last_id"], 0)
        alice.close()

    def test_disconnect_and_timeout_cleanup_leave_other_transfers_intact(self):
        now = [0.0]
        server = self.server(clock=lambda: now[0], transfer_timeout=10)
        alice, bob = self.client(server, "alice"), self.client(server, "bob")
        charlie = self.client(server, "charlie")
        path = self.root / "source.bin"
        path.write_bytes(b"unfinished")

        def start(sender, recipient):
            file_id, _, messages = FileSender().prepare(path, sender.username, recipient)
            event = next(messages)
            sender.udp.send(sender.server_udp, {**event, "token": sender.token}, uuid.UUID(file_id))
            return file_id

        first = start(alice, "bob")
        second = start(bob, "charlie")
        self.assertTrue(until(lambda: len(server.transfers) == 2 and
                             first in bob.file_receiver.incoming and second in charlie.file_receiver.incoming))
        alice.close()
        self.assertTrue(until(lambda: first not in server.transfers and first not in bob.file_receiver.incoming))
        self.assertIn(second, server.transfers)
        self.assertEqual(list((self.root / "bob").glob("*.part")), [])
        now[0] = 11
        self.assertTrue(until(lambda: not server.transfers and not charlie.file_receiver.incoming))
        self.assertEqual(list((self.root / "charlie").glob("*.part")), [])

    def test_partial_file_timeout_preserves_completed_file(self):
        now = [0.0]
        receiver = FileReceiver(self.root / "received", timeout=5, clock=lambda: now[0])
        self.addCleanup(receiver.close)
        path = self.root / "source.txt"
        path.write_bytes(b"completed")
        file_id, _, packets = FileSender().prepare(path, "alice", "bob")
        for event in packets:
            complete = receiver.process(event)
        _, _, packets = FileSender().prepare(path, "alice", "bob")
        partial = next(packets)
        receiver.process(partial)
        now[0] = 6
        self.assertEqual(receiver.cleanup_expired(), [partial["file_id"]])
        self.assertTrue(Path(complete["path"]).exists())
        self.assertFalse(any(receiver.download_dir.glob("*.part")))

    def test_receiver_disconnect_aborts_sender_transfer(self):
        server = self.server()
        alice, bob = self.client(server, "alice"), self.client(server, "bob")
        path = self.root / "source.bin"
        path.write_bytes(b"incomplete")
        file_id, _, packets = FileSender().prepare(path, "alice", "bob")
        alice.udp.send(alice.server_udp, {**next(packets), "token": alice.token}, uuid.UUID(file_id))
        self.assertTrue(until(lambda: file_id in bob.file_receiver.incoming))
        bob.close()
        self.assertTrue(until(lambda: file_id not in server.transfers))
        self.assertFalse(any((self.root / "bob").glob("*.part")))
        self.assertTrue(until(lambda: any(e.get("type") == "ERROR" and "interrupted" in e.get("message", "")
                                         for e in alice.get_state()["events"])))

    def test_bad_http_json_offline_recipient_and_network_error(self):
        server = self.server()
        alice = self.client(server, "alice")
        session = ClientSession(lambda *_: None, client=alice)
        self.assertEqual(http(session, "/api/chat", raw=b"{broken")[0], 400)
        self.assertEqual(http(session, "/api/chat", raw=b"[]")[0], 400)
        self.assertEqual(http(session, "/api/chat", raw=b"x" * 5000)[0], 400)
        alice.send_chat("offline", "should fail")
        self.assertTrue(until(lambda: any(e.get("type") == "ERROR" and "offline" in e.get("message", "")
                                         for e in alice.get_state()["events"])))
        alice.udp.ack_timeout, alice.udp.max_retries = 0.01, 0
        alice.udp._sendto = lambda *_: None
        status, body = http(session, "/api/chat", {"recipient": "offline", "text": "lost"})
        self.assertEqual(status, 503)
        self.assertIn("not acknowledged", body["error"])


if __name__ == "__main__":
    unittest.main()
