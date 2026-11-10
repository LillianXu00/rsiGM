"""Append-only transaction journal and deduplicated Git object snapshots."""
import hashlib,json,os,subprocess
from pathlib import Path

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
class Journal:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.events=[];prev='0'*64
        if self.path.exists():
            with self.path.open('rb') as f:
                for line in f:
                    row=json.loads(line)
                    if row['prev']!=prev or row['hash']!=hashlib.sha256(canonical(row['event']).encode()+prev.encode()).hexdigest():
                        raise RuntimeError('journal corruption; preserve original and recover explicitly')
                    prev=row['hash'];self.events.append(row['event'])
        self.prev=prev
    def append(self,event):
        h=hashlib.sha256(canonical(event).encode()+self.prev.encode()).hexdigest()
        row=canonical(dict(prev=self.prev,hash=h,event=event))+'\n'
        fd=os.open(self.path,os.O_CREAT|os.O_WRONLY|os.O_APPEND,0o600)
        try:
            data=row.encode();offset=0
            while offset<len(data):offset+=os.write(fd,data[offset:])
            os.fsync(fd)
        finally:os.close(fd)
        self.prev=h;self.events.append(json.loads(canonical(event)))
class Archive:
    def __init__(self,path):
        self.path=Path(path).resolve();self.path.mkdir(parents=True,exist_ok=True)
        if not (self.path/'HEAD').exists():self.git('init','--bare',str(self.path))
    def git(self,*args,data=None,env=None):
        e=os.environ.copy();e.update({'GIT_AUTHOR_NAME':'RQGM','GIT_AUTHOR_EMAIL':'lab@localhost','GIT_COMMITTER_NAME':'RQGM','GIT_COMMITTER_EMAIL':'lab@localhost'})
        if env:e.update(env)
        return subprocess.check_output(['git','--git-dir',str(self.path),*args],input=data,env=e,stderr=subprocess.PIPE).decode().strip()
    def commit(self,files,parent=None,message='candidate'):
        from .artifacts import validate
        validate(files)
        index=self.path/'stage-index';env={'GIT_INDEX_FILE':str(index)}
        self.git('read-tree','--empty',env=env)
        total=0
        for name,content in sorted(files.items()):
            p=Path(name)
            if p.is_absolute() or '..' in p.parts or '.git' in p.parts or name.startswith('-') or '\n' in name or '\x00' in name:raise ValueError('unsafe artifact path')
            total+=len(content.encode())
            if total>262144:raise ValueError('candidate >256KiB')
            blob=self.git('hash-object','-w','--stdin',data=content.encode())
            self.git('update-index','--add','--cacheinfo','100644',blob,name,env=env)
        tree=self.git('write-tree',env=env)
        args=['commit-tree',tree,'-m',message]
        if parent:args+=['-p',parent]
        commit=self.git(*args);self.git('update-ref','refs/heads/nodes/'+commit,commit)
        return commit
    def files(self,commit):
        names=self.git('ls-tree','-r','--name-only',commit).splitlines()
        return {n:subprocess.check_output(['git','--git-dir',str(self.path),'show',commit+':'+n],stderr=subprocess.PIPE).decode() for n in names}
    def materialize(self,commit,path):
        for name,content in self.files(commit).items():
            p=Path(path)/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
