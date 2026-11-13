"""Stream real child-process output to a real console and complete logs."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

config=json.loads(Path('downloads/report-evidence-active.json').read_text())
work,logs=Path(config['work']),Path(config['logs'])
checks=[('unittest',[sys.executable,'-u','-m','unittest','discover','-s','tests','-v']),
        ('smoke',[sys.executable,'-u','-m','scripts.smoke_test']),
        ('load',[sys.executable,'-u','-m','scripts.load_test']),
        ('ui',['node','scripts/test_ui.cjs'])]
results=[]
for name,command in checks:
    print('> '+subprocess.list2cmdline(command),flush=True)
    started=time.perf_counter()
    with (logs/(name+'.txt')).open('w',encoding='utf-8') as log:
        child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'})
        for line in child.stdout:
            print(line,end='',flush=True);log.write(line);log.flush()
        code=child.wait()
        elapsed=time.perf_counter()-started
        log.write(f'\nExit={code} ElapsedSeconds={elapsed:.3f}\n')
    results.append({'test':name,'exit_code':code,'seconds':round(elapsed,3)})
    (logs/'test-summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    if name in ('unittest','load'):
        (work/'console-phase.json').write_text(json.dumps({'phase':name,'exit_code':code}))
        deadline=time.monotonic()+1800
        while not (work/('continue-'+name+'.flag')).exists() and time.monotonic()<deadline:
            time.sleep(0.2)
    if code:
        sys.exit(code)
(work/'console-phase.json').write_text(json.dumps({'phase':'complete','exit_code':0}))
deadline=time.monotonic()+1800
while not (work/'close-console.flag').exists() and time.monotonic()<deadline:
    time.sleep(0.2)
