"""Measure end-to-end file transfer under simulated packet loss (real server + 2 clients).

Run from the project root:
    python scripts/lossy_benchmark.py --loss 0 0.1 0.2 0.3 --size-kb 100 --runs 2

Uses the project's DEFAULT transport settings (ACK_TIMEOUT, MAX_RETRIES, WINDOW_SIZE),
injects loss on server + both clients (same fault hook as tests/test_lossy_network.py)
and prints a Markdown table you can paste into the report.
"""
import argparse
import hashlib
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.client import CollaborationClient
from app.server.server import CollaborationServer
from tests.fault_injection import FaultyLink


def run_once(loss, size, seed, timeout):
    key = os.urandom(32)
    server = CollaborationServer("127.0.0.1", 0, 0, key)
    alice = bob = None
    links = []
    try:
        with tempfile.TemporaryDirectory() as temp:
            alice = CollaborationClient("alice", tcp_port=server.tcp_port, udp_port=server.udp_port,
                                        key=key, download_dir=Path(temp) / "alice")
            bob = CollaborationClient("bob", tcp_port=server.tcp_port, udp_port=server.udp_port,
                                      key=key, download_dir=Path(temp) / "bob")
            time.sleep(0.3)
            if loss:
                links = [FaultyLink(node, loss=loss, seed=seed * 10 + i)
                         for i, node in enumerate((server.udp, alice.udp, bob.udp))]
            data = os.urandom(size)
            source = Path(temp) / "source.bin"
            source.write_bytes(data)
            outcome = {}

            def upload():
                try:
                    alice.send_file(source, "bob")
                except Exception as exc:  # report, do not crash the benchmark
                    outcome["error"] = type(exc).__name__

            started = time.monotonic()
            worker = threading.Thread(target=upload, daemon=True)
            worker.start()
            result = None
            while time.monotonic() - started < timeout and result is None:
                result = next((e for e in bob.get_state()["events"] if e.get("type") == "FILE_COMPLETE"), None)
                time.sleep(0.05)
            elapsed = time.monotonic() - started
            intact = bool(result) and hashlib.sha256(Path(result["path"]).read_bytes()).digest() \
                == hashlib.sha256(data).digest()
            return intact, elapsed, outcome.get("error", ""), sum(l.stats["dropped"] for l in links)
    finally:
        for link in links:
            link.close()
        for client in (alice, bob):
            if client:
                client.close()
        server.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--loss", type=float, nargs="+", default=[0.0, 0.1, 0.2, 0.3])
    parser.add_argument("--size-kb", type=int, default=100)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=120, help="seconds before a run counts as failed")
    args = parser.parse_args()

    print(f"| Loss (each hop) | Run | File | Result | Time (s) | Throughput (KB/s) | Packets dropped | Note |")
    print("|---|---|---|---|---|---|---|---|")
    for loss in args.loss:
        for run in range(1, args.runs + 1):
            ok, seconds, error, dropped = run_once(loss, args.size_kb * 1024, run, args.timeout)
            speed = args.size_kb / seconds if ok else 0
            print(f"| {loss:.0%} | {run} | {args.size_kb} KB | {'SHA-256 OK' if ok else 'FAILED'} | "
                  f"{seconds:.1f} | {speed:.0f} | {dropped} | {error} |", flush=True)


if __name__ == "__main__":
    main()