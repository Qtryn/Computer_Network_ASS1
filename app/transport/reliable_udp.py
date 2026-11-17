"""Reliable UDP with independent streams, bounded receive credit and AIMD."""
import queue
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from app.common.config import ACK_TIMEOUT, MAX_DATAGRAM, MAX_RETRIES, WINDOW_SIZE
from app.common.protocol import ACK, DATA, HEADER, decode_frame, decode_message, encode_frame, encode_message
from app.security.crypto import CryptoBox, OVERHEAD

CHAT_STREAM = uuid.UUID("00000000-0000-0000-0000-000000000001")


@dataclass
class FlowState:
    window: float
    credit: int
    acknowledgements: int = 0
    timeouts: int = 0
    flow_waits: int = 0
    credit_revision: int = -1


@dataclass
class Acknowledgement:
    credit: int
    revision: int = -1
    ready: threading.Event = field(default_factory=threading.Event)


class ReliableUDP:
    def __init__(self, bind_host, bind_port, key, on_message,
                 window=WINDOW_SIZE, ack_timeout=ACK_TIMEOUT, max_retries=MAX_RETRIES,
                 flow_timeout=10, receive_capacity=None):
        if not 1 <= window <= 65535 or ack_timeout <= 0 or max_retries < 0 or flow_timeout <= 0:
            raise ValueError("Invalid transport window or timeout")
        capacity = max(16, window * 2) if receive_capacity is None else receive_capacity
        if not 1 <= capacity <= 65535:
            raise ValueError("Invalid receive capacity")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind_host, bind_port))
        self.sock.settimeout(0.2)
        self.crypto = CryptoBox(key)
        self.on_message = on_message
        self.window = window
        self.ack_timeout = ack_timeout
        self.max_retries = max_retries
        self.flow_timeout = flow_timeout
        self.running = threading.Event()
        self.running.set()
        self.lock = threading.Lock()
        self.pending_acks = {}  # uuid -> (Event, peer, stream, sequence)
        self.out_seq = {}  # (peer, stream UUID) -> next sequence
        self.send_locks = {}  # serialize producers only within the same stream
        self.recovery = {}  # failed stream -> unacknowledged frames (bounded by window)
        self.congestion = {}  # (peer, stream) -> FlowState
        self.last_acked = {}  # one unchanged DATA per stream for zero-credit probes
        self.receive_capacity = capacity
        self.in_seq = {}  # (peer, stream UUID) -> next sequence to deliver
        self.in_buffers = {}  # (peer, stream UUID) -> {sequence: (message, peer)}
        self.in_work = {}  # queued or active application messages per stream
        self.ack_revisions = {}  # reject stale/reordered credit snapshots at the sender
        self.seen = set()
        self.seen_order = deque()
        self.stream_queues = {}  # stream key -> Queue, with its own event worker
        self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.recv_thread.start()

    @property
    def port(self):
        return self.sock.getsockname()[1]

    def _next_seq(self, peer, stream):
        with self.lock:
            key = (peer, stream)
            sequence = self.out_seq.get(key, 0)
            self.out_seq[key] = sequence + 1
            return sequence

    def _sendto(self, raw, peer):
        """Single overridable socket send point for fault-injection tests."""
        self.sock.sendto(raw, peer)

    def send(self, peer, message, stream=CHAT_STREAM):
        self.send_many(peer, [message], stream)

    def send_many(self, peer, messages, stream, on_progress=None):
        """Sliding-window transfer; acknowledgements are per UDP packet/hop.

        The other endpoint's ACK does NOT prove that the app finally saved a file.
        A FILE_COMPLETE event at application level is the end-to-end confirmation.
        """
        if isinstance(stream, str):
            stream = uuid.UUID(stream)
        if not isinstance(stream, uuid.UUID):
            raise TypeError("stream must be UUID or UUID string")
        with self.lock:
            send_lock = self.send_locks.setdefault((peer, stream), threading.Lock())
        with send_lock:
            self._send_many(peer, messages, stream, on_progress)

    def _send_many(self, peer, messages, stream, on_progress):
        if not self.running.is_set():
            raise ConnectionError("UDP transport was stopped")
        iterator = iter(messages)
        outstanding = {}  # packet_id -> [raw, event, last_sent, retries]
        route = (peer, stream)
        congestion = self.congestion.setdefault(route, FlowState(1, 1))
        last_loss = 0.0
        flow_since = None
        empty = object()
        waiting = empty
        # Replay identical frames before allocating new sequences. A timeout means
        # delivery is uncertain; late duplicates remain safe at the receiver.
        recovery = deque(self.recovery.pop((peer, stream), []))
        exhausted = False
        confirmed = 0
        try:
            while (recovery or not exhausted or outstanding) and self.running.is_set():
                limit = min(self.window, int(congestion.window), congestion.credit)
                if not limit and not outstanding:
                    if not recovery and waiting is empty and not exhausted:
                        try:
                            waiting = next(iterator)
                        except StopIteration:
                            exhausted = True
                    if exhausted and not recovery:
                        break
                    flow_since = flow_since or time.monotonic()
                    if time.monotonic() - flow_since >= self.flow_timeout:
                        raise TimeoutError("Receiver credit did not reopen")
                    raw = self.last_acked[route]
                    _, packet_id, _, sequence, _ = decode_frame(raw)
                    probe = Acknowledgement(0)
                    with self.lock:
                        self.pending_acks[packet_id] = (probe, peer, stream, sequence)
                    try:
                        # Repeat accepted DATA, not a new sequence. Its ACK refreshes
                        # credit even if a previous update was lost; the app deduplicates.
                        self._sendto(raw, peer)
                        congestion.flow_waits += 1
                        probe.ready.wait(self.ack_timeout)
                        if probe.ready.is_set() and probe.revision > congestion.credit_revision:
                            congestion.credit = probe.credit
                            congestion.credit_revision = probe.revision
                        if not congestion.credit:
                            time.sleep(min(self.ack_timeout, .05))
                    finally:
                        with self.lock:
                            self.pending_acks.pop(packet_id, None)
                    continue
                if congestion.credit:
                    flow_since = None
                while not exhausted and len(outstanding) < limit:
                    if recovery:
                        packet_id, raw = recovery.popleft()
                        is_new = False
                    else:
                        try:
                            message = next(iterator) if waiting is empty else waiting
                            waiting = empty
                        except StopIteration:
                            exhausted = True
                            break
                        payload = encode_message(message)
                        # Validate before consuming a sequence number.
                        if HEADER.size + OVERHEAD + len(payload) > MAX_DATAGRAM:
                            raise ValueError("UDP datagram too large")
                        packet_id = uuid.uuid4()
                        sequence = self._next_seq(peer, stream)
                        header = encode_frame(DATA, packet_id, stream, sequence)
                        raw = header + self.crypto.encrypt(payload, header)
                        is_new = True
                    ack = Acknowledgement(self.window)
                    with self.lock:
                        self.pending_acks[packet_id] = (ack, peer, stream, decode_frame(raw)[3])
                    outstanding[packet_id] = [raw, ack, time.monotonic(), 0, is_new]
                    self._sendto(raw, peer)

                any_completed = False
                for packet_id, state in list(outstanding.items()):
                    raw, ack, sent_at, retries, is_new = state
                    if ack.ready.is_set():
                        del outstanding[packet_id]
                        with self.lock:
                            self.pending_acks.pop(packet_id, None)
                        confirmed += int(is_new)
                        any_completed = True
                        if ack.revision > congestion.credit_revision:
                            congestion.credit = ack.credit
                            congestion.credit_revision = ack.revision
                        self.last_acked[route] = raw
                        congestion.acknowledgements += 1
                        if not retries:
                            congestion.window = min(self.window, congestion.window + 1 / congestion.window)
                        if on_progress and is_new:
                            on_progress(confirmed)
                    elif time.monotonic() - sent_at >= self.ack_timeout:
                        now = time.monotonic()
                        if now - last_loss >= self.ack_timeout:
                            if congestion.credit:
                                congestion.window = max(1, congestion.window / 2)
                                congestion.timeouts += 1
                            else:
                                congestion.flow_waits += 1
                            last_loss = now
                        if not congestion.credit:
                            flow_since = flow_since or now
                            if now - flow_since >= self.flow_timeout:
                                raise TimeoutError("Receiver credit did not reopen")
                        elif retries >= self.max_retries:
                            raise TimeoutError(f"UDP packet {packet_id} not acknowledged; delivery uncertain")
                        self._sendto(raw, peer)
                        state[2] = time.monotonic()
                        state[3] += int(bool(congestion.credit))
                if not any_completed:
                    time.sleep(0.01)
        finally:
            if self.running.is_set() and (outstanding or recovery):
                self.recovery[(peer, stream)] = [
                    (packet_id, state[0]) for packet_id, state in outstanding.items()
                ] + list(recovery)
            with self.lock:
                for packet_id in outstanding:
                    self.pending_acks.pop(packet_id, None)
        if not self.running.is_set():
            raise ConnectionError("UDP transport was stopped")

    def _receive_loop(self):
        while self.running.is_set():
            try:
                raw, peer = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                kind, packet_id, stream, sequence, ciphertext = decode_frame(raw)
                if len(raw) > MAX_DATAGRAM:
                    continue
                if kind == ACK:
                    with self.lock:
                        pending = self.pending_acks.get(packet_id)
                    if pending and (peer, stream, sequence) == pending[1:]:
                        credit = self.crypto.decrypt(ciphertext, raw[:HEADER.size])
                        if len(credit) == 6:
                            revision = int.from_bytes(credit[2:], "big")
                            if revision > pending[0].revision:
                                pending[0].credit = int.from_bytes(credit[:2], "big")
                                pending[0].revision = revision
                            pending[0].ready.set()
                    continue
                header = raw[:len(raw) - len(ciphertext)]
                message = decode_message(self.crypto.decrypt(ciphertext, header))
                with self.lock:
                    duplicate = (peer, packet_id) in self.seen
                if not duplicate:
                    if not self._accept_in_order(peer, stream, sequence, message):
                        continue  # The sender will retry when the receiver has room.
                    with self.lock:
                        self.seen.add((peer, packet_id))
                        self.seen_order.append((peer, packet_id))
                        if len(self.seen_order) > 10000:
                            self.seen.discard(self.seen_order.popleft())
                with self.lock:
                    route = (peer, stream)
                    credit = self.receive_capacity - self.in_work.get(route, 0) - len(self.in_buffers.get(route, {}))
                    revision = self.ack_revisions.get(route, 0)
                    self.ack_revisions[route] = revision + 1
                header = encode_frame(ACK, packet_id, stream, sequence)
                payload = credit.to_bytes(2, "big") + revision.to_bytes(4, "big")
                self._sendto(header + self.crypto.encrypt(payload, header), peer)
            except (ValueError, KeyError, UnicodeError, TypeError):
                # Ignore malformed UDP datagrams without killing the receiving thread.
                continue
            except Exception as exc:
                # For a student project, keep listener alive; do not log decrypted content.
                print(f"[transport] Ignored packet/error: {type(exc).__name__}")

    def _accept_in_order(self, peer, stream, sequence, message):
        key = (peer, stream)
        ready = []
        with self.lock:
            expected = self.in_seq.get(key, 0)
            if sequence < expected:
                return True
            buffered = self.in_buffers.get(key, {})
            if sequence in buffered:
                return True
            used = self.in_work.get(key, 0) + len(buffered)
            if used >= self.receive_capacity - int(sequence != expected):
                return False
            buffer = self.in_buffers.setdefault(key, {})
            buffer[sequence] = message
            while expected in buffer:
                ready.append(buffer.pop(expected))
                expected += 1
            self.in_seq[key] = expected
            if not buffer:
                self.in_buffers.pop(key, None)
            if ready:
                task_queue = self.stream_queues.get(key)
                if task_queue is None:
                    task_queue = queue.Queue(maxsize=self.receive_capacity)
                    self.stream_queues[key] = task_queue
                    threading.Thread(target=self._stream_worker,
                                     args=(key, task_queue), daemon=True).start()
                for item in ready:
                    self.in_work[key] = self.in_work.get(key, 0) + 1
                    task_queue.put((peer, stream, item))
            return True

    def _stream_worker(self, key, task_queue):
        while self.running.is_set():
            try:
                peer, stream, message = task_queue.get(timeout=3.0)
            except queue.Empty:
                with self.lock:
                    if task_queue.empty() and self.stream_queues.get(key) is task_queue:
                        self.stream_queues.pop(key, None)
                        return
                continue
            try:
                if message is None:
                    return
                if self.running.is_set():
                    self.on_message(peer, stream, message)
            except Exception as exc:
                print(f"[transport] Handler error: {type(exc).__name__}")
            finally:
                if message is not None:
                    with self.lock:
                        self.in_work[key] -= 1
                        if not self.in_work[key]:
                            del self.in_work[key]
                task_queue.task_done()

    def close(self):
        self.running.clear()
        self.sock.close()
        self.recv_thread.join(timeout=1.0)
        with self.lock:
            for tasks in self.stream_queues.values():
                while True:
                    try:
                        tasks.get_nowait()
                        tasks.task_done()
                    except queue.Empty:
                        break
                tasks.put((None, None, None))
            self.stream_queues.clear()
            self.in_buffers.clear()
            self.recovery.clear()
            self.last_acked.clear()
