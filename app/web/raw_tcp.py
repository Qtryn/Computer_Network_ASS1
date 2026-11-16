"""Small IPv4 TCP listener for the isolated Linux StreApRous HTTP demo."""
import ipaddress
import queue
import secrets
import select
import socket
import ssl
import struct
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

FIN, SYN, RST, PSH, ACK = 1, 2, 4, 8, 16
HEADER = struct.Struct("!HHIIBBHHH")
MASK = 0xFFFFFFFF
WINDOW = 32768
MSS = 512
MAX_CONNECTIONS = 32
RETRY_TIMEOUT = 0.4
RETRIES = 6


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(value for value, in struct.iter_unpack("!H", data))
    while total > 0xFFFF:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def pseudo_header(source, destination, size):
    return socket.inet_aton(source) + socket.inet_aton(destination) + struct.pack("!BBH", 0, 6, size)


def segment(source, destination, ports, seq, ack, flags, window, payload=b""):
    header = HEADER.pack(*ports, seq, ack, 5 << 4, flags, window, 0, 0)
    digest = checksum(pseudo_header(source, destination, len(header) + len(payload)) + header + payload)
    return header[:16] + struct.pack("!H", digest) + header[18:] + payload


@dataclass
class Pending:
    seq: int
    flags: int
    payload: bytes
    end: int
    sent: float
    retries: int = 0


class Connection:
    """Socket-like byte stream. The packet loop never waits on a handler."""

    def __init__(self, listener, remote, next_seq, send_seq):
        self.listener = listener
        self.remote = remote
        self.expected = next_seq & MASK
        self.seq = send_seq
        self.pending = None
        self.peer_window = MSS
        self.incoming = bytearray()
        self.outgoing = deque()
        self.condition = threading.Condition()
        self.timeout = 10
        self.updated = time.monotonic()
        self.advertised = WINDOW
        self.established = self.closing = self.dead = self.eof = self.fin_sent = False

    def settimeout(self, seconds):
        self.timeout = min(30, seconds)

    def recv(self, size):
        with self.condition:
            if not self.condition.wait_for(lambda: self.incoming or self.eof or self.dead, self.timeout):
                raise TimeoutError("Raw TCP receive timed out")
            data = bytes(self.incoming[:size])
            del self.incoming[:size]
            return data

    def sendall(self, data):
        with self.condition:
            if self.dead or self.closing:
                raise ConnectionError("Raw TCP connection closed")
            self.outgoing.extend(data[offset:offset + MSS] for offset in range(0, len(data), MSS))

    def close(self):
        with self.condition:
            self.closing = True

    def abort(self):
        with self.condition:
            self.dead = True
            self.condition.notify_all()

    def send(self, seq, flags, payload=b""):
        self.advertised = WINDOW - len(self.incoming)
        self.listener.transmit(self.remote, seq, self.expected, flags, self.advertised, payload)

    def reliable(self, flags, payload=b""):
        end = (self.seq + len(payload) + bool(flags & (SYN | FIN))) & MASK
        self.pending = Pending(self.seq, flags, payload, end, time.monotonic())
        self.send(self.seq, flags, payload)

    def input(self, seq, ack, flags, window, payload):
        with self.condition:
            if flags & RST:
                self.abort()
                return
            self.updated = time.monotonic()
            if flags & SYN:
                if not self.established and self.pending:
                    self.send(self.pending.seq, self.pending.flags, self.pending.payload)
                return
            self.peer_window = window
            if flags & ACK and self.pending and ack == self.pending.end:
                if not self.established and seq != self.expected:
                    return
                self.seq = self.pending.end
                self.pending = None
                if not self.established:
                    self.established = True
                    self.listener.accepted.put((self, self.remote))
            if not self.established or not (payload or flags & FIN):
                return
            # A later segment is acknowledged at the last contiguous sequence.
            # Its sender retransmits from that point. Keep this demo's buffer bounded.
            if seq == self.expected and len(payload) <= WINDOW - len(self.incoming):
                self.incoming.extend(payload)
                self.expected = (self.expected + len(payload) + bool(flags & FIN)) & MASK
                if flags & FIN:
                    self.eof = True
                self.condition.notify_all()
            self.send(self.pending.end if self.pending else self.seq, ACK)

    def tick(self, now):
        with self.condition:
            if self.dead or now - self.updated > 35:
                self.abort()
            elif self.pending:
                pending = self.pending
                if now - pending.sent >= RETRY_TIMEOUT:
                    if pending.retries >= RETRIES:
                        self.abort()
                    else:
                        pending.retries += 1
                        pending.sent = now
                        self.send(pending.seq, pending.flags, pending.payload)
            elif self.established:
                if self.outgoing and self.peer_window:
                    block = self.outgoing.popleft()
                    if len(block) > self.peer_window:
                        self.outgoing.appendleft(block[self.peer_window:])
                        block = block[:self.peer_window]
                    self.reliable(ACK | PSH, block)
                elif self.closing and not self.outgoing and not self.fin_sent:
                    self.fin_sent = True
                    self.reliable(ACK | FIN)
                elif self.fin_sent and self.eof:
                    self.abort()
                elif self.advertised < WINDOW - len(self.incoming):
                    self.send(self.seq, ACK)


