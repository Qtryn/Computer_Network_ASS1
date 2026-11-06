"""Lossy-network tests (Member 5): loss, duplication, reordering, delay, corruption.

Run:  python -m unittest discover -s tests -p "test_lossy*" -v

Faults are injected through ReliableUDP._sendto (see fault_injection.py), with
fixed seeds so the scenarios are repeatable. Retry budgets are raised on purpose:
with loss p in BOTH directions one attempt succeeds with probability (1-p)^2, so
the default max_retries is too small for 20% loss.
"""
import os
import tempfile
import threading
import time
import unittest
import uuid
from hashlib import sha256
from pathlib import Path

try:  # python -m unittest discover -s tests
    from fault_injection import FaultyLink
except ImportError:  # python -m unittest tests.test_lossy_network
    from tests.fault_injection import FaultyLink

from app.transport.reliable_udp import ReliableUDP


def until(predicate, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class TransportUnderFaultsTests(unittest.TestCase):
    def setUp(self):
        self.key = os.urandom(32)
        self.nodes, self.links = [], []

    def tearDown(self):
        for link in self.links:
            link.close()
        for node in self.nodes:
            node.close()

    def node(self, on_message=None, **kwargs):
        kwargs.setdefault("ack_timeout", 0.05)
        kwargs.setdefault("max_retries", 60)
        udp = ReliableUDP("127.0.0.1", 0, self.key, on_message or (lambda *_: None), **kwargs)
        self.nodes.append(udp)
        return udp

    def fault(self, udp, **kwargs):
        link = FaultyLink(udp, **kwargs)
        self.links.append(link)
        return link

    def test_in_order_exactly_once_under_loss_dup_reorder(self):
        delivered = []
        sender = self.node()
        receiver = self.node(lambda peer, stream, msg: delivered.append(msg["n"]))
        up = self.fault(sender, loss=0.2, dup=0.1, reorder=0.2, delay=0.003, jitter=0.002, seed=1)
        self.fault(receiver, loss=0.2, dup=0.1, reorder=0.2, delay=0.003, jitter=0.002, seed=2)
        sender.send_many(("127.0.0.1", receiver.port),
                         ({"type": "T", "n": i} for i in range(150)), uuid.uuid4())
        self.assertTrue(until(lambda: len(delivered) >= 150))
        time.sleep(0.2)  # late duplicates must not produce extra deliveries
        self.assertEqual(delivered, list(range(150)))
        self.assertGreater(up.stats["dropped"], 0)
        self.assertGreater(up.stats["duplicated"], 0)

    def test_corrupted_packets_are_never_delivered(self):
        received = []
        originals = [os.urandom(300) for _ in range(80)]
        sender = self.node()
        receiver = self.node(lambda peer, stream, msg: received.append(msg["data"]))
        link = self.fault(sender, corrupt=0.25, seed=3)
        self.fault(receiver, corrupt=0.25, seed=4)
        sender.send_many(("127.0.0.1", receiver.port),
                         ({"type": "T", "data": data} for data in originals), uuid.uuid4())
        self.assertTrue(until(lambda: len(received) >= 80))
        time.sleep(0.2)
        self.assertEqual(received, originals)  # AES-GCM + AAD rejected every damaged packet
        self.assertGreater(link.stats["corrupted"], 0)

    def test_retry_budget_exhausted_raises_clear_error(self):
        sender = self.node(ack_timeout=0.03, max_retries=3)
        receiver = self.node()
        self.fault(sender, loss=1.0, seed=5)
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "not acknowledged"):
            sender.send(("127.0.0.1", receiver.port), {"type": "T"}, uuid.uuid4())
        self.assertLess(time.monotonic() - started, 3)

    def test_chat_stream_progresses_while_lossy_file_stream_is_slow(self):
        file_stream, chat_stream = uuid.uuid4(), uuid.uuid4()
        file_count, chat_seen = [0], []

        def handler(peer, stream, message):
            if stream == file_stream:
                time.sleep(0.02)  # slow file processing
                file_count[0] += 1
            else:
                chat_seen.append(message["text"])

        sender = self.node()
        receiver = self.node(handler)
        self.fault(sender, loss=0.2, reorder=0.1, seed=6)
        self.fault(receiver, loss=0.2, reorder=0.1, seed=7)
        peer = ("127.0.0.1", receiver.port)
        worker = threading.Thread(target=sender.send_many, daemon=True, args=(
            peer, ({"type": "F", "n": i, "data": b"x" * 500} for i in range(100)), file_stream))
        worker.start()
        time.sleep(0.3)
        sender.send(peer, {"type": "CHAT", "text": "hello"}, chat_stream)
        self.assertTrue(until(lambda: chat_seen, seconds=1.5), "chat was blocked by file stream")
        self.assertLess(file_count[0], 100, "file finished first, so this proved nothing")
        worker.join(timeout=15)
        self.assertTrue(until(lambda: file_count[0] == 100, seconds=10))


class EndToEndLossyFileTests(unittest.TestCase):
    """Real TCP login + UDP + file transfer with faults on server and both clients.

    Written from the API used in scripts/smoke_test.py.
    """

    def test_file_hash_matches_and_chat_continues_under_loss(self):
        from app.client import CollaborationClient
        from app.server.server import CollaborationServer

        key = os.urandom(32)
        server = CollaborationServer("127.0.0.1", 0, 0, key)
        alice = bob = None
        links = []
        try:
            with tempfile.TemporaryDirectory() as temp:
                alice = CollaborationClient("alice", tcp_port=server.tcp_port,
                                            udp_port=server.udp_port, key=key,
                                            download_dir=Path(temp) / "alice")
                bob = CollaborationClient("bob", tcp_port=server.tcp_port,
                                          udp_port=server.udp_port, key=key,
                                          download_dir=Path(temp) / "bob")
                self.assertTrue(until(lambda: "bob" in alice.get_state()["online"]))
                for seed, node in enumerate((server.udp, alice.udp, bob.udp), start=1):
                    node.ack_timeout, node.max_retries = 0.1, 40
                    links.append(FaultyLink(node, loss=0.15, dup=0.05, reorder=0.1,
                                            delay=0.002, jitter=0.002, seed=seed))

                data = os.urandom(60 * 1024)
                path = Path(temp) / "source.bin"
                path.write_bytes(data)
                uploader = threading.Thread(target=alice.send_file, args=(path, "bob"), daemon=True)
                uploader.start()
                time.sleep(0.2)
                alice.send_chat("bob", "chat during lossy file transfer")

                self.assertTrue(until(lambda: any(
                    e.get("text") == "chat during lossy file transfer"
                    for e in bob.get_state()["events"]), seconds=30), "chat not delivered")
                self.assertTrue(until(lambda: any(
                    e.get("type") == "FILE_COMPLETE" for e in bob.get_state()["events"]),
                    seconds=60), "file not completed")
                done = next(e for e in bob.get_state()["events"] if e.get("type") == "FILE_COMPLETE")
                self.assertEqual(sha256(Path(done["path"]).read_bytes()).hexdigest(),
                                 sha256(data).hexdigest())
                self.assertTrue(until(lambda: any(
                    e.get("type") == "FILE_RECEIPT" and e.get("status") == "ok"
                    for e in alice.get_state()["events"]), seconds=30), "receipt not delivered")
                for name, link in zip(("server", "alice", "bob"), links):
                    print(f"[lossy e2e] {name}: {link.stats}")
        finally:
            for link in links:
                link.close()
            for client in (alice, bob):
                if client:
                    client.close()
            server.close()


if __name__ == "__main__":
    unittest.main()