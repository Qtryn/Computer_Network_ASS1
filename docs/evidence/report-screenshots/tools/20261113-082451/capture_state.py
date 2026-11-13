import json
import ssl
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

config = json.loads(Path('downloads/report-evidence-active.json').read_text())
context = ssl.create_default_context(cafile='config/local_tls/server.pem')
result = {'at': datetime.now().astimezone().isoformat(), 'clients': {}}
for name, port in [('alice',18411),('bob',18412)]:
    with urllib.request.urlopen(f'https://127.0.0.1:{port}/api/state', context=context) as response:
        state = json.load(response)
    result['clients'][name] = {key: state.get(key) for key in (
        'username','connected','online','events','outbox','reauth_required','disconnect_reason')}
target = Path(config['logs']) / (sys.argv[1] + '.json')
with target.open('x', encoding='utf-8') as output:
    json.dump(result, output, ensure_ascii=False, indent=2)
print(target)
