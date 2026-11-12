"""Run: python -m app.run_client --name alice --ui-port 8011"""
import argparse
import ssl

from app.client import CollaborationClient, register_account
from app.features.outbox import ChatState
from app.common.config import TCP_PORT, UDP_PORT
from app.web.local_web import ClientSession, run_local_ui
from app.security.crypto import load_key


def main():
    parser = argparse.ArgumentParser(description="Collaboration browser-based client")
    parser.add_argument("--name", default="", help="Prefill username, e.g. alice")
    parser.add_argument("--tls-ca", help="Trusted server certificate/CA PEM; enables account login")
    parser.add_argument("--server-name", help="Expected TLS hostname (defaults to --host)")
    parser.add_argument("--ui-cert", help="Local browser HTTPS certificate PEM")
    parser.add_argument("--ui-key", help="Local browser HTTPS private key PEM")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP")
    parser.add_argument("--tcp-port", type=int, default=TCP_PORT)
    parser.add_argument("--udp-port", type=int, default=UDP_PORT)
    parser.add_argument("--ui-port", type=int, default=8011)
    args = parser.parse_args()
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
        return CollaborationClient(username, args.host, args.tcp_port, args.udp_port, key,
                                   password=password, tls_context=context,
                                   server_hostname=args.server_name,
                                   chat_state=client.chat_states.setdefault(username, ChatState(username)))

    def register(username, password):
        register_account(username, password, args.host, args.tcp_port,
                         tls_context=context, server_hostname=args.server_name)

    client = ClientSession(connect, account_mode=context is not None, username=args.name,
                           registration_factory=register, auto_reconnect=True)
    try:
        run_local_ui(client, args.ui_port, tls_context=ui_context)
    except KeyboardInterrupt:
        print("\nStopping client...")
    finally:
        client.close()


if __name__ == "__main__":
    main()
