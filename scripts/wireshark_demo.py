"""Generate synthetic localhost traffic for a REAL Wireshark/Npcap capture.

Start capture first: tcp port 9100 or udp port 9101. No packets are fabricated.
Uses an existing trusted localhost certificate; temporary accounts/files only.
"""
import argparse
import os
import ssl
import tempfile
import time
from pathlib import Path

from app.client import CollaborationClient, register_account
from app.common.protocol import ACK, decode_frame
from app.server.auth import PasswordAccounts, read_accounts
from app.server.server import CollaborationServer


def wait_for(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Demo condition timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tcp-port", type=int, default=9100)
    parser.add_argument("--udp-port", type=int, default=9101)
    parser.add_argument("--cert", default="config/local_tls/server.pem")
    parser.add_argument("--tls-key", default="config/local_tls/server-key.pem")
    args = parser.parse_args()
    tls_server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls_server.load_cert_chain(args.cert, args.tls_key)
    tls_client = ssl.create_default_context(cafile=args.cert)
    key = os.urandom(32)
    server, clients = None, []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        accounts_path = root / "accounts.json"

        def start_server():
            records = read_accounts(accounts_path) if accounts_path.exists() else {}
            return CollaborationServer("127.0.0.1", args.tcp_port, args.udp_port, key,
                accounts=PasswordAccounts(records, path=accounts_path), tls_context=tls_server)

        def connect(name, state=None):
            client = CollaborationClient(name, tcp_port=args.tcp_port, udp_port=args.udp_port,
                key=key, password="capture-demo-only", tls_context=tls_client,
                server_hostname="localhost", download_dir=root / name, chat_state=state)
            clients.append(client)
            return client

        try:
            server = start_server()
            for name in ("cap_alice", "cap_bob"):
                register_account(name, "capture-demo-only", tcp_port=args.tcp_port,
                                 tls_context=tls_client, server_hostname="localhost")
            alice, bob = connect("cap_alice"), connect("cap_bob")
            real_send = server.udp._sendto
            dropped = []
            alice_peer = ("127.0.0.1", alice.udp.port)

            def lose_one_ack(raw, peer):
                kind, packet_id, stream, sequence, _ = decode_frame(raw)
                if kind == ACK and peer == alice_peer and sequence == 0 and not dropped:
                    dropped.append(packet_id)
                    return
                real_send(raw, peer)

            server.udp._sendto = lose_one_ack
            alice.send_chat("cap_bob", "Captured encrypted chat with one lost transport ACK")
            wait_for(lambda: not alice.chat_state.pending())
            assert len(dropped) == 1
            print("RETRANSMITTED_PACKET_ID:", dropped[0])
            path = root / "Báo cáo capture.bin"
            path.write_bytes(bytes(range(256)) * 128)
            file_id = alice.send_file(path, "cap_bob")
            wait_for(lambda: any(e.get("type") == "FILE_RECEIPT" and e.get("file_id") == file_id
                                 and e.get("status") == "ok" for e in alice.get_state()["events"]))
            print("FILE_STREAM_ID:", file_id)
            # Queue an unconfirmed chat, then perform a real server stop/restart.
            state_a, state_b = alice.chat_state, bob.chat_state
            alice.udp._sendto = lambda *_: None
            alice.udp.ack_timeout, alice.udp.max_retries = 0.03, 0
            try:
                alice.send_chat("cap_bob", "Pending chat delivered after TLS reauthentication")
            except TimeoutError:
                pass
            server.close()
            wait_for(lambda: not alice.running.is_set() and not bob.running.is_set())
            alice.close()
            bob.close()
            server = start_server()
            bob, alice = connect("cap_bob", state_b), connect("cap_alice", state_a)
            wait_for(lambda: not alice.chat_state.pending())
            print("PASS: actual TLS registration/login, encrypted UDP chat/file, one lost ACK,")
            print("      real retransmission, SHA-256 receipt, disconnect and fresh-session replay")
        finally:
            for client in clients:
                client.close()
            if server:
                server.close()


if __name__ == "__main__":
    main()
