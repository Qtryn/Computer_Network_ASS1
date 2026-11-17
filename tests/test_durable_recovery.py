"""Exercise the actual CLI and HTTPS API through server and client restarts."""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPSHandler, HTTPCookieProcessor, Request, build_opener

from app.features.chat_store import DurableChatState, RelayChatStore
from tests.test_client_sessions import until
from tests.test_server_control import tls_contexts


def port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class DurableRecoveryTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        _, self.tls = tls_contexts(self.root)
        self.cert = str(self.root / "test-cert.pem")
        self.private = str(self.root / "test-key.pem")
        self.relay_db = self.root / "relay.sqlite3"
        self.env = {**os.environ, "COLLAB_KEY": os.urandom(32).hex(), "PYTHONDONTWRITEBYTECODE": "1"}
        self.tcp = int(os.environ.get("COLLAB_TEST_TCP", port()))
        self.udp = int(os.environ.get("COLLAB_TEST_UDP", port(socket.SOCK_DGRAM)))
        self.ui = {"alice": int(os.environ.get("COLLAB_TEST_ALICE", port())),
                   "bob": int(os.environ.get("COLLAB_TEST_BOB", port()))}
        self.cookies = {}

    def process(self, module, *args):
        process = subprocess.Popen([sys.executable, "-B", "-m", module, *map(str, args)],
                                   env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.addCleanup(self.stop, process)
        return process

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=8)

    def server(self):
        process = self.process("app.run_server", "--accounts", self.root / "accounts.json",
                               "--chat-db", self.relay_db, "--tls-cert", self.cert,
                               "--tls-key", self.private, "--tcp-port", self.tcp, "--udp-port", self.udp)

        def listening():
            try:
                with socket.create_connection(("127.0.0.1", self.tcp), timeout=0.2):
                    return True
            except OSError:
                return False
        self.assertTrue(until(listening, 8))
        return process

    def client(self, name):
        process = self.process("app.run_client", "--name", name, "--ui-port", self.ui[name],
                               "--tcp-port", self.tcp, "--udp-port", self.udp, "--tls-ca", self.cert,
                               "--server-name", "localhost", "--ui-cert", self.cert, "--ui-key", self.private,
                               "--state-db", self.root / f"{name}.sqlite3")

        def listening():
            try:
                return self.request(name, "/api/state", authenticated=False)[0] == 200
            except OSError:
                return False
        self.assertTrue(until(listening, 8))
        return process

    def request(self, name, path, body=None, *, authenticated=True):
        timeout = 20 if path in ("/api/register", "/api/login") else 6
        conn = http.client.HTTPSConnection("localhost", self.ui[name], context=self.tls, timeout=timeout)
        try:
            headers = {"Content-Type": "application/json"}
            if authenticated and name in self.cookies:
                headers["Cookie"] = self.cookies[name]
            conn.request("GET" if body is None else "POST", path,
                         None if body is None else json.dumps(body), headers)
            response = conn.getresponse()
            cookie = response.getheader("Set-Cookie")
            if cookie:
                self.cookies[name] = cookie.split(";", 1)[0]
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def login(self, name, *, register=False):
        credentials = {"username": name, "password": "fixture-only-password"}
        if register:
            self.assertEqual(self.request(name, "/api/register", credentials)[0], 200)
        self.assertEqual(self.request(name, "/api/login", credentials)[0], 200)

    def state(self, name):
        return self.request(name, "/api/state")[1]

    def test_two_local_ui_ports_share_a_browser_cookie_jar_without_logging_each_other_out(self):
        self.server()
        for name in self.ui:
            self.client(name)
        jar = CookieJar()
        browser = build_opener(HTTPSHandler(context=self.tls), HTTPCookieProcessor(jar))

        def request(name, path, body=None):
            data = None if body is None else json.dumps(body).encode()
            req = Request(f"https://localhost:{self.ui[name]}{path}", data,
                          {"Content-Type": "application/json"})
            timeout = 20 if path in ("/api/register", "/api/login") else 6
            with browser.open(req, timeout=timeout) as response:
                return json.load(response)

        for name in self.ui:
            credentials = {"username": name, "password": "fixture-only-password"}
            request(name, "/api/register", credentials)
            request(name, "/api/login", credentials)
        for name in self.ui:
            self.assertTrue(request(name, "/api/state")["connected"], name)
        self.assertEqual(len(list(jar)), 2)
        request("alice", "/api/logout", {})
        self.assertFalse(request("alice", "/api/state")["connected"])
        self.assertTrue(request("bob", "/api/state")["connected"])

    def test_direct_and_channel_chat_then_recover_after_both_processes_stop(self):
        server = self.server()
        alice = self.client("alice")
        bob = self.client("bob")
        body = {"recipient": "bob", "text": "private test"}
        self.assertEqual(self.request("alice", "/api/chat", body)[0], 401)
        self.login("alice", register=True)
        self.login("bob", register=True)
        self.assertTrue(until(lambda: "bob" in self.state("alice")["online"], 8))
        for name in self.ui:
            self.assertEqual(self.request(name, "/api/channel", {"channel": "networks"})[0], 202)
        self.assertTrue(until(lambda: all("networks" in self.state(name)["channels"] for name in self.ui), 8))
        self.assertEqual(self.request("alice", "/api/chat",
                                      {"recipient": "#networks", "text": "channel test"})[0], 200)
        self.assertTrue(until(lambda: any(item["text"] == "channel test"
                                       for item in self.state("bob")["history"]), 10))

        code, result = self.request("alice", "/api/chat", body)
        self.assertEqual(code, 200)
        direct_id = result["chat"]["message_id"]
        self.assertTrue(until(lambda: any(event.get("path") == "direct" and event.get("message_id") == direct_id
                                       for event in self.state("alice")["events"]), 10))
        self.assertIsNone(RelayChatStore(self.relay_db).delivery(("alice", direct_id)))

        self.stop(server)
        self.assertTrue(until(lambda: not self.state("alice")["connected"], 8))
        code, result = self.request("alice", "/api/chat", {"recipient": "bob", "text": "saved offline"})
        self.assertEqual(code, 202)
        self.assertTrue(result["queued_offline"])
        message_id = result["chat"]["message_id"]
        self.assertEqual(self.state("alice")["outbox"][0]["message_id"], message_id)
        self.stop(alice)
        self.assertEqual(DurableChatState("alice", self.root / "alice.sqlite3").pending()[0]["message_id"],
                         message_id)
        self.server()
        alice = self.client("alice")
        self.login("alice")
        self.assertTrue(until(lambda: RelayChatStore(self.relay_db).pending("bob"), 8))
        self.login("bob")
        self.assertTrue(until(lambda: any(item["message_id"] == message_id and
                                       item.get("delivery") == "DELIVERED"
                                       for item in self.state("alice")["history"]), 12))
        self.assertEqual(sum(item["message_id"] == message_id for item in self.state("bob")["history"]), 1)
        private = self.request("bob", "/api/state", authenticated=False)[1]
        self.assertFalse(private["connected"])
        self.assertNotIn("history", private)

        self.stop(bob)
        self.assertTrue(until(lambda: "bob" not in self.state("alice")["online"], 8))
        self.assertIn("bob", self.state("alice")["chat_recipients"])
        code, result = self.request("alice", "/api/chat",
                                    {"recipient": "bob", "text": "awaiting application receipt"})
        self.assertEqual(code, 200)
        in_flight = result["chat"]["message_id"]
        self.assertTrue(until(lambda: any(item["message_id"] == in_flight
                                       for item in RelayChatStore(self.relay_db).pending("bob")), 8))
        self.stop(alice)
        self.client("alice")
        self.client("bob")
        self.login("alice")
        self.login("bob")
        self.assertTrue(until(lambda: any(item["message_id"] == in_flight and
                                       item.get("delivery") == "DELIVERED"
                                       for item in self.state("alice")["history"]), 12))
        self.assertEqual(sum(item["message_id"] == in_flight for item in self.state("bob")["history"]), 1)
