#!/usr/bin/env python3
"""
UDP proxy giả lập mạng lỗi: mất gói, trễ, trùng gói, đảo thứ tự.

    client  <-->  lossy_proxy (--listen)  <-->  server (--server)

Client trỏ tới cổng của proxy thay vì cổng server. Mỗi client có một socket
upstream riêng nên server vẫn thấy các nguồn (IP, port) khác nhau.

Ví dụ:
    # server chạy ở 127.0.0.1:9000, client kết nối tới 127.0.0.1:9001
    python scripts/lossy_proxy.py --listen 9001 --server 127.0.0.1:9000 \
        --loss 0.1 --delay 50 --jitter 20 --dup 0.05 --reorder 0.1 --seed 42

    # chỉ làm lỗi chiều client -> server
    python scripts/lossy_proxy.py --listen 9001 --server 127.0.0.1:9000 \
        --loss 0.2 --direction up

Dùng raw socket + select (không thư viện mạng cấp cao), đơn luồng nên
kết quả có thể tái lập khi đặt --seed.
"""

from __future__ import annotations

import argparse
import heapq
import itertools
import random
import select
import socket
import sys
import time
from dataclasses import dataclass, field

MAX_DGRAM = 65535


@dataclass
class Impairment:
    loss: float = 0.0          # xác suất mất gói [0..1]
    delay_ms: float = 0.0      # trễ cơ bản
    jitter_ms: float = 0.0     # dao động trễ (+/- ngẫu nhiên đều)
    dup: float = 0.0           # xác suất nhân đôi gói
    reorder: float = 0.0       # xác suất bị giữ lại thêm để đảo thứ tự
    reorder_ms: float = 80.0   # thời gian giữ thêm khi đảo thứ tự


@dataclass
class Stats:
    received: int = 0
    dropped: int = 0
    duplicated: int = 0
    reordered: int = 0
    forwarded: int = 0

    def line(self, name: str) -> str:
        return (f"{name}: rx={self.received} fwd={self.forwarded} "
                f"drop={self.dropped} dup={self.duplicated} reorder={self.reordered}")


@dataclass
class Session:
    client_addr: tuple
    upstream: socket.socket
    last_seen: float = field(default_factory=time.monotonic)


class LossyProxy:
    def __init__(self, listen: tuple, server: tuple, up: Impairment, down: Impairment,
                 seed: int | None = None, idle_timeout: float = 120.0, verbose: bool = False):
        self.server = server
        self.up, self.down = up, down
        self.rng = random.Random(seed)
        self.idle_timeout = idle_timeout
        self.verbose = verbose

        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._big_buffers(self.listen_sock)
        self.listen_sock.bind(listen)
        self.sessions: dict[tuple, Session] = {}
        self.by_sock: dict[socket.socket, Session] = {}
        self.stats = {"up": Stats(), "down": Stats()}
        self._queue: list = []          # heap: (due_time, seq, sock, data, dest)
        self._seq = itertools.count()
        self._running = True

    @staticmethod
    def _big_buffers(sock: socket.socket, size: int = 4 * 1024 * 1024):
        """Tăng bộ đệm để proxy không tự làm mất gói khi nhận dồn dập."""
        for opt in (socket.SO_RCVBUF, socket.SO_SNDBUF):
            try:
                sock.setsockopt(socket.SOL_SOCKET, opt, size)
            except OSError:
                pass

    # ---- impairment ---------------------------------------------------
    def _schedule(self, direction: str, data: bytes, sock: socket.socket, dest: tuple):
        imp = self.up if direction == "up" else self.down
        st = self.stats[direction]
        st.received += 1

        if self.rng.random() < imp.loss:
            st.dropped += 1
            if self.verbose:
                print(f"[{direction}] DROP {len(data)}B")
            return

        copies = 1
        if self.rng.random() < imp.dup:
            copies = 2
            st.duplicated += 1

        for _ in range(copies):
            delay = imp.delay_ms
            if imp.jitter_ms:
                delay += self.rng.uniform(-imp.jitter_ms, imp.jitter_ms)
            if self.rng.random() < imp.reorder:
                delay += imp.reorder_ms
                st.reordered += 1
            delay = max(0.0, delay) / 1000.0
            heapq.heappush(self._queue,
                           (time.monotonic() + delay, next(self._seq), sock, data, dest, direction))

    def _flush_due(self):
        now = time.monotonic()
        while self._queue and self._queue[0][0] <= now:
            _, _, sock, data, dest, direction = heapq.heappop(self._queue)
            try:
                sock.sendto(data, dest)
                self.stats[direction].forwarded += 1
            except OSError as exc:  # đích đã đóng, v.v. -> bỏ qua, không làm sập proxy
                if self.verbose:
                    print(f"[{direction}] send error: {exc}")

    # ---- sessions -----------------------------------------------------
    def _session_for(self, addr: tuple) -> Session:
        sess = self.sessions.get(addr)
        if sess is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._big_buffers(s)
            s.bind(("0.0.0.0", 0))
            sess = Session(addr, s)
            self.sessions[addr] = sess
            self.by_sock[s] = sess
            if self.verbose:
                print(f"[session] new client {addr}")
        sess.last_seen = time.monotonic()
        return sess

    def _expire_sessions(self):
        now = time.monotonic()
        for addr, sess in list(self.sessions.items()):
            if now - sess.last_seen > self.idle_timeout:
                self.by_sock.pop(sess.upstream, None)
                sess.upstream.close()
                del self.sessions[addr]

    # ---- main loop ----------------------------------------------------
    def stop(self):
        self._running = False

    def run(self):
        last_expire = time.monotonic()
        while self._running:
            timeout = 0.05
            if self._queue:
                timeout = max(0.0, min(timeout, self._queue[0][0] - time.monotonic()))
            socks = [self.listen_sock, *self.by_sock.keys()]
            try:
                readable, _, _ = select.select(socks, [], [], timeout)
            except (OSError, ValueError):
                continue

            for s in readable:
                try:
                    data, addr = s.recvfrom(MAX_DGRAM)
                except OSError:  # vd: ConnectionResetError trên Windows khi đích chưa mở
                    continue
                if s is self.listen_sock:
                    sess = self._session_for(addr)
                    self._schedule("up", data, sess.upstream, self.server)
                else:
                    sess = self.by_sock.get(s)
                    if sess:
                        self._schedule("down", data, self.listen_sock, sess.client_addr)

            self._flush_due()
            if time.monotonic() - last_expire > 5:
                self._expire_sessions()
                last_expire = time.monotonic()

        self.close()

    def close(self):
        self.listen_sock.close()
        for sess in self.sessions.values():
            sess.upstream.close()


