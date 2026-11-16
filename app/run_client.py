"""Run: python -m app.run_client --name alice --ui-port 8011"""
import argparse
import ssl
from pathlib import Path

from app.client import CollaborationClient, register_account
from app.features.outbox import ChatState
from app.features.chat_store import DurableChatState
from app.common.config import TCP_PORT, UDP_PORT
from app.web.local_web import ClientSession, run_local_ui
from app.security.crypto import load_key


def main():
    parser = argparse.ArgumentParser(description="Collaboration browser-based client")
    parser.add_argument("--name", default="", help="Prefill username, e.g. alice")
    parser.add_argument("--demo", action="store_true", help="Explicit passwordless test mode")
    parser.add_argument("--state-db", type=Path, default=Path("config/local_client.sqlite3"))
    parser.add_argument("--tls-ca", help="Trusted server certificate/CA PEM; enables account login")
    parser.add_argument("--server-name", help="Expected TLS hostname (defaults to --host)")
    parser.add_argument("--ui-cert", help="Local browser HTTPS certificate PEM")
    parser.add_argument("--ui-key", help="Local browser HTTPS private key PEM")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP")
    parser.add_argument("--tcp-port", type=int, default=TCP_PORT)
    parser.add_argument("--udp-port", type=int, default=UDP_PORT)
    parser.add_argument("--ui-port", type=int, default=8011)
    parser.add_argument("--raw-http", action="store_true", help="Use the Linux user-space TCP listener for the UI")
    args = parser.parse_args()
    if args.demo and any((args.tls_ca, args.ui_cert, args.ui_key)):
        parser.error("--demo cannot be combined with TLS options")
    if not args.demo and not any((args.tls_ca, args.ui_cert, args.ui_key)):
        args.tls_ca = "config/local_tls/server.pem"
        args.ui_cert = "config/local_tls/server.pem"
        args.ui_key = "config/local_tls/server-key.pem"
    if not args.demo and not args.tls_ca:
        parser.error("Account mode requires --tls-ca")
    if bool(args.ui_cert) != bool(args.ui_key):
        parser.error("--ui-cert and --ui-key must be supplied together")
    if args.tls_ca and not args.ui_cert:
        parser.error("Account mode requires --ui-cert and --ui-key to protect browser passwords")
    context = ssl.create_default_context(cafile=args.tls_ca) if args.tls_ca else None
    ui_context = None
    if args.ui_cert:
        ui_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ui_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ui_context.load_cert_chain(args.ui_cert, args.ui_key)
    key = load_key()

    def connect(username, password):
        state = client.chat_states.get(username)
        if state is None:
            state = DurableChatState(username, args.state_db) if context else ChatState(username)
            state.reset_sending()
            client.chat_states[username] = state
        return CollaborationClient(username, args.host, args.tcp_port, args.udp_port, key,
                                   password=password, tls_context=context,
                                   server_hostname=args.server_name,
                                   chat_state=state)

    def register(username, password):
        register_account(username, password, args.host, args.tcp_port,
                         tls_context=context, server_hostname=args.server_name)

    client = ClientSession(connect, account_mode=context is not None, username=args.name,
                           registration_factory=register, auto_reconnect=True,
                           require_http_session=context is not None)
    try:
        run_local_ui(client, args.ui_port, tls_context=ui_context, raw_tcp=args.raw_http)
    except KeyboardInterrupt:
        print("\nStopping client...")
    finally:
        client.close()


if __name__ == "__main__":
    main()
