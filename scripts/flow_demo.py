"""Real loopback AIMD/credit demonstration; no packet capture or fake output."""
import json
import os
import threading
import time
import uuid

from app.common.protocol import DATA, decode_frame
from app.transport.reliable_udp import ReliableUDP


def main():
    key, stream, release = os.urandom(32), uuid.uuid4(), threading.Event()
    release.set()
    received, errors = [], []

    def consume(_peer, _stream, message):
        if not release.wait(3):
            raise TimeoutError("Demo receiver was not released")
        received.append(message["index"])

    receiver = ReliableUDP("127.0.0.1", 0, key, consume, receive_capacity=4)
    sender = ReliableUDP("127.0.0.1", 0, key, lambda *_: None, ack_timeout=.05)
    peer = ("127.0.0.1", receiver.port)

    def metrics(phase):
        state = sender.congestion[(peer, stream)]
        print(json.dumps({"phase": phase, "cwnd": round(state.window, 3),
            "acknowledgements": state.acknowledgements, "timeouts": state.timeouts,
            "receiver_credit": state.credit, "flow_waits": state.flow_waits}), flush=True)

    worker = None
    try:
        sender.send_many(peer, ({"index": i} for i in range(8)), stream)
        metrics("continuous ACKs")
        original, dropped = sender._sendto, []

        def lose_once(raw, destination):
            if decode_frame(raw)[0] == DATA and not dropped:
                dropped.append(raw)
            else:
                original(raw, destination)

        sender._sendto = lose_once
        sender.send(peer, {"index": 8}, stream)
        sender._sendto = original
        metrics("one DATA lost")
        assert sender.congestion[(peer, stream)].timeouts > 0
        sender.send_many(peer, ({"index": i} for i in range(9, 17)), stream)
        metrics("network recovered")
        release.clear()

        def transmit():
            try:
                sender.send_many(peer, ({"index": i} for i in range(17, 25)), stream)
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=transmit)
        worker.start()
        deadline = time.monotonic() + 2
        while not sender.congestion[(peer, stream)].flow_waits and time.monotonic() < deadline:
            time.sleep(.01)
        metrics("receiver backpressure")
        assert sender.congestion[(peer, stream)].flow_waits > 0
        with receiver.lock:
            assert receiver.in_work.get((("127.0.0.1", sender.port), stream), 0) <= receiver.receive_capacity
        release.set()
        worker.join(3)
        assert not worker.is_alive() and not errors, errors
        deadline = time.monotonic() + 1
        while len(received) < 25 and time.monotonic() < deadline:
            time.sleep(.01)
        assert received == list(range(25)), received
        metrics("receiver recovered")
        print("PASS: 25 messages received once, in order; AIMD and bounded receiver credit")
    finally:
        release.set()
        sender.close()
        receiver.close()
        if worker:
            worker.join(2)


if __name__ == "__main__":
    main()
