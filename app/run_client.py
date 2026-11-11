"""Run: python -m app.run_client --ui-port 8011"""
import argparse

from app.client import CollaborationClient
from app.common.config import TCP_PORT, UDP_PORT
from app.web.local_web import LocalUIState, run_local_ui
from app.security.crypto import load_key


def main():
    parser = argparse.ArgumentParser(description="Collaboration browser-based client")
    parser.add_argument("--name", help="Log in as this username before opening the UI")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP")
    parser.add_argument("--tcp-port", type=int, default=TCP_PORT)
    parser.add_argument("--udp-port", type=int, default=UDP_PORT)
    parser.add_argument("--ui-port", type=int, default=8011)
    args = parser.parse_args()
    key = load_key()
    client_factory = lambda username: CollaborationClient(
        username, args.host, args.tcp_port, args.udp_port, key)
    client = client_factory(args.name) if args.name else None
    ui = LocalUIState(client_factory, client)
    try:
        run_local_ui(ui, args.ui_port)
    except KeyboardInterrupt:
        print("\nStopping client...")
    finally:
        ui.close()


if __name__ == "__main__":
    main()
