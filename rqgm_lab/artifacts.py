"""Bounded text artifacts; never follow candidate symlinks into the host."""
from pathlib import Path
import os,stat

def validate(files,limit=262144):
    if not isinstance(files,dict) or len(files)>64:raise ValueError('invalid files mapping')
    total=0
    for name,value in files.items():
        if not isinstance(name,str) or not isinstance(value,str):raise ValueError('text files required')
        p=Path(name)
        if not name or name in ('.','..') or p.is_absolute() or any(x in ('..','.git','__pycache__') for x in p.parts) or name.startswith('-') or any(c in name for c in '\n\x00\t'):
            raise ValueError('unsafe file path')
        total+=len(value.encode())
    if total>limit:raise ValueError('artifact too large')
    names=set(files)
    if any(str(parent) in names for name in names for parent in Path(name).parents if str(parent)!='.'):
        raise ValueError('file/directory collision')
    return files

def write(directory,files):
    for name,text in validate(files).items():
        p=Path(directory)/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)

def collect(directory,exclude=()):
    result={};total=0
    # os.walk does not follow directory symlinks. Reject rather than dereference them.
    for base,dirs,names in os.walk(directory,followlinks=False):
        for name in dirs+names:
            p=Path(base)/name
            if p.is_symlink():raise ValueError('symlinks are not exportable artifacts')
        for name in names:
            p=Path(base)/name;relative=str(p.relative_to(directory))
            if relative in exclude or '__pycache__' in p.parts:continue
            info=p.lstat()
            if not stat.S_ISREG(info.st_mode):raise ValueError('non-regular artifact')
            total+=info.st_size
            if total>262144 or len(result)>=64:raise ValueError('export budget exceeded')
            try:result[relative]=p.read_text()
            except UnicodeDecodeError:continue
    return result
