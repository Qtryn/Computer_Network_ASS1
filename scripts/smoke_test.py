"""End-to-end localhost check: real TCP login, encrypted reliable UDP, files.

Run AFTER generating key: python scripts/smoke_test.py
"""
import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.client import CollaborationClient
from app.server.server import CollaborationServer
from app.security.crypto import load_key


def until(predicate, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main():
    key = load_key()
    server = CollaborationServer("127.0.0.1", 0, 0, key)
    alice = bob = None
    try:
        with tempfile.TemporaryDirectory() as temp:
            alice = CollaborationClient("alice", tcp_port=server.tcp_port, udp_port=server.udp_port,
                                        key=key, download_dir=Path(temp) / "alice")
            bob = CollaborationClient("bob", tcp_port=server.tcp_port, udp_port=server.udp_port,
                                      key=key, download_dir=Path(temp) / "bob")
            assert until(lambda: "bob" in alice.get_state()["online"]), "Online list not updated"
            alice.send_chat("bob", "Xin chào Bob - private")
            assert until(lambda: any(e.get("text") == "Xin chào Bob - private"
                                     for e in bob.get_state()["events"])), "Private chat not delivered"
            alice.send_chat("*", "Broadcast test")
            assert until(lambda: any(e.get("text") == "Broadcast test"
                                     for e in bob.get_state()["events"])), "Broadcast not delivered"
            path = Path(temp) / "source.bin"
            data = os.urandom(20480) + bytes(range(256))
            path.write_bytes(data)
            transfer_id = alice.send_file(path, "bob")
            assert until(lambda: any(e.get("type") == "FILE_COMPLETE" and e.get("file_id") == transfer_id
                                     for e in bob.get_state()["events"])), "File not received"
            assert until(lambda: any(e.get("type") == "FILE_RECEIPT" and e.get("file_id") == transfer_id
                                     for e in alice.get_state()["events"])), "Receipt not delivered"
            result = next(e for e in bob.get_state()["events"]
                          if e.get("type") == "FILE_COMPLETE" and e.get("file_id") == transfer_id)
            assert hashlib.sha256(Path(result["path"]).read_bytes()).digest() == hashlib.sha256(data).digest()
            bob.close()
            bob = None
            assert until(lambda: "bob" not in alice.get_state()["online"]), "Disconnect not updated"
            print("PASS: TCP login, online list, private and broadcast chat, binary UDP file, SHA-256, receipt, logout")
    finally:
        if alice:
            alice.close()
        if bob:
            bob.close()
        server.close()


if __name__ == "__main__":
    main()
