"""Member 2: small reliable UDP transport, using raw UDP sockets.

Features already present: packet sequence/ACK, retransmit missing packets,
fixed sliding window, in-order delivery per stream, duplicate suppression,
independent worker per stream (chat is not blocked by file processing).

Not implemented: TCP-like BBR/CUBIC congestion control; see docs/member_tasks.md.
"""
import queue
import socket
import threading
import time
import uuid
from collections import deque

from app.common.config import ACK_TIMEOUT, MAX_DATAGRAM, MAX_RETRIES, WINDOW_SIZE
from app.common.protocol import ACK, DATA, HEADER, decode_frame, decode_message, encode_frame, encode_message
from app.security.crypto import CryptoBox, OVERHEAD

CHAT_STREAM = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ReliableUDP:
    def __init__(self, bind_host, bind_port, key, on_message,
                 window=WINDOW_SIZE, ack_timeout=ACK_TIMEOUT, max_retries=MAX_RETRIES):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind_host, bind_port))
        self.sock.settimeout(0.2)
        self.crypto = CryptoBox(key)
        self.on_message = on_message
        self.window = window
        self.ack_timeout = ack_timeout
        self.max_retries = max_retries
        self.running = threading.Event()
        self.running.set()
        self.lock = threading.Lock()
        self.pending_acks = {}  # uuid -> (Event, peer, stream, sequence)
        self.out_seq = {}  # (peer, stream UUID) -> next sequence
        self.send_locks = {}  # serialize producers only within the same stream
        self.recovery = {}  # failed stream -> unacknowledged frames (bounded by window)
        self.in_seq = {}  # (peer, stream UUID) -> next sequence to deliver
        self.in_buffers = {}  # (peer, stream UUID) -> {sequence: (message, peer)}
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
        # Replay identical frames before allocating new sequences. A timeout means
        # delivery is uncertain; late duplicates remain safe at the receiver.
        recovery = deque(self.recovery.pop((peer, stream), []))
        exhausted = False
        confirmed = 0
        try:
            while (recovery or not exhausted or outstanding) and self.running.is_set():
                while not exhausted and len(outstanding) < self.window:
                    if recovery:
                        packet_id, raw = recovery.popleft()
                        is_new = False
                    else:
                        try:
                            message = next(iterator)
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
                    ack = threading.Event()
                    with self.lock:
                        self.pending_acks[packet_id] = (ack, peer, stream, decode_frame(raw)[3])
                    outstanding[packet_id] = [raw, ack, time.monotonic(), 0, is_new]
                    self._sendto(raw, peer)

                any_completed = False
                for packet_id, state in list(outstanding.items()):
                    raw, ack, sent_at, retries, is_new = state
                    if ack.is_set():
                        del outstanding[packet_id]
                        with self.lock:
                            self.pending_acks.pop(packet_id, None)
                        confirmed += int(is_new)
                        any_completed = True
                        if on_progress and is_new:
                            on_progress(confirmed)
                    elif time.monotonic() - sent_at >= self.ack_timeout:
                        if retries >= self.max_retries:
                            raise TimeoutError(f"UDP packet {packet_id} not acknowledged; delivery uncertain")
                        self._sendto(raw, peer)
                        state[2] = time.monotonic()
                        state[3] += 1
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
                    if (pending and not ciphertext and
                            (peer, stream, sequence) == pending[1:]):
                        pending[0].set()
                    continue
                header = raw[:len(raw) - len(ciphertext)]
                message = decode_message(self.crypto.decrypt(ciphertext, header))
                with self.lock:
                    duplicate = (peer, packet_id) in self.seen
                    if not duplicate:
                        self.seen.add((peer, packet_id))
                        self.seen_order.append((peer, packet_id))
                        if len(self.seen_order) > 10000:
                            self.seen.discard(self.seen_order.popleft())
                # Accept before ACK: an ACK socket error must not mark a packet
                # seen without delivering it. Retransmissions then remain safe.
                if not duplicate:
                    self._accept_in_order(peer, stream, sequence, message)
                # ACK even duplicate DATA so sender can stop retransmitting.
                self._sendto(encode_frame(ACK, packet_id, stream, sequence), peer)
            except (ValueError, KeyError, UnicodeError, TypeError):
                # Ignore malformed UDP datagrams without killing the receiving thread.
                continue
            except Exception as exc:
                # For a student project, keep listener alive; do not log decrypted content.
                print(f"[transport] Ignored packet/error: {type(exc).__name__}: {exc}")

    def _accept_in_order(self, peer, stream, sequence, message):
        key = (peer, stream)
        ready = []
        with self.lock:
            expected = self.in_seq.get(key, 0)
            if sequence < expected:
                return
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
                    task_queue = queue.Queue()
                    self.stream_queues[key] = task_queue
                    threading.Thread(target=self._stream_worker,
                                     args=(key, task_queue), daemon=True).start()
                for item in ready:
                    task_queue.put((peer, stream, item))

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
                print(f"[transport] Handler error: {type(exc).__name__}: {exc}")
            finally:
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
