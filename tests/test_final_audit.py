"""Pre-report checks using real loopback sockets and local client processes."""
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.client import CollaborationClient
from app.features.chat import ChatService
from app.features.outbox import ChatState
from app.server.server import CollaborationServer
from tests.test_client_sessions import until


class FinalAuditTests(unittest.TestCase):
    def test_concurrent_chat_files_logout_and_resource_cleanup(self):
        for count in (2, 10, 20):
            with self.subTest(clients=count), tempfile.TemporaryDirectory() as directory:
                baseline = set(threading.enumerate())
                root = Path(directory)
                key = os.urandom(32)
                server = CollaborationServer("127.0.0.1", 0, 0, key)
                clients = []
                try:
                    def connect(index):
                        return CollaborationClient(f"audit{index:02}", key=key,
                            tcp_port=server.tcp_port, udp_port=server.udp_port,
                            download_dir=root / f"receiver{index:02}")

                    with ThreadPoolExecutor(max_workers=count) as pool:
                        clients = list(pool.map(connect, range(count)))
                        self.assertTrue(until(lambda: all(len(c.online) == count for c in clients)))
                        list(pool.map(lambda c: c.send_chat("*", "global " + c.username), clients))
                        self.assertTrue(until(lambda: all(not c.chat_state.pending() for c in clients), 20))
                        for client in clients:
                            received = [e for e in client.get_state()["events"] if e["type"] == "CHAT"
                                        and not e.get("outgoing")]
                            self.assertEqual(len(received), count - 1)
                            self.assertEqual(len({e["message_id"] for e in received}), count - 1)

                        def private(index):
                            clients[index].send_chat(clients[(index + 1) % count].username,
                                                     f"private {index}")

                        list(pool.map(private, range(count)))
                        self.assertTrue(until(lambda: all(not c.chat_state.pending() for c in clients), 20))
                        for index, client in enumerate(clients):
                            self.assertTrue(any(e.get("text") == f"private {(index - 1) % count}"
                                                for e in client.get_state()["events"]))

                        def transfer(index):
                            payload = bytes(range(256)) * 80  # 20 KiB, > 6 transport windows
                            source = root / f"Báo cáo {index}.bin"
                            source.write_bytes(payload)
                            receiver = clients[index + 1]
                            file_id = clients[index].send_file(source, receiver.username)
                            self.assertTrue(until(lambda: any(e.get("type") == "FILE_RECEIPT"
                                and e.get("file_id") == file_id and e.get("status") == "ok"
                                for e in clients[index].get_state()["events"]), 20))
                            destination = root / f"receiver{index + 1:02}" / source.name
                            self.assertEqual(hashlib.sha256(destination.read_bytes()).digest(),
                                             hashlib.sha256(payload).digest())

                        list(pool.map(transfer, range(0, count, 2)))
                        self.assertTrue(until(lambda: not server.transfers))
                        self.assertFalse(list(root.rglob("*.part")))
                        self.assertFalse(server.transfer_activity)
                        self.assertFalse(server.transfer_sessions)
                        list(pool.map(lambda c: c.close(), clients))
                        self.assertTrue(until(lambda: not server.registry.names()))
                        self.assertTrue(until(lambda: not server.connections))
                        self.assertTrue(all(c.tcp.fileno() == -1 and c.udp.sock.fileno() == -1
                                            for c in clients))
                    print(f"[final audit] {count} concurrent clients: global/private chat, "
                          f"{count // 2} files with SHA-256, logout/metadata/socket cleanup PASS")
                finally:
                    for client in clients:
                        client.close()
                    server.close()
                self.assertTrue(until(lambda: not (set(threading.enumerate()) - baseline), 5),
                                "Application threads survived shutdown")

    def test_reused_chat_id_with_changed_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            key = os.urandom(32)
            server = CollaborationServer("127.0.0.1", 0, 0, key)
            clients = []
            try:
                for name in ("alice", "bob"):
                    clients.append(CollaborationClient(name, key=key, tcp_port=server.tcp_port,
                        udp_port=server.udp_port, download_dir=Path(directory) / name))
                alice, bob = clients
                alice.send_chat("bob", "original")
                self.assertTrue(until(lambda: not alice.chat_state.pending()))
                original = next(e for e in bob.get_state()["events"] if e["type"] == "CHAT")
                changed = ChatService.build_message("alice", "bob", "changed",
                    message_id=original["message_id"], targets=["bob"])
                alice.udp.send(alice.server_udp, {**changed, "token": alice.token}, alice.chat_stream)
                self.assertTrue(until(lambda: any("reused" in e.get("message", "")
                    for e in alice.get_state()["events"])))
                self.assertEqual([e["text"] for e in bob.get_state()["events"] if e["type"] == "CHAT"],
                                 ["original"])
                self.assertTrue(bob.chat_state.already_received(original))
                with self.assertRaisesRegex(ValueError, "reused"):
                    bob.chat_state.already_received(changed)
            finally:
                for client in clients:
                    client.close()
                server.close()

    def test_closing_local_process_discards_ram_outbox(self):
        with tempfile.TemporaryDirectory() as directory:
            key = os.urandom(32)
            server = CollaborationServer("127.0.0.1", 0, 0, key)
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                ui_port = reservation.getsockname()[1]
            command = [sys.executable, "-m", "app.run_client", "--name", "audit_owner",
                       "--tcp-port", str(server.tcp_port), "--udp-port", str(server.udp_port),
                       "--ui-port", str(ui_port)]
            environment = {**os.environ, "COLLAB_KEY": key.hex()}

            def request(path, body=None):
                connection = http.client.HTTPConnection("127.0.0.1", ui_port, timeout=2)
                try:
                    connection.request("GET" if body is None else "POST", path,
                        None if body is None else json.dumps(body),
                        {"Content-Type": "application/json"})
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    self.assertEqual(response.status, 200, result)
                    return result
                finally:
                    connection.close()

            def ready():
                try:
                    return request("/api/state")["connected"] is False
                except OSError:
                    return False

            def start():
                process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.addCleanup(lambda: process.poll() is None and process.kill())
                self.assertTrue(until(ready, 8))
                request("/api/login", {"username": "audit_owner", "password": ""})
                return process

            process = None
            try:
                process = start()
                request("/api/chat", {"recipient": "absent", "text": "RAM pending only"})
                before = request("/api/state")["outbox"]
                self.assertEqual(len(before), 1)
                process.terminate()
                process.wait(timeout=8)
                self.assertTrue(until(lambda: not server.registry.names()))
                process = start()
                self.assertEqual(request("/api/state")["outbox"], [])
                self.assertEqual(ChatState("audit_owner").pending(), [])
                print("[final audit] local process restart loses RAM-only pending message as documented")
            finally:
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=8)
                server.close()
