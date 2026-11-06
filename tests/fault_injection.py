"""In-process network fault injection for ReliableUDP.

Wraps the `_sendto` hook that Member 2 provides "for fault-injection tests", so
no production code has to change. Works for a standalone ReliableUDP and for the
`.udp` attribute of CollaborationServer / CollaborationClient.

    link = FaultyLink(client.udp, loss=0.2, dup=0.05, reorder=0.1, seed=1)
    ...
    print(link.stats)       # copy these numbers into the test report
    link.close()
"""
import random
import threading


class FaultyLink:
    def __init__(self, udp, loss=0.0, dup=0.0, reorder=0.0, corrupt=0.0,
                 delay=0.0, jitter=0.0, reorder_delay=0.05, seed=None):
        self.loss, self.dup, self.reorder, self.corrupt = loss, dup, reorder, corrupt
        self.delay, self.jitter, self.reorder_delay = delay, jitter, reorder_delay
        self.rng = random.Random(seed)
        self.lock = threading.Lock()
        self.timers = set()
        self.closed = False
        self.stats = {"sent": 0, "dropped": 0, "duplicated": 0,
                      "reordered": 0, "corrupted": 0, "delivered": 0}
        self._real_sendto = udp._sendto   # bound method, captured before patching
        udp._sendto = self.send

    def _roll(self, probability):
        return probability > 0 and self.rng.random() < probability

    def send(self, raw, peer):
        with self.lock:
            if self.closed:
                return
            self.stats["sent"] += 1
            if self._roll(self.loss):
                self.stats["dropped"] += 1
                return
            copies = 1
            if self._roll(self.dup):
                copies = 2
                self.stats["duplicated"] += 1
            plan = []
            for _ in range(copies):
                data = raw
                if self._roll(self.corrupt):
                    index = self.rng.randrange(len(data))
                    data = data[:index] + bytes([data[index] ^ 0xFF]) + data[index + 1:]
                    self.stats["corrupted"] += 1
                wait = self.delay + (self.rng.uniform(-self.jitter, self.jitter) if self.jitter else 0)
                if self._roll(self.reorder):
                    wait += self.reorder_delay
                    self.stats["reordered"] += 1
                plan.append((data, max(0.0, wait)))
        for data, wait in plan:
            if wait <= 0:
                self._deliver(data, peer)
            else:
                timer = threading.Timer(wait, self._fire, args=(data, peer))
                timer.daemon = True
                with self.lock:
                    self.timers.add(timer)
                timer.start()

    def _fire(self, data, peer):
        self._deliver(data, peer)
        with self.lock:
            self.timers = {t for t in self.timers if t.is_alive() and t is not threading.current_thread()}

    def _deliver(self, data, peer):
        if self.closed:
            return
        try:
            self._real_sendto(data, peer)
            with self.lock:
                self.stats["delivered"] += 1
        except OSError:
            pass  # socket already closed at test teardown

    def close(self):
        with self.lock:
            self.closed = True
            timers, self.timers = list(self.timers), set()
        for timer in timers:
            timer.cancel()