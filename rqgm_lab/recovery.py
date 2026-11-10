"""Explicit recovery to a NEW directory; original raw records are never truncated."""
import hashlib,json,shutil
from pathlib import Path
from .store import canonical

def valid_prefix(data):
    lines=data.splitlines(keepends=True);offset=0;prev='0'*64
    for index,line in enumerate(lines):
        try:
            row=json.loads(line)
            expected=hashlib.sha256(canonical(row['event']).encode()+prev.encode()).hexdigest()
            if row['prev']!=prev or row['hash']!=expected or not line.endswith(b'\n'):raise ValueError('invalid row')
            prev=row['hash'];offset+=len(line)
        except (ValueError,KeyError,TypeError):
            if index!=len(lines)-1:raise ValueError('interior corruption requires manual investigation')
            break
    return offset

def recover(source,destination):
    src=Path(source).resolve();dst=Path(destination).resolve()
    if dst.exists() or src==dst or src in dst.parents:raise ValueError('destination must be new and outside source')
    # Validate before copying anything. Retain all original bytes in *.original files.
    plans={}
    for name in ('events.jsonl','calls.jsonl'):
        p=src/name
        if p.exists():
            data=p.read_bytes();plans[name]=(data,valid_prefix(data))
    if 'events.jsonl' not in plans:raise ValueError('source is not a run')
    shutil.copytree(src,dst,symlinks=True)
    manifest={}
    for name,(data,n) in plans.items():
        (dst/(name+'.original')).write_bytes(data);(dst/name).write_bytes(data[:n])
        manifest[name]={'original_sha256':hashlib.sha256(data).hexdigest(),'kept_bytes':n,'original_bytes':len(data)}
    for p in (dst/'objects.git').glob('stage-index*'):
        if p.is_file():p.unlink()  # Derived Git index only, never objects or raw records.
    (dst/'recovery.json').write_text(json.dumps({'source':str(src),'journals':manifest},indent=2))
    return str(dst)
