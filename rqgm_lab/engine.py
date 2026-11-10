"""Bounded general-purpose harness interpreter. Architecture remains candidate code."""
import hashlib,json,tempfile,time,threading,uuid,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from . import artifacts
from .sandbox import run
from .store import Journal,canonical
from .protocol import CONTRACT

class BudgetExceeded(RuntimeError):pass
class CandidateError(RuntimeError):pass
class TransportError(RuntimeError):pass

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_suffix('.tmp');tmp.write_text(canonical(value));tmp.chmod(0o600)
    with tmp.open('rb') as f:os.fsync(f.fileno())
    os.replace(tmp,path)

def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()

class Meter:
    def __init__(self,root,max_calls=64,max_tokens=300000):
        self.journal=Journal(Path(root)/'calls.jsonl');self.max_calls=max_calls;self.max_tokens=max_tokens
        self.lock=threading.Lock();self.blocked=None
    def totals(self):
        charged=[x for x in self.journal.events if x['type']=='reserve']
        used=[x.get('usage',{}) for x in self.journal.events if x['type']=='response']
        return {'requests':len(charged),'reserved_tokens':sum(x['tokens'] for x in charged),
                'reported_input_tokens':sum(x.get('input',x.get('input_tokens',0))+x.get('cacheRead',x.get('cache_read_input_tokens',0)) for x in used),
                'reported_output_tokens':sum(x.get('output',x.get('output_tokens',0)) for x in used)}
    def reserve(self,body,operation):
        # UTF-8 byte count is a conservative input bound; include framing margin.
        bound=len(canonical(body).encode())+int(body['max_tokens'])+512
        with self.lock:
            totals=self.totals()
            if totals['requests']>=self.max_calls or totals['reserved_tokens']+bound>self.max_tokens:
                self.blocked='request/token reservation budget exhausted';raise BudgetExceeded(self.blocked)
            self.journal.append({'type':'reserve','operation':operation,'tokens':bound,'time':time.time()})
    def response(self,operation,value):
        with self.lock:self.journal.append({'type':'response','operation':operation,'usage':value.get('usage',{}),'time':time.time()})

