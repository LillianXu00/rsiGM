"""No API calls. Fail before experiments if isolation/runtime/resources are unavailable."""
import json,shutil,tempfile,subprocess,os
from pathlib import Path
from .sandbox import ROOT,run

def check():
    info={}
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    info['available_memory_mib']=int(memory['MemAvailable'].split()[0])//1024
    info['free_disk_mib']=shutil.disk_usage(ROOT).free//1048576
    if info['available_memory_mib']<768 or info['free_disk_mib']<500:raise RuntimeError('insufficient free memory/disk')
    if not (ROOT/'runtime/node_modules/@earendil-works/pi-coding-agent').exists():raise RuntimeError('Pi dependency missing')
    for tool in ('git','claude','node'):
        binary=shutil.which(tool)
        if not binary:raise RuntimeError(tool+' missing')
        info[tool]=subprocess.check_output([binary,'--version'],text=True).strip()
    if not (ROOT/'private/regression.json').exists():raise RuntimeError('prepare private regression bundle first')
    key=ROOT/'apikey.bin'
    if not key.exists() or (key.stat().st_mode&0o077):raise RuntimeError('apikey.bin missing or permissions must be 600')
    with tempfile.TemporaryDirectory(prefix='rqgm-doctor-') as cwd:
        code=f'''import json,os,socket
results=[]
for fn in [lambda:open({str(key)!r}),lambda:open({str(ROOT/'private/regression.json')!r}),lambda:open('/proc/1/environ'),lambda:socket.socket(),lambda:os.fork(),lambda:os.stat({str(ROOT/'private/regression.json')!r})]:
 try:fn();results.append(False)
 except PermissionError:results.append(True)
print(json.dumps({{"denied":results,"uid":os.geteuid()}}))
'''
        result=run(['/usr/bin/python3','-I','-c',code],cwd)
        if result['code']:raise RuntimeError('kernel isolation probe failed: '+result['stderr'][-500:])
        probe=json.loads(result['stdout'])
        if probe['denied']!=[True]*6 or probe['uid']==os.geteuid():raise RuntimeError('isolated UID and kernel permissions required; run controller with privilege to drop UID')
        info['child_uid']=probe['uid']
    info['kernel_isolation']='passed';info['dataset_tasks']=len(json.loads((ROOT/'private/regression.json').read_text())['tasks'])
    return info
