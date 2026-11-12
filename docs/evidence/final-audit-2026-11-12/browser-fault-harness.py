"""Temporary audit-only server: real sockets, switchable outgoing CHAT loss."""
import ssl
import time
from pathlib import Path
from app.common.protocol import DATA, HEADER, decode_frame, decode_message
from app.security.crypto import load_key
from app.server.auth import PasswordAccounts, read_accounts
from app.server.server import CollaborationServer

store = Path('downloads/final-audit-accounts.json')
flag = Path('downloads/browser-drop-chat.flag')
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.load_cert_chain('config/local_tls/server.pem', 'config/local_tls/server-key.pem')
server = CollaborationServer('127.0.0.1', 19000, 19001, load_key(),
    accounts=PasswordAccounts(read_accounts(store), path=store, lock_seconds=5),
    tls_context=context)
send = server.udp._sendto

def controlled_loss(raw, peer):
    if flag.exists():
        kind, packet, stream, sequence, ciphertext = decode_frame(raw)
        if kind == DATA:
            message = decode_message(server.udp.crypto.decrypt(ciphertext, raw[:HEADER.size]))
            if message.get('type') == 'CHAT' and message.get('sender') == 'test_alice':
                print(f'DROP_CHAT packet={packet} stream={stream} sequence={sequence}', flush=True)
                return
    send(raw, peer)

server.udp._sendto = controlled_loss
try:
    while True:
        time.sleep(0.2)
except KeyboardInterrupt:
    pass
finally:
    server.close()
