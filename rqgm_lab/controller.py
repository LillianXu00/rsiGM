import argparse,fcntl,hashlib,html,json,os,random,tempfile,time,signal
from pathlib import Path
from .sandbox import ROOT
from .store import Archive,Journal,canonical
from .search import active,sample,cell,best
from .vendor.beta import best_belief
from .providers import proposal,editable,pi
from .validation import regression,anchor,prepare

class Lab:
    def __init__(self,root,budget=16):
        self.root=Path(root).resolve();self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.lock=(self.root/'lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.j=Journal(self.root/'events.jsonl');self.archive=Archive(self.root/'objects.git')
        self.budget=budget
        trusted={str(p.relative_to(ROOT)):p.read_text() for p in (ROOT/'rqgm_lab').rglob('*.py')}
        for name in ['runtime/pi-bridge.mjs','runtime/package-lock.json','docs/PLAN.md']:
            trusted[name]=(ROOT/name).read_text()
        self.code_version=self.archive.commit(trusted,message='trusted controller snapshot')
        states=[e['state'] for e in self.j.events if e['type']=='commit']
        if states:self.s=states[-1]
        else:
            trees={}
            for kind in ['seed','challenger']:
                base=ROOT/'seeds'/kind
                files={str(p.relative_to(base)):p.read_text() for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
                sha=self.archive.commit(files,message=kind+' root')
                trees[kind]={sha:{'parent':None,'strategy':'initial seed'}}
            incumbent=next(iter(trees['challenger']))
            self.s={'trees':trees,'records':[],'slots':{'challenger':incumbent},'epoch':0,'n':0,'checkpoint':4,'step':0,'training':[], 'baseline':None,'failed_expansions':[]}
            self.commit('initialize')
    def commit(self,reason,**details):
        self.j.append({'type':'commit','reason':reason,'time':time.time(),'state':self.s,'details':details,'controller_commit':self.code_version})
    def rng(self):return random.Random(1949+self.s['step'])
    def evaluate(self):
        s=self.s;rng=self.rng();records=active(s['records'],s['slots'])
        n,draws=sample(s['trees']['seed'],records,rng)
        role,task=cell(records,n,[('execution','generated')],rng)
        # Frozen mock generator distribution, seeded by epoch and evaluation number.
        # Training and selection draw different examples; no fixed real task bank.
        case=editable(self.archive,s['slots']['challenger'],'generate.py',{'nonce':100000*s['epoch']+s['n']})
        x=case['input']
        req=editable(self.archive,n,'executor.py',{'task':case['prompt']})
        result=pi(req,str(x*x if s['n']%3 else x))
        observed=int(result['text']); expected=case['expected']
        verdict=editable(self.archive,s['slots']['challenger'],'judge.py',{'observed':observed,'expected':expected})
        if type(verdict.get('ok')) is not bool:raise ValueError('invalid verdict')
        rec={'id':len(s['records']),'node':n,'role':role,'task':task,'ok':verdict['ok'],
             'deps':dict(s['slots']),'epoch':s['epoch'],'test_version':s['slots']['challenger'],
             'trace':{'case':case,'input':x,'output':observed,'runtime':result['runtime'],'resources':result.get('resources',{})},'usage':result['usage'],'kind':'selection'}
        s['records'].append(rec);s['n']+=1;s['step']+=1
        self.commit('evaluate',draws=draws,selected=n)
    def expand(self,kind):
        s=self.s;rng=self.rng();tree=s['trees'][kind]
        rec=active(s['records'],s['slots']) if kind=='seed' else s.get('challenger_records',[])
        parent,draws=sample(tree,rec,rng,expand=True)
        # Demand-driven training: fresh public artifact, never search/hidden evidence.
        train={'task':f'Check a fresh arithmetic example {rng.randrange(1000)}','observation':'mock training trace; verify claims with executable controls'}
        prop,trace=proposal(self.archive,parent,kind,[train])
        files=prop['files']
        required=['meta.py','executor.py'] if kind=='seed' else ['judge.py','generate.py','.claude/skills/challenge/SKILL.md']
        if any(p not in files for p in required):raise ValueError('candidate removed entry point')
        for name,value in files.items():
            if name.endswith('.py'):compile(value,name,'exec')
        sha=self.archive.commit(files,parent,prop['strategy'])
        gate=None
        if kind=='challenger':
            for nonce in [917,918]:
                case=editable(self.archive,sha,'generate.py',{'nonce':nonce})
                positive=editable(self.archive,sha,'judge.py',{'observed':case['reference'],'expected':case['expected']})
                negative=editable(self.archive,sha,'judge.py',{'observed':case['negative_control'],'expected':case['expected']})
                if positive.get('ok') is not True or negative.get('ok') is not False:
                    raise ValueError('invalid generated scenario controls')
        if kind=='seed':
            gate=regression(self.archive,sha)
            if gate['ok']<s['baseline']:
                s['failed_expansions'].append({'parent':parent,'commit':sha})
                s['step']+=1;self.commit('candidate_rejected',candidate=sha,private_gate=gate);return
        tree[sha]={'parent':parent,'strategy':prop['strategy']}
        s['step']+=1
        if kind=='challenger':s['checkpoint_candidate_ready']=True
        self.commit('expand',kind=kind,parent=parent,candidate=sha,draws=draws,trace=trace,training=train,private_gate=gate)
    def checkpoint(self):
        if not self.s.get('checkpoint_candidate_ready'):
            self.expand('challenger')
        s=self.s;old=s['slots']['challenger'];scores={};anchor_rows=[]
        for node in s['trees']['challenger']:
            result=anchor(self.archive,node)
            scores[node]=best_belief(result['ok'],result['total']-result['ok'])
            # Fixed full anchor per candidate; repeated checks are NOT independent new evidence.
            for i,ok in enumerate(result['outcomes']):anchor_rows.append({'node':node,'ok':ok,'deps':{},'task':i})
        s['challenger_records']=anchor_rows
        winner=old
        for node in scores:
            if scores[node]>scores[winner]+1e-12:winner=node
        invalidated=[]
        if winner!=old:
            invalidated=[r['id'] for r in active(s['records'],s['slots']) if 'challenger' in r['deps']]
            s['slots']['challenger']=winner;s['epoch']+=1
        s.pop('checkpoint_candidate_ready',None)
        s['checkpoint']*=2;s['step']+=1
        self.commit('checkpoint',winner=winner,incumbent=old,private_anchor_scores=scores,invalidated=invalidated)
    def run(self):
        s=self.s
        if s['baseline'] is None:
            r=regression(self.archive,next(k for k,v in s['trees']['seed'].items() if v['parent'] is None))
            s['baseline']=r['ok'];self.commit('baseline',private_result=r)
        while s['n']<self.budget:
            # A pending boundary is committed before any new epoch evaluations.
            if s['n']>=s['checkpoint']:self.checkpoint();continue
            action='expand' if s['n']**0.5>=len(s['trees']['seed'])+len(s['failed_expansions']) else 'evaluate'
            self.j.append({'type':'begin','step':s['step'],'action':action})
            try:
                if action=='expand':self.expand('seed')
                else:self.evaluate()
            except Exception as e:
                self.j.append({'type':'failure','step':s['step'],'error':repr(e)})
                # Durable last committed state remains the rollback target; do not silently skip.
                raise
        if s['n']>=s['checkpoint']:self.checkpoint()
        winner=best(s['trees']['seed'],active(s['records'],s['slots']))
        self.j.append({'type':'result','winner':winner,'n':s['n'],'epoch':s['epoch'],'mock':True})
        self.report();return winner
    def report(self):
        s=self.s;rows=[]
        for kind,tree in s['trees'].items():
            for sha,n in tree.items():rows.append('<tr><td>'+kind+'</td><td>'+sha[:12]+'</td><td>'+(n['parent'] or 'root')[:12]+'</td><td>'+html.escape(n['strategy'])+'</td></tr>')
        checkpoints=[e for e in self.j.events if e.get('reason')=='checkpoint']
        body=f'<h1>RQGM mock experiment</h1><p>Control-flow simulation; no evidence of emergent agent capabilities.</p><p>Evaluations: {s["n"]}; epoch: {s["epoch"]}; active records: {len(active(s["records"],s["slots"]))}/{len(s["records"])}</p>'
        body+='<table><tr><th>Tree</th><th>Commit</th><th>Parent</th><th>Strategy</th></tr>'+''.join(rows)+'</table>'
        body+='<h2>Epoch transitions</h2><pre>'+html.escape(json.dumps([e['details'] for e in checkpoints],indent=2))+'</pre>'
        (self.root/'report.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;background:#f5f6f8}td,th{padding:12px;border-bottom:1px solid #ccc;text-align:left}pre{white-space:pre-wrap}</style>'+body)

def main():
    def interrupted(signum,frame):raise KeyboardInterrupt('signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','report','prepare','calibrate']);p.add_argument('--root',default='runs/mock');p.add_argument('--budget',type=int,default=8);a=p.parse_args()
    if a.command=='prepare':prepare();print('Private regression bundle prepared');return
    if a.budget<1 or a.budget>128:p.error('mock budget must be 1..128')
    execution_lock=None
    if a.command in ('run','calibrate'):
        (ROOT/'runs').mkdir(exist_ok=True)
        execution_lock=(ROOT/'runs/.execution.lock').open('a')
        fcntl.flock(execution_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lab=Lab(a.root,a.budget)
    if a.command=='run':
        try:print(lab.run())
        except KeyboardInterrupt:
            lab.j.append({'type':'interrupted','step':lab.s['step']});raise SystemExit(130)
    elif a.command=='report':lab.report()
    else:
        r=regression(lab.archive,next(k for k,v in lab.s['trees']['seed'].items() if v['parent'] is None),calibrate=True)
        lab.j.append({'type':'calibration','private_result':r});print('Reference calibration:',r['ok'],'/',r['total'])
if __name__=='__main__':main()
