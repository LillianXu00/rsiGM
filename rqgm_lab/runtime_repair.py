"""Explicit, journalled migration restricted to the empty-response runtime fix."""
import argparse,fcntl
from pathlib import Path
from .sandbox import ROOT
from .store import Archive,Journal
from .engine import digest

ALLOWED={'rqgm_lab/live.py','rqgm_lab/engine.py','runtime/pi-bridge.mjs',
         'rqgm_lab/runtime_repair.py'}

def repair(root):
    root=Path(root).resolve()
    if not (root/'events.jsonl').is_file():raise ValueError('existing experiment required')
    with (ROOT/'runs/.execution.lock').open('a') as global_lock,(root/'lock').open('a') as lock:
        for handle in (global_lock,lock):fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        journal=Journal(root/'events.jsonl');last=[e for e in journal.events if e['type']=='state'][-1]
        state=last['state'];archive=Archive(root/'objects.git')
        old=archive.files(last['controller_commit'])
        if digest(old)!=state['source_hash']:raise RuntimeError('archived source fingerprint mismatch')
        source={str(p.relative_to(ROOT)):p.read_text() for p in (ROOT/'rqgm_lab').rglob('*.py')}
        for name in ('runtime/pi-bridge.mjs','runtime/package-lock.json'):source[name]=(ROOT/name).read_text()
        changed={name for name in set(old)|set(source) if old.get(name)!=source.get(name)}
        if not changed:return {'status':'already current'}
        if changed-ALLOWED:raise RuntimeError('unrelated source changes; migration refused: '+str(sorted(changed-ALLOWED)))
        previous=state['source_hash'];commit=archive.commit(source,message='trusted empty-response runtime repair')
        state['source_hash']=digest(source)
        import time
        journal.append({'type':'state','reason':'runtime_repair','time':time.time(),
            'state':state,'controller_commit':commit,'details':{
                'previous_commit':last['controller_commit'],'previous_source_hash':previous,
                'changed_files':sorted(changed),'reason':'bounded empty-response retry and diagnostics',
                'comparability':'Runtime policy changed; historical evaluations retained under their original controller versions.'}})
        return {'status':'repaired','root':str(root),'controller_commit':commit,'pending':state['pending']}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True)
    import json
    print(json.dumps(repair(parser.parse_args().root),ensure_ascii=False))

if __name__=='__main__':main()
