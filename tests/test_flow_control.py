import os
import threading
import time
import unittest
import uuid

from app.common.protocol import ACK, decode_frame
from app.transport.reliable_udp import ReliableUDP


class FlowControlTests(unittest.TestCase):
    def test_window_grows_after_acks_but_never_exceeds_configured_maximum(self):
        key = os.urandom(32)
        receiver = ReliableUDP("127.0.0.1", 0, key, lambda *_: None)
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None, window=4)
        self.addCleanup(receiver.close)
        self.addCleanup(sender.close)
        peer, stream = ("127.0.0.1", receiver.port), uuid.uuid4()
        sender.send(peer, {"index": 0}, stream)
        initial = sender.congestion[(peer, stream)].window
        sender.send_many(peer, ({"index": i} for i in range(1, 40)), stream)
        state = sender.congestion[(peer, stream)]
        self.assertGreater(state.window, initial)
        self.assertLessEqual(state.window, sender.window)

    def test_zero_credit_pauses_new_data_without_exhausting_network_retries(self):
        key, release, reached = os.urandom(32), threading.Event(), threading.Event()
        values, errors, sequences = [], [], []

        def consume(_peer, _stream, message):
            reached.set()
            release.wait(3)
            values.append(message["index"])

        receiver = ReliableUDP("127.0.0.1", 0, key, consume)
        receiver.receive_capacity = 1
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None,
                             ack_timeout=0.03, max_retries=1)
        self.addCleanup(receiver.close)
        self.addCleanup(sender.close)
        original = sender._sendto

        def observe(raw, peer):
            sequences.append(decode_frame(raw)[3])
            original(raw, peer)

        sender._sendto = observe
        peer, stream = ("127.0.0.1", receiver.port), uuid.uuid4()

        def transmit():
            try:
                sender.send_many(peer, ({"index": i} for i in range(4)), stream)
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=transmit)
        worker.start()
        self.assertTrue(reached.wait(1))
        try:
            time.sleep(0.25)  # Longer than the network retry budget.
            self.assertTrue(worker.is_alive(), errors)
            self.assertEqual(set(sequences), {0}, "Zero credit must not allocate new DATA")
            self.assertEqual(sender.congestion[(peer, stream)].timeouts, 0)
        finally:
            release.set()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        deadline = time.monotonic() + 1
        while len(values) != 4 and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(values, list(range(4)))

    def test_window_recovers_after_loss_and_chat_bypasses_a_lost_file_stream(self):
        key, file_stream, chat_stream = os.urandom(32), uuid.uuid4(), uuid.uuid4()
        chats, errors = threading.Event(), []
        receiver = ReliableUDP("127.0.0.1", 0, key,
                              lambda _p, stream, _m: chats.set() if stream == chat_stream else None)
        sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None, ack_timeout=.05)
        self.addCleanup(receiver.close)
        self.addCleanup(sender.close)
        peer = ("127.0.0.1", receiver.port)
        sender.send_many(peer, ({"index": i} for i in range(12)), file_stream)
        before = sender.congestion[(peer, file_stream)].window
        original, loss = sender._sendto, threading.Event()
        loss.set()

        def lose_file(raw, destination):
            if decode_frame(raw)[2] != file_stream or not loss.is_set():
                original(raw, destination)

        sender._sendto = lose_file

        def transmit():
            try:
                sender.send(peer, {"index": 12}, file_stream)
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=transmit)
        worker.start()
        try:
            deadline = time.monotonic() + 1
            while not sender.congestion[(peer, file_stream)].timeouts and time.monotonic() < deadline:
                time.sleep(.005)
            reduced = sender.congestion[(peer, file_stream)].window
            self.assertLess(reduced, before)
            sender.send(peer, {"type": "CHAT"}, chat_stream)
            self.assertTrue(chats.wait(.2))
        finally:
            loss.clear()
            worker.join(3)
        self.assertEqual(errors, [])
        sender.send_many(peer, ({"index": i} for i in range(13, 25)), file_stream)
        self.assertGreater(sender.congestion[(peer, file_stream)].window, reduced)

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
