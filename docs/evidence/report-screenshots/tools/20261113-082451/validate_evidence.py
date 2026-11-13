import hashlib
import json
import struct
import uuid
from datetime import datetime
from pathlib import Path

config = json.loads(Path('downloads/report-evidence-active.json').read_text())
logs = Path(config['logs'])
before = json.loads((logs/'03-before-restart.json').read_text(encoding='utf-8'))
after = json.loads((logs/'04-after-relogin.json').read_text(encoding='utf-8'))
chat = json.loads((logs/'02-chat-file.json').read_text(encoding='utf-8'))
expected = [m['message_id'] for m in before['clients']['alice']['outbox']]
assert len(expected) == 2
assert before['clients']['alice']['connected']
assert not [e for e in before['clients']['bob']['events'] if e.get('message_id') in expected]
received = [e for e in after['clients']['bob']['events'] if e.get('type') == 'CHAT' and e.get('message_id') in expected]
assert [e['message_id'] for e in received] == expected
assert after['clients']['alice']['outbox'] == []
assert after['clients']['alice']['connected'] and after['clients']['bob']['connected']
for mid in expected:
    receipt = [e for e in after['clients']['alice']['events'] if e.get('type') == 'CHAT_RECEIPT' and e.get('message_id') == mid]
    assert len(receipt) == 1 and receipt[0]['status'] == 'DELIVERED'
for prefix in ['REPORT private 01:', 'REPORT broadcast 02:']:
    assert len([e for e in chat['clients']['bob']['events'] if e.get('type') == 'CHAT' and e.get('text','').startswith(prefix)]) == 1
file_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path(config['work'])/'report-demo.txt',Path('downloads/report_bob/report-demo.txt')]}
assert len(set(file_hashes.values())) == 1
assert any(e.get('type') == 'FILE_RECEIPT' and e.get('status') == 'ok' for e in chat['clients']['alice']['events'])

frames = {}
for line in (logs/'pcap-selected-frames.tsv').read_text(encoding='utf-8-sig').splitlines():
    number, src, dst, raw = line.split('\t')
    payload = bytes.fromhex(raw)
    frames[number] = {'src_port':int(src),'dst_port':int(dst),'kind':payload[5],
        'sequence':int.from_bytes(payload[6:10],'big'),
        'packet_uuid':str(uuid.UUID(bytes=payload[10:26])),
        'stream_uuid':str(uuid.UUID(bytes=payload[26:42])),
        'payload_sha256':hashlib.sha256(payload).hexdigest(), 'payload_size':len(payload)}
assert frames['109']['payload_sha256'] == frames['120']['payload_sha256']
assert [frames[n]['kind'] for n in ('109','120','121')] == [1,1,2]
assert len({frames[n]['packet_uuid'] for n in frames}) == 1
assert len({frames[n]['sequence'] for n in frames}) == 1
assert frames['121']['payload_size'] == 42
pcap = Path('docs/evidence/final-audit-2026-11-12/final-loopback.pcapng')
assert hashlib.sha256(pcap.read_bytes()).hexdigest() == 'e9acddbab2bba4ddf4a7d79240d31ebf7f7a46bb4c63823de2f54a63b3ff75f4'
tests = json.loads((logs/'test-summary.json').read_text(encoding='utf-8'))
assert len(tests) == 4 and all(t['exit_code'] == 0 for t in tests)
assert 'Ran 65 tests in 44.532s' in (logs/'unittest.txt').read_text(encoding='utf-8')
images = {}
for path in sorted(Path(config['mirror']).glob('0[1-6]_*.png')):
    data = path.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    assert data == (Path(config['evidence'])/path.name).read_bytes()
    images[path.name] = {'width':struct.unpack('>I',data[16:20])[0], 'height':struct.unpack('>I',data[20:24])[0],
        'sha256':hashlib.sha256(data).hexdigest()}
assert len(images) == 6
result = {'at':datetime.now().astimezone().isoformat(), 'result':'PASS', 'images':images,
    'tests':tests, 'replay_original_ids':expected, 'replay_received_ids':[e['message_id'] for e in received],
    'file_sha256':file_hashes,'pcap_frames':frames,'pdf_compiled':False,
    'pdf_limitation':'pdfLaTeX/latexmk/tectonic unavailable on Windows PATH, common installation paths, and existing Ubuntu WSL distribution.'}
with (logs/'evidence-validation.json').open('x',encoding='utf-8') as output:
    json.dump(result,output,ensure_ascii=False,indent=2)
print('PASS: six genuine PNGs mirrored; private/broadcast once each; file SHA-256 and receipt; ordered replay preserves two UUIDs; DATA retransmission/ACK; four test commands exit 0.')
