"""Fail-closed Linux Landlock + seccomp launcher. No trusted data in child cwd/env."""
import ctypes as C
import errno
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
READ = (1 << 0) | (1 << 2) | (1 << 3)
FS = (1 << 15) - 1

class Ruleset(C.Structure):
    _fields_ = [('fs', C.c_uint64), ('net', C.c_uint64)]
class PathRule(C.Structure):
    _pack_ = 1
    _fields_ = [('access', C.c_uint64), ('fd', C.c_int32)]

def restrict(read_paths, write_paths, processes=False, port=0):
    libc = C.CDLL(None, use_errno=True)
    def check(n):
        if n < 0:
            raise OSError(C.get_errno(), os.strerror(C.get_errno()))
        return n
    abi = check(libc.syscall(444, 0, 0, 1))
    if abi < 4:
        raise RuntimeError('Landlock ABI >= 4 required')
    check(libc.prctl(38, 1, 0, 0, 0))
    # Do not retain administrative capabilities when the controller runs as root.
    class CapHeader(C.Structure):
        _fields_=[('version',C.c_uint32),('pid',C.c_int)]
    class CapData(C.Structure):
        _fields_=[('effective',C.c_uint32),('permitted',C.c_uint32),('inheritable',C.c_uint32)]
    header=CapHeader(0x20080522,0);data=(CapData*2)()
    check(libc.capset(C.byref(header),C.byref(data)))
    rules = Ruleset(FS, 3)  # No TCP bind/connect permitted.
    fd = check(libc.syscall(444, C.byref(rules), C.sizeof(rules), 0))
    for path, access in [(p, READ) for p in read_paths] + [(p, FS) for p in write_paths]:
        pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        try:
            if not Path(path).is_dir():
                access &= (1 << 0) | (1 << 1) | (1 << 2) | (1 << 14)
            rule = PathRule(access, pfd)
            check(libc.syscall(445, fd, 1, C.byref(rule), 0))
        finally:
            os.close(pfd)
    if port:
        class Net(C.Structure):
            _fields_ = [("access", C.c_uint64),("port",C.c_uint64)]
        net=Net(2,port)
        check(libc.syscall(445,fd,2,C.byref(net),0))
    check(libc.syscall(446, fd, 0)); os.close(fd)
    sec = C.CDLL('libseccomp.so.2', use_errno=True)
    sec.seccomp_init.argtypes = [C.c_uint32]; sec.seccomp_init.restype = C.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [C.c_char_p]
    sec.seccomp_rule_add.argtypes = [C.c_void_p, C.c_uint32, C.c_int, C.c_uint]
    sec.seccomp_load.argtypes = [C.c_void_p]; sec.seccomp_release.argtypes = [C.c_void_p]
    ctx = sec.seccomp_init(0x7fff0000)
    if not ctx: raise RuntimeError('seccomp init failed')
    denied = ['socket','socketpair','ptrace','process_vm_readv','process_vm_writev',
              'mount','umount2','unshare','setns','bpf','keyctl','io_uring_setup',
              'open_by_handle_at','pidfd_getfd','kill','tkill','tgkill','setsid','setpgid']
    if port: denied.remove('socket')
    if not processes: denied += ['fork','vfork']
    for name in denied:
        num = sec.seccomp_syscall_resolve_name(name.encode())
        if num >= 0: check(sec.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, num, 0))
    # clone without CLONE_THREAD is forbidden; V8 threads remain possible.
    class Arg(C.Structure):
        _fields_ = [('arg',C.c_uint),('op',C.c_int),('a',C.c_uint64),('b',C.c_uint64)]
    if port:
        sec.seccomp_rule_add_array.argtypes = [C.c_void_p,C.c_uint32,C.c_int,C.c_uint,C.POINTER(Arg)]
        arg=Arg(0,1,2,0)  # socket domain != AF_INET
        check(sec.seccomp_rule_add_array(ctx,0x50000|errno.EPERM,sec.seccomp_syscall_resolve_name(b'socket'),1,C.byref(arg)))
    if not processes:
        sec.seccomp_rule_add_array.argtypes = [C.c_void_p,C.c_uint32,C.c_int,C.c_uint,C.POINTER(Arg)]
        arg=Arg(0,7,0x10000,0)
        check(sec.seccomp_rule_add_array(ctx,0x50000|errno.EPERM,sec.seccomp_syscall_resolve_name(b'clone'),1,C.byref(arg)))
        check(sec.seccomp_rule_add(ctx,0x50000|errno.ENOSYS,sec.seccomp_syscall_resolve_name(b'clone3'),0))
    check(sec.seccomp_load(ctx)); sec.seccomp_release(ctx)

