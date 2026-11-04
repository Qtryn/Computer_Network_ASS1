"""Loopback transport tests that emulate a dropped datagram and reordering."""
import os
import threading
import time
import unittest
import uuid

from app.common.protocol import DATA, decode_frame
from app.transport.reliable_udp import ReliableUDP


class TransportTests(unittest.TestCase):
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
