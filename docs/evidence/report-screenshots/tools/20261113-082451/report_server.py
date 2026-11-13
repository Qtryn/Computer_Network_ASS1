"""Evidence-only real server; optional CHAT DATA loss for report_alice."""
import json
import ssl
import time
from pathlib import Path
from app.common.protocol import DATA, HEADER, decode_frame, decode_message
from app.security.crypto import load_key
from app.server.auth import PasswordAccounts, read_accounts
from app.server.server import CollaborationServer

config = json.loads(Path('downloads/report-evidence-active.json').read_text())
work = Path(config['work'])
store, flag = work / 'accounts.json', work / 'drop-chat.flag'
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.load_cert_chain('config/local_tls/server.pem', 'config/local_tls/server-key.pem')
server = CollaborationServer('127.0.0.1', *config['ports'][:2], load_key(),
    accounts=PasswordAccounts(read_accounts(store) if store.exists() else {}, path=store),
    tls_context=context)
send = server.udp._sendto

def controlled_loss(raw, peer):
    if flag.exists():
        kind, packet, stream, sequence, ciphertext = decode_frame(raw)
        if kind == DATA:
            message = decode_message(server.udp.crypto.decrypt(ciphertext, raw[:HEADER.size]))
            if message.get('type') == 'CHAT' and message.get('sender') == 'report_alice':
                with (Path(config['logs']) / 'controlled-loss.txt').open('a', encoding='utf-8') as log:
                    log.write(f'DROP_CHAT packet={packet} stream={stream} sequence={sequence}\n')
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