def run(command, cwd, payload='', read=(), timeout=20, memory_mb=256, processes=False, port=0, extra_env=None):
    """File output bounded by RLIMIT_FSIZE; process group terminated on every exit."""
    cwd = Path(cwd).resolve()
    spec = dict(command=command, cwd=str(cwd), read=[str(Path(p).resolve()) for p in read],
                memory_mb=memory_mb, processes=processes, port=port)
    env = {'PATH':'/usr/bin:/bin','HOME':str(cwd),'TMPDIR':str(cwd),
           'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','NODE_OPTIONS':'--max-old-space-size=192'}
    env.update(extra_env or {})
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p=subprocess.Popen([sys.executable, str(Path(__file__).resolve()), json.dumps(spec)],
                           stdin=subprocess.PIPE, stdout=out, stderr=err, env=env,
                           start_new_session=True, close_fds=True)
        timed_out=False
        stop=threading.Event(); violations=[]; peak=[0]
        def monitor():
            while not stop.wait(0.1):
                try:
                    status=Path(f'/proc/{p.pid}/status').read_text()
                    rss=next(int(line.split()[1]) for line in status.splitlines() if line.startswith('VmRSS:'))
                    peak[0]=max(peak[0],rss)
                    files=list(cwd.rglob('*'))
                    size=sum(f.lstat().st_size for f in files if f.is_file() and not f.is_symlink())
                    if rss>512*1024 or size>8*1024*1024 or len(files)>256:
                        violations.append('RSS/workspace limit');os.killpg(p.pid,signal.SIGKILL);return
                except (FileNotFoundError,ProcessLookupError,StopIteration):return
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        try:
            p.communicate(payload.encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
        finally:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            p.wait();stop.set();watcher.join()
        out.seek(0);err.seek(0)
        return dict(code=p.returncode, stdout=out.read(1048576).decode(errors='replace'),
                    stderr=err.read(65536).decode(errors='replace'), timeout=timed_out, violations=violations, peak_rss_kb=peak[0])

if __name__ == '__main__':
    spec=json.loads(sys.argv[1]); os.chdir(spec['cwd']); os.umask(0o077)
    # When launched by a privileged controller, separate DAC identity as well.
    caps=int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('CapEff:')),16)
    if os.geteuid()==0 and caps & 0xc1 == 0xc1:
        workspace=Path(spec['cwd'])
        for base,dirs,files in os.walk(workspace,followlinks=False):
            for name in dirs+files:os.chown(Path(base)/name,65534,65534,follow_symlinks=False)
        os.chown(workspace,65534,65534)
        os.setgroups([]);os.setgid(65534);os.setuid(65534)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    # V8 reserves a large virtual cage; RSS is bounded by its heap flag + outer timeout.
    if spec['memory_mb']:
        n=spec['memory_mb']*1024*1024;resource.setrlimit(resource.RLIMIT_AS,(n,n))
    allowed=['/usr','/lib','/lib64','/bin','/dev/null','/dev/urandom','/dev/random','/etc/ld.so.cache','/etc/ssl/openssl.cnf']
    restrict([p for p in allowed if Path(p).exists()]+spec['read'],[spec['cwd']],spec['processes'],spec['port'])
    os.execv(spec['command'][0],spec['command'])
