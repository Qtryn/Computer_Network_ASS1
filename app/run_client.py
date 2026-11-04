"""Run: python -m app.run_client --name alice --ui-port 8011"""
import argparse

from app.client import CollaborationClient
from app.common.config import TCP_PORT, UDP_PORT
from app.web.local_web import run_local_ui
from app.security.crypto import load_key


def main():
    parser = argparse.ArgumentParser(description="Collaboration browser-based client")
    parser.add_argument("--name", required=True, help="Username, e.g. alice")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP")
    parser.add_argument("--tcp-port", type=int, default=TCP_PORT)
    parser.add_argument("--udp-port", type=int, default=UDP_PORT)
    parser.add_argument("--ui-port", type=int, default=8011)
    args = parser.parse_args()
    client = CollaborationClient(args.name, args.host, args.tcp_port,
                                 args.udp_port, load_key())
    try:
        run_local_ui(client, args.ui_port)
    except KeyboardInterrupt:
        print("\nStopping client...")
    finally:
        client.close()


if __name__ == "__main__":
    main()
