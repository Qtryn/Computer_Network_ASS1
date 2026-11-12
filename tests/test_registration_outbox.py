"""Real HTTPS/TLS/UDP regressions for registration, restart and outbox identity."""
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from app.client import CollaborationClient, register_account
from app.features.outbox import ChatState
from app.server.auth import PasswordAccounts, read_accounts
from app.server.server import CollaborationServer
from app.transport.reliable_udp import CHAT_STREAM, ReliableUDP
from app.common.protocol import session_stream
from app.common.protocol import HEADER, encode_message
from app.common.config import MAX_DATAGRAM
from app.security.crypto import OVERHEAD
from app.features.chat import ChatService
from app.web.local_web import ClientSession
from tests.test_client_sessions import http, until
from tests.test_server_control import tls_contexts


class RegistrationOutboxTests(unittest.TestCase):
    def test_stable_message_id_and_targets_are_included_in_budget(self):
        for text in ("x" * 600, '"' * 600, "\x01" * 600, "ệ" * 200):
            try:
                message = ChatService.build_message("u" * 20, "v" * 20, text,
                    message_id="00000000-0000-0000-0000-000000000003", targets=["v" * 20])
            except ValueError:
                continue
            size = HEADER.size + OVERHEAD + len(encode_message({**message, "token": "f" * 48}))
            self.assertLessEqual(size, MAX_DATAGRAM)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.key = os.urandom(32)
        self.path = self.root / "accounts.json"
        self.tls_server, self.tls_client = tls_contexts(self.root)

    def start(self, *, ports=(0, 0), account_mode=True):
        options = {}
        if account_mode:
            records = read_accounts(self.path) if self.path.exists() else {}
            options = {"accounts": PasswordAccounts(records, path=self.path), "tls_context": self.tls_server}
        server = CollaborationServer("127.0.0.1", *ports, self.key, **options)
        self.addCleanup(server.close)
        return server

    def provision(self, *names):
        store = PasswordAccounts({}, path=self.path)
        for name in names:
            store.register(name, "demo-secret")

    def session(self, ports, *, account_mode=True, auto=False):
        def connect(name, password):
            client = CollaborationClient(name, tcp_port=ports[0], udp_port=ports[1], key=self.key,
                download_dir=self.root / name,
                password=password, tls_context=self.tls_client if account_mode else None,
                server_hostname="localhost", chat_state=ui.chat_states.setdefault(name, ChatState(name)))
            self.addCleanup(client.close)
            return client

        def register(name, password):
            register_account(name, password, tcp_port=ports[0], tls_context=self.tls_client,
                             server_hostname="localhost")

        ui = ClientSession(connect, account_mode=account_mode, registration_factory=register,
                           auto_reconnect=auto)
        ui.test_local_tls = (self.tls_server, self.tls_client) if account_mode else None
        self.addCleanup(ui.close)
        return ui

    def test_https_registration_login_duplicate_validation_and_restart_persistence(self):
        server = self.start()
        ports = (server.tcp_port, server.udp_port)
        ui = self.session(ports)
        for credentials in ({"username": "bad name", "password": "demo-secret"},
                            {"username": "alice", "password": "short"}):
            self.assertEqual(http(ui, "/api/register", credentials)[0], 400)
        credentials = {"username": "alice", "password": "demo-secret"}
        self.assertEqual(http(ui, "/api/register", credentials)[0], 200)
        self.assertEqual(http(ui, "/api/register", credentials)[0], 400)
        self.assertNotIn("demo-secret", self.path.read_text())
        self.assertEqual(http(ui, "/api/login", credentials)[0], 200)
        self.assertEqual(ui.client.username, "alice")
        ui.logout()
        server.close()
        self.start(ports=ports)
        self.assertEqual(http(ui, "/api/login", credentials)[0], 200)

    def test_registration_is_thread_safe_and_atomic_on_write_failure(self):
        store = PasswordAccounts({}, path=self.path)

        def register(_):
            try:
                store.register("alice", "demo-secret")
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(register, range(4))), 1)
        self.assertEqual(list(read_accounts(self.path)), ["alice"])
        before = self.path.read_bytes()
        with patch("pathlib.Path.replace", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                store.register("bob", "demo-secret")
        self.assertNotIn("bob", store.accounts)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".accounts-*")), [])

    def test_registration_rejects_insecure_transport(self):
        server = self.start()
        ui = self.session((server.tcp_port, server.udp_port))
        ui.test_local_tls = None
        status, body = http(ui, "/api/register", {"username": "alice", "password": "demo-secret"})
        self.assertEqual(status, 400)
        self.assertIn("HTTPS", body["error"])
        with self.assertRaisesRegex(ValueError, "verified TLS"):
            register_account("alice", "demo-secret", tcp_port=server.tcp_port)
        self.assertFalse(self.path.exists())

    def test_server_restart_requires_account_login_and_replays_ordered_outbox(self):
        self.provision("alice", "bob")
        server = self.start()
        ports = (server.tcp_port, server.udp_port)
        alice, bob = self.session(ports, auto=True), self.session(ports, auto=True)
        alice.login("alice", "demo-secret")
        bob.login("bob", "demo-secret")
        old_token = alice.client.token
        alice.client.udp.ack_timeout, alice.client.udp.max_retries = 0.02, 0
        alice.client.udp._sendto = lambda *_: None
        for text in ("first pending", "second pending"):
            with self.assertRaises(TimeoutError):
                alice.client.send_chat("bob", text)
        pending = alice.client.chat_state.pending()
        ids = [message["message_id"] for message in pending]
        self.assertEqual(len(set(ids)), 2)
        server.close()
        self.assertTrue(until(lambda: not alice.get_state()["connected"] and not bob.get_state()["connected"]))
        self.assertTrue(alice.get_state()["reauth_required"])
        self.assertEqual(alice.get_state()["events"], [])
        self.assertEqual(http(alice, "/api/chat", {"recipient": "bob", "text": "disconnected"})[0], 503)
        self.start(ports=ports)
        self.assertFalse(alice.get_state()["connected"])  # No password was retained.
        bob.login("bob", "demo-secret")
        alice.login("alice", "demo-secret")
        self.assertNotEqual(alice.client.token, old_token)
        self.assertTrue(until(lambda: not alice.client.chat_state.pending(), seconds=12))
        received = [event for event in bob.client.get_state()["events"] if event["type"] == "CHAT"]
        self.assertEqual([event["text"] for event in received], ["first pending", "second pending"])
        self.assertEqual([event["message_id"] for event in received], ids)
        delivered = [event for event in alice.client.get_state()["events"]
                     if event["type"] == "CHAT_RECEIPT" and event.get("status") == "DELIVERED"]
        self.assertEqual([event["message_id"] for event in delivered], ids)

    def test_recipient_deduplicates_after_server_restart_and_lost_application_ack(self):
        self.provision("alice", "bob")
        server = self.start()
        ports = (server.tcp_port, server.udp_port)
        alice, bob = self.session(ports), self.session(ports)
        alice.login("alice", "demo-secret")
        bob.login("bob", "demo-secret")
        original = bob.client.udp.send
        bob.client.udp.send = lambda peer, message, stream=CHAT_STREAM: (
            None if message.get("type") == "CHAT_ACK" else original(peer, message, stream))
        alice.client.send_chat("bob", "exactly once within this local app lifetime")
        self.assertTrue(until(lambda: any(e.get("type") == "CHAT" for e in bob.client.get_state()["events"])))
        self.assertEqual(len(alice.client.chat_state.pending()), 1)
        message_id = alice.client.chat_state.pending()[0]["message_id"]
        server.close()
        self.assertTrue(until(lambda: not alice.get_state()["connected"] and not bob.get_state()["connected"]))
        self.start(ports=ports)
        bob.login("bob", "demo-secret")
        alice.login("alice", "demo-secret")
        self.assertTrue(until(lambda: not alice.client.chat_state.pending(), seconds=10))
        self.assertFalse(any(e.get("type") == "CHAT" for e in bob.client.get_state()["events"]))
        self.assertIn(("alice", message_id), bob.client.chat_state.received)

    def test_pending_outbox_hidden_from_another_account_and_resumed_by_owner(self):
        self.provision("alice", "bob", "charlie")
        server = self.start()
        ports = (server.tcp_port, server.udp_port)
        alice, bob = self.session(ports), self.session(ports)
        alice.login("alice", "demo-secret")
        bob.login("bob", "demo-secret")
        alice.client.udp.ack_timeout, alice.client.udp.max_retries = 0.02, 0
        alice.client.udp._sendto = lambda *_: None
        with self.assertRaises(TimeoutError):
            alice.client.send_chat("bob", "alice-private-pending")
        alice.logout()
        self.assertNotIn("alice-private-pending", json.dumps(alice.get_state()))
        alice.login("charlie", "demo-secret")
        self.assertNotIn("alice-private-pending", json.dumps(alice.get_state()))
        self.assertFalse(alice.client.chat_state.pending())
        alice.client.send_chat("bob", "charlie's own chat")
        self.assertTrue(until(lambda: not alice.client.chat_state.pending()))
        self.assertFalse(any(e.get("text") == "alice-private-pending" for e in bob.client.get_state()["events"]))
        alice.logout()
        alice.login("alice", "demo-secret")
        self.assertTrue(until(lambda: not alice.client.chat_state.pending()))
        self.assertTrue(any(e.get("text") == "alice-private-pending" and e.get("sender") == "alice"
                            for e in bob.client.get_state()["events"]))

    def test_transport_ack_is_not_delivery_and_wrong_receiver_cannot_confirm(self):
        self.provision("alice", "bob", "charlie")
        server = self.start()
        ports = (server.tcp_port, server.udp_port)
        alice, bob, charlie = self.session(ports), self.session(ports), self.session(ports)
        for ui, name in ((alice, "alice"), (bob, "bob"), (charlie, "charlie")):
            ui.login(name, "demo-secret")
        original = bob.client.udp.send
        bob.client.udp.send = lambda *args, **kwargs: None  # Transport still ACKs; app ACK is withheld.
        alice.client.send_chat("bob", "must await app ACK")
        self.assertTrue(until(lambda: any(e.get("text") == "must await app ACK"
                                         for e in bob.client.get_state()["events"])))
        message_id = alice.client.chat_state.pending()[0]["message_id"]
        server._handle_udp(("127.0.0.1", charlie.client.udp.port), session_stream(charlie.client.token, "ack"), {
            "type": "CHAT_ACK", "sender": "charlie", "token": charlie.client.token,
            "original_sender": "alice", "message_id": message_id})
        self.assertEqual(len(alice.client.chat_state.pending()), 1)
        self.assertFalse(any(e.get("status") == "DELIVERED" for e in alice.client.get_state()["events"]))
        bob.client.udp.send = original
        alice.client.outbox_wakeup.set()
        self.assertTrue(until(lambda: not alice.client.chat_state.pending()))
        self.assertEqual(sum(e.get("text") == "must await app ACK" for e in bob.client.get_state()["events"]), 1)

    def test_relogin_reusing_udp_port_has_fresh_sequences_and_rejects_old_chat(self):
        self.provision("alice", "bob")
        server = self.start()
        ports = (server.tcp_port, server.udp_port)
        alice, bob = self.session(ports), self.session(ports)
        alice.login("alice", "demo-secret")
        bob.login("bob", "demo-secret")
        alice.client.send_chat("bob", "before port reuse")
        self.assertTrue(until(lambda: not alice.client.chat_state.pending()))
        old_port, old_stream = alice.client.udp.port, alice.client.chat_stream
        alice.logout()
        self.assertTrue(until(lambda: server.registry.get("alice") is None))

        def reuse_port(host, port, key, callback):
            return ReliableUDP(host, old_port, key, callback)

        with patch("app.client.ReliableUDP", side_effect=reuse_port):
            alice.login("alice", "demo-secret")
        self.assertEqual(alice.client.udp.port, old_port)
        self.assertNotEqual(alice.client.chat_stream, old_stream)
        alice.client.send_chat("bob", "after port reuse")
        self.assertTrue(until(lambda: not alice.client.chat_state.pending()))
        bob.client.send_chat("alice", "reply to reused port")
        self.assertTrue(until(lambda: not bob.client.chat_state.pending()))
        self.assertTrue(any(e.get("text") == "reply to reused port" for e in alice.client.get_state()["events"]))
        alice.client._on_udp_message(alice.client.server_udp, old_stream, {
            "type": "CHAT", "sender": "bob", "recipient": "alice", "text": "late old session"})
        self.assertFalse(any(e.get("text") == "late old session" for e in alice.client.get_state()["events"]))

    def test_demo_auto_reconnect_uses_backoff_and_explicit_logout_stops_it(self):
        server = self.start(account_mode=False)
        ports = (server.tcp_port, server.udp_port)
        ui = self.session(ports, account_mode=False, auto=True)
        ui.login("alice")
        token = ui.client.token
        server.close()
        self.assertTrue(until(lambda: ui.get_state()["reconnecting"]))
        restarted = self.start(ports=ports, account_mode=False)
        self.assertTrue(until(lambda: ui.get_state()["connected"], seconds=12))
        self.assertNotEqual(ui.client.token, token)
        ui.logout()
        time.sleep(0.4)
        self.assertFalse(ui.get_state()["connected"])
        self.assertIsNone(ui.reconnect_user)
        self.assertIsNone(restarted.registry.get("alice"))

    def test_unicode_filename_and_chat_work_through_integrated_http(self):
        server = self.start(account_mode=False)
        ports = (server.tcp_port, server.udp_port)
        alice, bob = self.session(ports, account_mode=False), self.session(ports, account_mode=False)
        alice.login("alice")
        bob.login("bob")
        name, content = "Báo cáo mạng máy tính.txt", "Nội dung tiếng Việt".encode()
        self.assertEqual(http(alice, "/api/file?to=bob", raw=content, headers={"X-Filename": quote(name)})[0], 202)
        self.assertTrue(until(lambda: (self.root / "bob" / name).exists()))
        self.assertEqual((self.root / "bob" / name).read_bytes(), content)
        self.assertEqual(http(alice, "/api/chat", {"recipient": "bob", "text": "UI integrated"})[0], 200)
        self.assertTrue(until(lambda: any(e.get("text") == "UI integrated" for e in bob.client.get_state()["events"])))
