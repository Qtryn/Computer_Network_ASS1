"""Repeatable 20-client localhost concurrency check.

Run: python scripts/load_test.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.client import CollaborationClient
from app.server.server import CollaborationServer
from app.security.crypto import load_key


def wait_for(test, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if test():
            return True
        time.sleep(0.05)
    return False


def main():
    key = load_key()
    server = CollaborationServer("127.0.0.1", 0, 0, key)
    clients = []
    try:
        for i in range(20):
            clients.append(CollaborationClient(f"user{i:02}", tcp_port=server.tcp_port,
                                               udp_port=server.udp_port, key=key))
        if not wait_for(lambda: all(len(client.get_state()["online"]) == 20 for client in clients)):
            raise AssertionError("Some clients did not see all 20 online users")
        clients[0].send_chat("user19", "Concurrency test message")
        if not wait_for(lambda: any(event.get("text") == "Concurrency test message"
                                    for event in clients[-1].get_state()["events"])):
            raise AssertionError("Private message to last client was not received")
        print("PASS: 20 concurrent clients, online list and private chat")
    finally:
        for client in clients:
            client.close()
        server.close()


if __name__ == "__main__":
    main()
