"""Run from repository root: python -m app.run_server"""
import argparse
import ssl
import time
from pathlib import Path

from app.common.config import TCP_PORT, UDP_PORT
from app.server.auth import PasswordAccounts, read_accounts
from app.server.server import CollaborationServer
from app.security.crypto import load_key


def main():
    parser = argparse.ArgumentParser(description="Collaboration server")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 for LAN access")
    parser.add_argument("--tcp-port", type=int, default=TCP_PORT)
    parser.add_argument("--udp-port", type=int, default=UDP_PORT)
    parser.add_argument("--accounts", type=Path, help="Local JSON account file; requires TLS")
    parser.add_argument("--tls-cert", type=Path, help="Server certificate (PEM)")
    parser.add_argument("--tls-key", type=Path, help="Server private key (PEM)")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--lock-seconds", type=int, default=60)
    parser.add_argument("--session-seconds", type=int, default=3600)
    args = parser.parse_args()
    account_options = (args.accounts, args.tls_cert, args.tls_key)
    if any(account_options) and not all(account_options):
        parser.error("--accounts, --tls-cert and --tls-key must be supplied together")
    if min(args.max_attempts, args.lock_seconds, args.session_seconds) < 1:
        parser.error("Login limits and session duration must be positive")
    accounts = tls_context = None
    try:
        if args.accounts:
            records = read_accounts(args.accounts)
            if not records:
                raise ValueError("Provision at least one account")
            accounts = PasswordAccounts(records, max_attempts=args.max_attempts,
                                        lock_seconds=args.lock_seconds)
            tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
            tls_context.load_cert_chain(args.tls_cert, args.tls_key)
        server = CollaborationServer(args.host, args.tcp_port, args.udp_port, load_key(),
                                     accounts=accounts, tls_context=tls_context,
                                     session_seconds=args.session_seconds)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.close()


if __name__ == "__main__":
    main()
