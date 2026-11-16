import os
import threading
import time
import unittest
import uuid

from app.common.protocol import ACK, decode_frame
from app.transport.reliable_udp import ReliableUDP


class FlowControlTests(unittest.TestCase):
    def test_ack_credit_bounds_slow_receiver(self):
        key = os.urandom(32)
        values = []
        release = threading.Event()

        def consume(_peer, _stream, message):
            if message["index"] == 0:
                release.wait(3)
            values.append(message["index"])

        receiver = ReliableUDP("127.0.0.1", 0, key, consume)
        self.addCleanup(receiver.close)
        receiver.receive_capacity = 4
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None, ack_timeout=0.1, max_retries=30)
        self.addCleanup(sender.close)
        peer = ("127.0.0.1", receiver.port)
        stream = uuid.uuid4()
        emit = receiver._sendto
        dropped = False

        def lose_first_ack(raw, address):
            nonlocal dropped
            if not dropped and decode_frame(raw)[0] == ACK:
                dropped = True
                return
            emit(raw, address)

        receiver._sendto = lose_first_ack
        errors = []

        def transmit():
            try:
                sender.send_many(peer, ({"index": i} for i in range(32)), stream)
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=transmit)
        worker.start()
        high_water = 0
        try:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with receiver.lock:
                    high_water = max(high_water, max(receiver.in_work.values(), default=0))
                state = sender.congestion.get((peer, stream))
                if state and state.flow_waits:
                    break
                time.sleep(0.01)
            self.assertEqual(high_water, receiver.receive_capacity)
            self.assertGreater(state.flow_waits, 0)
        finally:
            release.set()
            worker.join(timeout=6)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        deadline = time.monotonic() + 2
        while len(values) < 32 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(values, list(range(32)))
        self.assertEqual(state.acknowledgements, 32)

    def test_loss_halves_congestion_window(self):
        key = os.urandom(32)
        receiver = ReliableUDP("127.0.0.1", 0, key, lambda *_: None)
        self.addCleanup(receiver.close)
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None, ack_timeout=0.1)
        self.addCleanup(sender.close)
        peer, stream = ("127.0.0.1", receiver.port), uuid.uuid4()
        emit = sender._sendto

        def lose_initial(raw, address):
            sender._sendto = emit

        sender._sendto = lose_initial
        sender.send(peer, {"sample": "one lost DATA"}, stream)
        state = sender.congestion[(peer, stream)]
        self.assertGreaterEqual(state.timeouts, 1)
        self.assertLessEqual(state.window, 2)
