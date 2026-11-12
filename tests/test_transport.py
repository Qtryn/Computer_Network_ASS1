"""Loopback transport tests that emulate a dropped datagram and reordering."""
import os
import threading
import time
import unittest
import uuid

from app.common.protocol import DATA, decode_frame, encode_frame
from app.transport.reliable_udp import ReliableUDP


class TransportTests(unittest.TestCase):
    def test_ack_socket_error_does_not_drop_accepted_packet(self):
        key, delivered = os.urandom(32), []
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None, ack_timeout=0.02)
        receiver = ReliableUDP("127.0.0.1", 0, key, lambda p, s, m: delivered.append(m))
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        original = receiver._sendto
        attempts = []

        def fail_once(raw, peer):
            attempts.append(raw)
            if len(attempts) == 1:
                raise OSError("simulated ACK send failure")
            original(raw, peer)

        receiver._sendto = fail_once
        sender.send(("127.0.0.1", receiver.port), {"ok": True}, uuid.uuid4())
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(delivered, [{"ok": True}])

    def test_invalid_oversized_and_malformed_udp_do_not_stop_listener(self):
        key, delivered = os.urandom(32), []
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None)
        receiver = ReliableUDP("127.0.0.1", 0, key, lambda p, s, m: delivered.append(m))
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        peer, stream = ("127.0.0.1", receiver.port), uuid.uuid4()
        header = encode_frame(DATA, uuid.uuid4(), stream, 0)
        for raw in (b"bad", b"x" * 5000, header + sender.crypto.encrypt(b"\x00\x01{", header)):
            sender._sendto(raw, peer)
        sender.send(peer, {"ok": True}, stream)
        deadline = time.monotonic() + 1
        while not delivered and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(delivered, [{"ok": True}])

    def test_oversized_message_does_not_consume_sequence(self):
        key, delivered = os.urandom(32), []
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None)
        receiver = ReliableUDP("127.0.0.1", 0, key, lambda p, s, m: delivered.append(m))
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        peer, stream = ("127.0.0.1", receiver.port), uuid.uuid4()
        with self.assertRaisesRegex(ValueError, "too large"):
            sender.send(peer, {"data": b"x" * 5000}, stream)
        sender.send(peer, {"ok": True}, stream)
        deadline = time.monotonic() + 1
        while not delivered and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(delivered, [{"ok": True}])

    def test_lost_all_acks_recovers_without_duplicate_delivery(self):
        key, delivered = os.urandom(32), []
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None,
                             ack_timeout=0.02, max_retries=1)
        receiver = ReliableUDP("127.0.0.1", 0, key,
                               lambda p, s, m: delivered.append(m["number"]))
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        original = receiver._sendto
        receiver._sendto = lambda *_: None
        peer, stream = ("127.0.0.1", receiver.port), uuid.uuid4()
        with self.assertRaises(TimeoutError):
            sender.send(peer, {"number": 0}, stream)
        with self.assertRaises(TimeoutError):
            sender.send_many(peer, [], stream)
        receiver._sendto = original
        sender.send(peer, {"number": 1}, stream)
        deadline = time.monotonic() + 1
        while len(delivered) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(delivered, [0, 1])

    def test_retry_exhaustion_recovers_gap_and_ignores_late_duplicates(self):
        key, delivered, saved = os.urandom(32), [], []
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None,
                             ack_timeout=0.02, max_retries=1)
        receiver = ReliableUDP("127.0.0.1", 0, key,
                               lambda p, s, m: delivered.append(m["number"]))
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        peer, stream = ("127.0.0.1", receiver.port), uuid.uuid4()
        original = sender._sendto

        def drop_zero(raw, address):
            if decode_frame(raw)[3] == 0:
                saved.append(raw)
            else:
                original(raw, address)

        sender._sendto = drop_zero
        with self.assertRaises(TimeoutError):
            sender.send_many(peer, [{"number": 0}, {"number": 1}], stream)
        self.assertEqual(delivered, [])
        sender._sendto = original
        sender.send(peer, {"number": 2}, stream)
        deadline = time.monotonic() + 2
        while len(delivered) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(delivered, [0, 1, 2])
        original(saved[0], peer)  # Delayed packet must not deliver twice.
        time.sleep(0.05)
        self.assertEqual(delivered, [0, 1, 2])

    def test_dropped_first_packet_is_retransmitted_and_delivered_in_order(self):
        key = os.urandom(32)
        delivered = []
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None,
                             ack_timeout=0.08, max_retries=10)
        receiver = ReliableUDP("127.0.0.1", 0, key,
                               lambda address, stream, message: delivered.append(message["number"]),
                               ack_timeout=0.08, max_retries=10)
        original_send = sender._sendto
        dropped = set()

        def simulated_network(raw, address):
            kind, packet_id, stream, sequence, body = decode_frame(raw)
            if kind == DATA and sequence == 0 and sequence not in dropped:
                dropped.add(sequence)
                return  # Packet zero drops; packets 1..n arrive first.
            original_send(raw, address)

        sender._sendto = simulated_network
        try:
            stream_id = uuid.uuid4()
            messages = ({"type": "TEST", "number": index} for index in range(12))
            sender.send_many(("127.0.0.1", receiver.port), messages, stream_id)
            deadline = time.monotonic() + 2
            while len(delivered) != 12 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(delivered, list(range(12)))
            self.assertIn(0, dropped)
        finally:
            sender.close()
            receiver.close()

    def test_distinct_streams_do_not_block_each_other(self):
        key = os.urandom(32)
        started_file = threading.Event()
        completed_chat = threading.Event()
        first_stream = uuid.uuid4()
        second_stream = uuid.uuid4()

        def handler(peer, stream, message):
            if stream == first_stream:
                started_file.set()
                time.sleep(0.35)  # Simulates slow file processing.
            elif stream == second_stream:
                completed_chat.set()

        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None)
        receiver = ReliableUDP("127.0.0.1", 0, key, handler)
        try:
            peer = ("127.0.0.1", receiver.port)
            sender.send(peer, {"type": "TEST"}, first_stream)
            self.assertTrue(started_file.wait(2))
            sender.send(peer, {"type": "CHAT", "text": "not blocked"}, second_stream)
            self.assertTrue(completed_chat.wait(0.2))
        finally:
            sender.close()
            receiver.close()


if __name__ == "__main__":
    unittest.main()
