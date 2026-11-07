"""TV1 regression checks using real localhost TCP sockets."""

import json
import os
import select
import socket
import ssl
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.server.auth import PasswordAccounts, hash_password
from app.server.server import CollaborationServer, MAX_CONTROL_LINE


def wire(kind, **fields):
    return (json.dumps({"type": kind, **fields}) + "\n").encode("utf-8")


def read(stream):
    return json.loads(stream.readline())


def tls_contexts(directory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=1))
                   .not_valid_after(now + timedelta(days=1))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
                   .sign(key, hashes.SHA256()))
    certfile = Path(directory) / "test-cert.pem"
    keyfile = Path(directory) / "test-key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                          serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(certfile, keyfile)
    return server, ssl.create_default_context(cafile=str(certfile))


class ServerControlTests(unittest.TestCase):
    def start_server(self, **options):
        server = CollaborationServer("127.0.0.1", 0, 0, os.urandom(32), **options)
        self.addCleanup(server.close)
        return server

    def connect(self, server, context=None):
        connection = socket.create_connection(("127.0.0.1", server.tcp_port), timeout=4)
        if context is not None:
            connection = context.wrap_socket(connection, server_hostname="localhost")
        self.addCleanup(connection.close)
        stream = connection.makefile("rb")
        self.addCleanup(stream.close)
        return connection, stream

    def test_split_hello_and_coalesced_requests(self):
        server = self.start_server()
        connection, stream = self.connect(server)
        hello = wire("HELLO", version=1)
        connection.sendall(hello[:-1])
        self.assertFalse(select.select([connection], [], [], 0.1)[0])
        connection.sendall(hello[-1:] + wire("LOGIN", username="alice", udp_port=45000)
                           + wire("GET_USERS"))
        self.assertEqual(read(stream), {"type": "HELLO_OK", "version": 1})
        login = read(stream)
        self.assertEqual(login["type"], "LOGIN_OK")
        self.assertEqual(login["expires_in_seconds"], 3600)
        self.assertEqual(read(stream)["users"], ["alice"])

    def test_bad_connections_do_not_break_listener(self):
        server = self.start_server()
        for payload, code in (
            (wire("HELLO", version=2), "UNSUPPORTED_VERSION"),
            (wire("HELLO", version=True), "INVALID_MESSAGE"),
            (b"[]\n", "INVALID_MESSAGE"),
            (b"\xff\n", "INVALID_MESSAGE"),
            (b"x" * (MAX_CONTROL_LINE + 1), "INVALID_MESSAGE"),
        ):
            with self.subTest(code=code, prefix=payload[:20]):
                connection, stream = self.connect(server)
                connection.sendall(payload)
                self.assertEqual(read(stream), {"type": "PROTOCOL_ERROR", "code": code})
                self.assertEqual(stream.readline(), b"")
        connection, stream = self.connect(server)
        connection.sendall(wire("PING") + wire("HELLO", version=1))
        self.assertEqual(read(stream)["code"], "HELLO_REQUIRED")
        self.assertEqual(read(stream)["type"], "HELLO_OK")

    def test_password_lock_survives_reconnect_and_session_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            tls_server, tls_client = tls_contexts(directory)
        now = [100.0]
        salt = os.urandom(16)
        accounts = PasswordAccounts(
            {"alice": {"salt": salt.hex(), "hash": hash_password("demo-secret", salt).hex()}},
            clock=lambda: now[0],
        )
        with self.assertRaises(ValueError):
            CollaborationServer("127.0.0.1", 0, 0, os.urandom(32), accounts=accounts)
        server = self.start_server(accounts=accounts, tls_context=tls_server, clock=lambda: now[0])
        connection, stream = self.connect(server, tls_client)
        connection.sendall(wire("LOGIN", username="alice", udp_port=45000))
        self.assertEqual(read(stream)["code"], "HELLO_REQUIRED")
        connection.sendall(wire("HELLO", version=1))
        self.assertEqual(read(stream)["type"], "HELLO_OK")

        def login(password):
            connection.sendall(wire("LOGIN", username="alice", udp_port=45000, password=password))
            return read(stream)

        for remaining in (2, 1):
            self.assertEqual(login("wrong"), {"type": "LOGIN_FAIL", "remaining_attempts": remaining})
        self.assertEqual(login("wrong"), {"type": "LOGIN_LOCKED", "retry_after_seconds": 60})
        stream.close()
        connection.close()
        now[0] = 130.0
        connection, stream = self.connect(server, tls_client)
        connection.sendall(wire("HELLO", version=1))
        read(stream)
        self.assertEqual(login("demo-secret"), {"type": "LOGIN_LOCKED", "retry_after_seconds": 30})
        now[0] = 160.0
        for remaining in (2, 1):
            self.assertEqual(login("wrong"), {"type": "LOGIN_FAIL", "remaining_attempts": remaining})
        token = login("demo-secret")["token"]
        peer = ("127.0.0.1", 45000)
        self.assertIsNotNone(server.registry.authenticate("alice", token, peer))
        now[0] += 3600
        connection.sendall(wire("GET_USERS"))
        self.assertEqual(read(stream)["type"], "AUTH_REQUIRED")
        self.assertEqual(server.registry.names(), [])
        self.assertIsNone(server.registry.authenticate("alice", token, peer))
        self.assertNotEqual(login("demo-secret")["token"], token)

    def test_concurrent_logins_and_disconnect_cleanup(self):
        server = self.start_server()
        # A client stuck before HELLO and unresponsive UDP destinations must not stall TCP.
        waiting, _ = self.connect(server)
        waiting.sendall(b'{"type"')

        def login(index):
            connection, stream = self.connect(server)
            connection.sendall(wire("LOGIN", username=f"user{index:02}", udp_port=45000 + index))
            self.assertEqual(read(stream)["type"], "LOGIN_OK")
            return connection, stream

        with ThreadPoolExecutor(max_workers=20) as pool:
            clients = list(pool.map(login, range(20)))
        first, first_stream = clients[0]
        first.sendall(wire("GET_USERS"))
        self.assertEqual(len(read(first_stream)["users"]), 20)
        last, last_stream = clients[-1]
        last_stream.close()
        last.shutdown(socket.SHUT_RDWR)
        last.close()
        deadline = time.monotonic() + 3
        while "user19" in server.registry.names() and time.monotonic() < deadline:
            time.sleep(0.01)
        first.sendall(wire("GET_USERS"))
        self.assertEqual(read(first_stream)["users"], [f"user{i:02}" for i in range(19)])
        server.close()
        self.assertEqual(waiting.recv(1), b"")