class Engine:
    def __init__(self,root,model='glm-5.3-flash',max_calls=64,max_tokens=300000,parallel=2,provider=None):
        self.root=Path(root);self.model=model;self.meter=Meter(root,max_calls,max_tokens)
        self.parallel=parallel;self.provider=provider;self.model_lock=threading.Lock()
        if parallel not in (1,2):raise ValueError('parallel must be 1 or 2')
    def model_call(self,tool,request,operation,max_tokens=2048):
        key=digest({'operation':operation,'tool':tool,'model':self.model,'request':request,'max_tokens':max_tokens})
        path=self.root/'responses'/f'{key}.json'
        # Serialize heavy model runtimes, allowing independent code contexts to overlap.
        with self.model_lock:
            if path.exists():return json.loads(path.read_text())
            self.meter.blocked=None
            if self.provider:
                self.meter.reserve({'prompt':request,'max_tokens':max_tokens},operation)
                value=self.provider(tool,request,operation,max_tokens)
            else:
                from .live import invoke,EmptyModelResponse
                # Two attempts in total, including across process restarts. Each is
                # charged by the broker before HTTP, even when no answer is returned.
                failures=sum(e.get('type')=='empty_response' and e.get('operation')==operation
                             for e in self.meter.journal.events)
                if failures>=2:raise TransportError('empty response retry limit exhausted for '+operation)
                for attempt in range(failures,2):
                    try:
                        value=invoke(tool,request,self.model,max_tokens,managed=True,charge=lambda body:self.meter.reserve(body,operation))
                        break
                    except EmptyModelResponse as e:
                        self.meter.response(operation,{'usage':e.diagnostic.get('usage',{})})
                        self.meter.journal.append({'type':'empty_response','operation':operation,
                            'attempt':attempt+1,'diagnostic':e.diagnostic,'time':time.time()})
                        if attempt==1:raise TransportError(str(e)+'; retry limit exhausted') from None
                        time.sleep(1)
                    except Exception as e:
                        if self.meter.blocked:raise BudgetExceeded(self.meter.blocked) from None
                        raise TransportError(str(e)) from None
            self.meter.response(operation,value);atomic(path,value)
            return value
    def python(self,code,cwd,stdin=''):
        # Candidate-controlled source gets no model endpoint/key and cannot fork.
        if not isinstance(code,str) or len(code.encode())>65536:raise CandidateError('invalid Python primitive')
        r=run(['/usr/bin/python3','-I','-S','-c',"import sys;sys.path.insert(0,'.')\n"+code],cwd,stdin,timeout=12)
        return {k:r[k] for k in ('code','stdout','stderr','timeout','peak_rss_kb')}
    def primitive(self,command,cwd,tool,operation,max_tokens,allow_parallel=True):
        action=command.get('action');started=time.time();context=digest(operation)[:16]
        event={'action':action,'context':context,'started':started}
        if action=='model':
            prompt=command.get('prompt');system=command.get('system','You are a coding agent.')
            if not isinstance(prompt,str) or not isinstance(system,str) or len((prompt+system).encode())>64000:raise CandidateError('model prompt limit')
            value=self.model_call(tool,{'prompt':prompt,'system':system},operation,max_tokens)
            # Agent sees text and usage only, no ledger, credentials, hidden state or host path.
            result={'text':value['text'],'usage':value.get('usage',{})}
        elif action=='python':result=self.python(command['code'],cwd,command.get('stdin',''))
        elif action=='context' and not allow_parallel:
            child_files=artifacts.validate(command.get('files',{}))
            child=self.harness(child_files,command.get('entry','executor.py'),command.get('input',{}),tool,operation+'/context',max_tokens=max_tokens,allow_parallel=False)
            result={'result':child['result'],'files':child['workspace'],'events':child['events']}
        elif action=='parallel' and allow_parallel:
            jobs=command.get('jobs',[])
            if not isinstance(jobs,list) or not 1<=len(jobs)<=self.parallel:raise CandidateError('parallel budget')
            def job(i,spec):
                with tempfile.TemporaryDirectory(prefix='rqgm-context-') as directory:
                    artifacts.write(directory,spec.get('files',{}))
                    value,child=self.primitive(spec,directory,tool,operation+f'/job-{i}',max_tokens,False)
                    return {'result':value,'files':artifacts.collect(directory),'event':child}
            with ThreadPoolExecutor(max_workers=self.parallel) as pool:
                futures=[pool.submit(job,i,spec) for i,spec in enumerate(jobs)]
                result=[f.result() for f in futures]
            event['jobs']=[x['event'] for x in result]
        else:raise CandidateError('unsupported primitive')
        event['ended']=time.time();return result,event
    def harness(self,files,entry,payload,tool,operation,*,workspace=None,max_steps=8,max_model_calls=3,max_tokens=2048,allow_parallel=True):
        artifacts.validate(files)
        if entry not in files:raise CandidateError('entry missing')
        # Each turn re-enters arbitrary candidate Python, with explicit candidate-owned state.
        with tempfile.TemporaryDirectory(prefix='rqgm-harness-') as cwd:
            artifacts.write(cwd,files)
            if workspace:artifacts.write(cwd,workspace)
            state=None;observation=None;events=[];model_calls=0;deadline=time.monotonic()+420
            for step in range(max_steps):
                if time.monotonic()>deadline:raise CandidateError('harness wall budget')
                command=self.python('import runpy;runpy.run_path('+repr(entry)+',run_name="__main__")',cwd,canonical({'input':payload,'state':state,'observation':observation}))
                if command['code'] or command['timeout']:raise CandidateError('entry failure: '+command['stderr'][-1500:])
                try:command=json.loads(command['stdout'])
                except ValueError:raise CandidateError('entry returned invalid JSON') from None
                if not isinstance(command,dict):raise CandidateError('entry must return object')
                action=command.get('action')
                if action=='finish':
                    return {'result':command.get('result'),'workspace':artifacts.collect(cwd),'events':events}
                requested=int(action=='model')+sum(j.get('action')=='model' for j in command.get('jobs',[]) if isinstance(j,dict))
                model_calls+=requested
                if model_calls>max_model_calls:raise CandidateError('per-turn model call limit')
                state=command.get('state')
                observation,event=self.primitive(command,cwd,tool,f'{operation}/step-{step}',max_tokens,allow_parallel)
                events.append(event)
            raise CandidateError('harness step budget exhausted')