def parse_hostport(text: str) -> tuple:
    host, _, port = text.rpartition(":")
    return (host or "127.0.0.1", int(port))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="UDP proxy giả lập mất/trễ/trùng/đảo gói")
    p.add_argument("--listen", default="9001", help="[host:]port cho client kết nối (mặc định 9001)")
    p.add_argument("--server", required=True, help="host:port của server thật, vd 127.0.0.1:9000")
    p.add_argument("--loss", type=float, default=0.0, help="tỉ lệ mất gói 0..1")
    p.add_argument("--delay", type=float, default=0.0, help="trễ cơ bản (ms)")
    p.add_argument("--jitter", type=float, default=0.0, help="dao động trễ +/- (ms)")
    p.add_argument("--dup", type=float, default=0.0, help="tỉ lệ nhân đôi gói 0..1")
    p.add_argument("--reorder", type=float, default=0.0, help="tỉ lệ đảo thứ tự 0..1")
    p.add_argument("--reorder-delay", type=float, default=80.0, help="giữ thêm khi đảo thứ tự (ms)")
    p.add_argument("--direction", choices=["both", "up", "down"], default="both",
                   help="up = client->server, down = server->client (mặc định both)")
    p.add_argument("--seed", type=int, default=None, help="seed để tái lập kết quả")
    p.add_argument("--idle-timeout", type=float, default=120.0, help="giây không hoạt động thì hủy session")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("loss", "dup", "reorder"):
        if not 0.0 <= getattr(args, name) <= 1.0:
            print(f"--{name} phải nằm trong [0, 1]", file=sys.stderr)
            return 2

    imp = Impairment(args.loss, args.delay, args.jitter, args.dup, args.reorder, args.reorder_delay)
    clean = Impairment()
    up = imp if args.direction in ("both", "up") else clean
    down = imp if args.direction in ("both", "down") else clean

    listen = parse_hostport(args.listen) if ":" in args.listen else ("0.0.0.0", int(args.listen))
    proxy = LossyProxy(listen, parse_hostport(args.server), up, down,
                       seed=args.seed, idle_timeout=args.idle_timeout, verbose=args.verbose)

    print(f"Proxy {listen[0]}:{listen[1]} -> {args.server} | loss={args.loss} delay={args.delay}ms "
          f"jitter={args.jitter}ms dup={args.dup} reorder={args.reorder} dir={args.direction} "
          f"seed={args.seed}")
    print("Ctrl+C để dừng và in thống kê.")
    try:
        proxy.run()
    except KeyboardInterrupt:
        pass
    finally:
        print()
        print(proxy.stats["up"].line("UP  (client->server)"))
        print(proxy.stats["down"].line("DOWN(server->client)"))
        proxy.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())