class RawTCPListener:
    def __init__(self, host, port):
        if sys.platform != "linux":
            raise OSError("Raw TCP HTTP requires Linux and an isolated network namespace")
        address = ipaddress.IPv4Address(host)
        if not address.is_loopback:
            raise ValueError("Raw HTTP lab listener binds only to an IPv4 loopback address")
        if not 1024 <= port <= 65535:
            raise ValueError("Raw HTTP demo requires a port in 1024–65535")
        self.host, self.port = host, port
        self.raw = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        self.raw.bind((host, 0))
        self.connections = {}
        self.accepted = queue.Queue(maxsize=MAX_CONNECTIONS)
        self.running = True
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def transmit(self, remote, seq, ack, flags, window, payload):
        data = segment(self.host, remote[0], (self.port, remote[1]), seq, ack, flags, window, payload)
        self.raw.sendto(data, (remote[0], 0))

    def accept(self):
        try:
            return self.accepted.get(timeout=0.5)
        except queue.Empty:
            raise socket.timeout from None

    def input(self, packet):
        if len(packet) < 40 or packet[0] >> 4 != 4:
            return
        offset = (packet[0] & 15) * 4
        if offset < 20 or len(packet) < offset + 20 or socket.inet_ntoa(packet[16:20]) != self.host:
            return
        raw = packet[offset:]
        source = socket.inet_ntoa(packet[12:16])
        sport, dport, seq, ack, hdr, flags, window, tcp_checksum, _ = HEADER.unpack_from(raw)
        header_size = (hdr >> 4) * 4
        if dport != self.port or not 20 <= header_size <= len(raw):
            return
        pseudo = pseudo_header(source, self.host, len(raw))
        # Linux loopback can deliver its checksum-offload seed to raw listeners.
        loopback_seed = ipaddress.IPv4Address(source).is_loopback and tcp_checksum == (checksum(pseudo) ^ 0xFFFF)
        if not loopback_seed and checksum(pseudo + raw):
            return
        remote = (source, sport)
        connection = self.connections.get(remote)
        if connection is None:
            if flags & (SYN | ACK | RST | FIN) != SYN or len(self.connections) >= MAX_CONNECTIONS:
                return
            connection = Connection(self, remote, seq + 1, secrets.randbits(32))
            self.connections[remote] = connection
            connection.reliable(SYN | ACK)
        else:
            connection.input(seq, ack, flags, window, raw[header_size:])

    def loop(self):
        while self.running:
            try:
                if select.select([self.raw], [], [], 0.02)[0]:
                    self.input(self.raw.recv(65535))
                now = time.monotonic()
                for key, connection in list(self.connections.items()):
                    connection.tick(now)
                    if connection.dead:
                        del self.connections[key]
            except (OSError, queue.Full):
                if not self.running:
                    break

    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.raw.close()
        for connection in self.connections.values():
            connection.abort()


class RawTLS:
    """Bridge standard TLS to the user-space TCP stream using memory BIOs."""

    is_secure = True

    def __init__(self, connection, context):
        self.connection = connection
        self.incoming = ssl.MemoryBIO()
        self.outgoing = ssl.MemoryBIO()
        self.tls = context.wrap_bio(self.incoming, self.outgoing, server_side=True)
        self.step(self.tls.do_handshake)

    def flush(self):
        while self.outgoing.pending:
            self.connection.sendall(self.outgoing.read())

    def step(self, action):
        while True:
            try:
                result = action()
                self.flush()
                return result
            except ssl.SSLWantReadError:
                self.flush()
                data = self.connection.recv(32768)
                if data:
                    self.incoming.write(data)
                else:
                    self.incoming.write_eof()
            except ssl.SSLWantWriteError:
                self.flush()

    def settimeout(self, seconds):
        self.connection.settimeout(seconds)

    def recv(self, size):
        return self.step(lambda: self.tls.read(size))

    def sendall(self, data):
        view = memoryview(data)
        while view:
            written = self.step(lambda: self.tls.write(view))
            view = view[written:]

    def close(self):
        try:
            self.tls.unwrap()
        except OSError:
            pass
        try:
            self.flush()
        finally:
            self.connection.close()
