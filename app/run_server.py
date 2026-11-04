"""Run from repository root: python -m app.run_server"""
import argparse
import time

from app.common.config import TCP_PORT, UDP_PORT
from app.server.server import CollaborationServer
from app.security.crypto import load_key


def main():
    parser = argparse.ArgumentParser(description="Collaboration server")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 for LAN access")
    parser.add_argument("--tcp-port", type=int, default=TCP_PORT)
    parser.add_argument("--udp-port", type=int, default=UDP_PORT)
    args = parser.parse_args()
    server = CollaborationServer(args.host, args.tcp_port, args.udp_port, load_key())
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.close()


if __name__ == "__main__":
    main()
