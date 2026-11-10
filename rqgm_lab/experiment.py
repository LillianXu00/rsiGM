"""Real RQGM experiment. No synthetic model answers or scripted candidate patches."""
import argparse,fcntl,json,os,random,signal,time,hashlib
from pathlib import Path
from .sandbox import ROOT
from .store import Archive,Journal,canonical
from .engine import Engine,BudgetExceeded,CandidateError,TransportError,atomic,digest
from . import artifacts,anchors,scenarios
from .protocol import CONTRACT,GOALS,CASE_CONTRACT
from .regression_live import regression
from .search import active,sample,cell,best,counts
from .vendor.beta import best_belief

class Experiment:
    def __init__(self,root,*,model='glm-5.3-flash',first_checkpoint=2,min_regression=10,
                 max_calls=80,max_tokens=600000,parallel=2,provider=None):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=(self.root/'lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.j=Journal(self.root/'events.jsonl');self.archive=Archive(self.root/'objects.git')
        self.engine=Engine(self.root,model,max_calls,max_tokens,parallel,provider)
        source={str(p.relative_to(ROOT)):p.read_text() for p in (ROOT/'rqgm_lab').rglob('*.py')}
        source['runtime/pi-bridge.mjs']=(ROOT/'runtime/pi-bridge.mjs').read_text()
        source['runtime/package-lock.json']=(ROOT/'runtime/package-lock.json').read_text()
        self.source_hash=digest(source)
        self.source_commit=self.archive.commit(source,message='trusted source snapshot')
        private_hash=hashlib.sha256((ROOT/'private/regression.json').read_bytes()).hexdigest()
        config={'mode':'live' if provider is None else 'test','model':model,'first_checkpoint':first_checkpoint,
                'min_regression':min_regression,'parallel':parallel,'alpha':0.5,'epsilon':0.05,'dataset':private_hash}
        snapshots=[e['state'] for e in self.j.events if e['type']=='state']
        if snapshots:
            self.s=snapshots[-1]
            if self.s['config']!=config:raise RuntimeError('immutable experiment config mismatch; use a new run directory')
            if self.s['source_hash']!=self.source_hash:raise RuntimeError('trusted source changed; use archived source or a new run directory')
        else:
            trees={}
            for kind in ('seed','challenger'):
                files=artifacts.collect(ROOT/'seeds'/('live_'+kind))
                commit=self.archive.commit(files,message='live '+kind+' root')
                trees[kind]={commit:{'parent':None,'strategy':'minimal unprescribed seed'}}
            incumbent=next(iter(trees['challenger']));self.s={
                'config':config,'source_hash':self.source_hash,'trees':trees,'slots':{'challenger':incumbent},
                'suites':{},'records':[],'challenger_records':[],'n':0,'epoch':0,'step':0,
                'checkpoint':first_checkpoint,'baseline':None,'training':[],'rejected':[],
                'last_expand_at':-1,'pending':None,'bootstrap_failures':0}
            self.save('initialize')
        # Validate candidate graph and dataset fingerprint on every resume.
        for tree in self.s['trees'].values():
            if any(v['parent'] is not None and v['parent'] not in tree for v in tree.values()):raise RuntimeError('broken lineage')
    def close(self):self.lock.close()
    def event(self,kind,**data):self.j.append({'type':kind,'time':time.time(),**data})
    def save(self,reason,**details):
        self.event('state',reason=reason,state=self.s,controller_commit=self.source_commit,details=details)
    def seed_root(self):return next(k for k,v in self.s['trees']['seed'].items() if v['parent'] is None)
    def files(self,node):return self.archive.files(node)
    def rng(self):return random.Random(1949+self.s['step'])
    def regress(self,node,operation):
        path=self.root/'regression-progress'/(digest({'node':node,'operation':operation})+'.json')
        completed=json.loads(path.read_text()) if path.exists() else []
        def save(rows):
            self.event('private_regression_task',operation=operation,node=node,row=rows[-1]);atomic(path,rows)
        return regression(self.engine,self.files(node),operation,save,completed)
    def initialize(self):
        s=self.s;incumbent=s['slots']['challenger']
        if incumbent not in s['suites']:
            if s['bootstrap_failures']>=3:raise RuntimeError('three invalid initial suites; inspect recorded generation failures')
            op='bootstrap-'+str(s['bootstrap_failures'])
            try:
                suite,trace=scenarios.generate(self.engine,self.files(incumbent),self.files(self.seed_root()),s['training'],op)
            except (CandidateError,ValueError,KeyError,TypeError) as e:
                s['bootstrap_failures']+=1
                # Public generation failure can inform the next generation, never hidden validation.
                s['training']=[{'generation_failure':str(e)}];self.save('invalid_initial_suite',error=str(e));return False
            s['suites'][incumbent]=suite;self.save('freeze_initial_suite',trace=trace)
        if s['baseline'] is None:
            result=self.regress(self.seed_root(),'baseline')
            s['baseline']=result['ok'];self.save('baseline',private_result=result)
        if s['baseline']<s['config']['min_regression']:
            raise RuntimeError('initial coding baseline below configured acceptance floor; review private report before starting a new run')
        return True
    def begin(self,kind):
        s=self.s;rng=self.rng();txn={'kind':kind,'id':f"step-{s['step']}-{kind}"}
        if kind=='evaluate':
            records=active(s['records'],s['slots']);node,draws=sample(s['trees']['seed'],records,rng)
            suite=s['suites'][s['slots']['challenger']]
            balanced=[r for r in s['records'] if r['deps']==s['slots']]
            role,task=cell(balanced,node,[(c['goal'],c['id']) for c in suite['cases']],rng)
            txn.update(node=node,draws=draws,role=role,task=task)
        else:
            which='seed' if kind=='expand_seed' else 'challenger'
            records=active(s['records'],s['slots']) if which=='seed' else s['challenger_records']
            parent,draws=sample(s['trees'][which],records,rng,expand=True)
            txn.update(parent=parent,draws=draws)
        s['pending']=txn;self.save('begin',transaction=txn)
    def finish(self,reason,**details):
        self.s['pending']=None;self.s['step']+=1;self.save(reason,**details)
    def train(self,txn,node):
        if 'training' in txn:return txn['training']
        incumbent=self.s['slots']['challenger'];files=self.files(node)
        suite,trace=scenarios.generate(self.engine,self.files(incumbent),files,self.s['training'][-2:],txn['id']+'/training-generation')
        case=suite['cases'][0]
        result=scenarios.evaluate(self.engine,files,self.files(incumbent),case,txn['id']+'/training-execution')
        public={'case':case,'result':result}
        txn['training']=public;self.s['training']=(self.s['training']+[public])[-3:]
        self.save('training',transaction=txn['id'],node=node,trace=trace,public=public)
        return public
    def proposal(self,txn,kind):
        if 'candidate' in txn:return txn['candidate']
        parent=txn['parent'];parent_files=self.files(parent)
        if kind=='seed':node=parent
        else:
            records=active(self.s['records'],self.s['slots'])
            node=best(self.s['trees']['seed'],records) if records else self.seed_root()
        training=self.train(txn,node)
        payload={'files':parent_files,'current_agent':self.files(node),'training':[training],
                 'goals':GOALS,'primitive_contract':CONTRACT,'evidence_contract':scenarios.JUDGE_CONTRACT}
        result=self.engine.harness(parent_files,'meta.py' if kind=='seed' else 'improve.py',payload,
            'pi' if kind=='seed' else 'claude',txn['id']+'/proposal',max_tokens=4096,max_model_calls=2)
        self.event('proposal',transaction=txn['id'],trace=result)
        proposal=result['result']
        if not isinstance(proposal,dict):raise CandidateError('proposal object required')
        files=artifacts.validate(proposal['files'])
        required=['meta.py','executor.py'] if kind=='seed' else ['generate.py','improve.py','judge.py','.claude/skills/challenge/SKILL.md']
        if any(name not in files for name in required):raise CandidateError('entry removed')
        for name,text in files.items():
            if name.endswith('.py'):compile(text,name,'exec')
        if files==parent_files:raise CandidateError('proposal made no change')
        strategy=proposal.get('strategy','unspecified')
        if not isinstance(strategy,str) or len(strategy)>4000:raise CandidateError('invalid strategy')
        sha=self.archive.commit(files,parent,strategy)
        txn['candidate']=sha;txn['strategy']=strategy;self.save('candidate_created',transaction=txn['id'],candidate=sha)
        return sha
    def expand_seed(self):
        s=self.s;txn=s['pending'];s['last_expand_at']=s['n']
        try:
            candidate=self.proposal(txn,'seed')
            result=self.regress(candidate,txn['id']+'/candidate-regression')
            if result['ok']<max(s['baseline'],s['config']['min_regression']):
                s['rejected'].append({'commit':candidate,'parent':txn['parent'],'kind':'seed'})
                self.finish('candidate_rejected',candidate=candidate,private_result=result);return
            s['trees']['seed'][candidate]={'parent':txn['parent'],'strategy':txn['strategy']}
            self.finish('seed_expanded',candidate=candidate,draws=txn['draws'],private_result=result)
        except (CandidateError,ValueError,KeyError,TypeError,SyntaxError) as e:
            s['rejected'].append({'commit':txn.get('candidate'),'parent':txn['parent'],'kind':'seed'})
            self.finish('candidate_invalid',error=str(e),transaction=txn['id'])
    def evaluate(self):
        s=self.s;txn=s['pending'];incumbent=s['slots']['challenger']
        case=next(c for c in s['suites'][incumbent]['cases'] if c['id']==txn['task'])
        result=scenarios.evaluate(self.engine,self.files(txn['node']),self.files(incumbent),case,txn['id'])
        s['records'].append({'id':len(s['records']),'node':txn['node'],'role':txn['role'],'task':txn['task'],
            'ok':result['ok'],'usable':result.get('usable',True),'deps':dict(s['slots']),'epoch':s['epoch'],'test_version':digest(case),
            'trace':result,'kind':'selection'})
        s['n']+=1;self.finish('evaluate',draws=txn['draws'],node=txn['node'])
    def checkpoint(self):
        s=self.s;txn=s['pending'];old=s['slots']['challenger'];new=None
        try:
            new=self.proposal(txn,'challenger')
            if new not in s['suites']:
                current=best(s['trees']['seed'],active(s['records'],s['slots']))
                suite,trace=scenarios.generate(self.engine,self.files(new),self.files(current),s['training'][-2:],txn['id']+'/candidate-suite')
                s['suites'][new]=suite;self.save('candidate_suite_frozen',candidate=new,trace=trace)
            s['trees']['challenger'][new]={'parent':txn['parent'],'strategy':txn['strategy']}
        except (CandidateError,ValueError,KeyError,TypeError,SyntaxError) as e:
            s['rejected'].append({'commit':txn.get('candidate'),'parent':txn['parent'],'kind':'challenger'})
            self.event('challenger_invalid',transaction=txn['id'],error=str(e));new=None
        scores={};records=[]
        for node in sorted(s['trees']['challenger']):
            result=anchors.score(self.files(node))
            scores[node]=best_belief(result['ok'],result['total']-result['ok'])
            records.extend({'node':node,'ok':ok,'deps':{},'task':i} for i,ok in enumerate(result['outcomes']))
        s['challenger_records']=records;winner=old
        for node in sorted(scores):
            if scores[node]>scores[winner]+1e-12:winner=node
        invalidated=[];records=active(s['records'],s['slots'])
        if winner!=old:
            s['previous_epoch_best']={'node':best(s['trees']['seed'],records),'epoch':s['epoch']} if records else None
            invalidated=[r['id'] for r in records if 'challenger' in r['deps']]
            s['slots']['challenger']=winner;s['epoch']+=1
        s['checkpoint']*=2
        self.finish('checkpoint',old=old,winner=winner,private_anchor_scores=scores,invalidated=invalidated)
    def run(self,budget):
        while not self.initialize():pass
        while self.s['n']<budget or self.s['n']>=self.s['checkpoint'] or self.s['pending']:
            s=self.s
            if not s['pending']:
                if s['n']>=s['checkpoint']:kind='checkpoint'
                elif s['n']**s['config']['alpha']>=len(s['trees']['seed']) and s['last_expand_at']!=s['n']:kind='expand_seed'
                else:kind='evaluate'
                self.begin(kind)
            {'evaluate':self.evaluate,'expand_seed':self.expand_seed,'checkpoint':self.checkpoint}[s['pending']['kind']]()
        records=active(self.s['records'],self.s['slots'])
        result={'winner':best(self.s['trees']['seed'],records) if records else None,
                'epoch':self.s['epoch'],'evaluations':self.s['n'],'usage':self.engine.meter.totals()}
        self.event('result',**result);self.report();return result
    def report(self):
        from .report import render
        render(self.root,self.s,self.j.events,self.engine.meter.totals())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','report','replay','recover','doctor'])
    parser.add_argument('--root',default='runs/live');parser.add_argument('--budget',type=int,default=4)
    parser.add_argument('--max-api-calls',type=int,default=80);parser.add_argument('--max-reserved-tokens',type=int,default=600000)
    parser.add_argument('--model',default='glm-5.3-flash');parser.add_argument('--first-checkpoint',type=int,default=2)
    parser.add_argument('--min-regression',type=int,default=10);parser.add_argument('--parallel',type=int,default=2)
    parser.add_argument('--record',type=int,default=0);parser.add_argument('--destination')
    a=parser.parse_args()
    if a.command=='doctor':
        from .doctor import check
        print(json.dumps(check(),ensure_ascii=False,indent=2));return
    if a.command=='recover':
        from .recovery import recover
        if not a.destination:parser.error('--destination is required; recovery never modifies the original')
        print(recover(a.root,a.destination));return
    if not 1<=a.budget<=128 or not 1<=a.first_checkpoint<=64 or not 1<=a.min_regression<=12 or a.max_api_calls<1 or a.max_reserved_tokens<1:
        parser.error('invalid experiment bounds')
    if a.command in ('report','replay'):
        j=Journal(Path(a.root)/'events.jsonl');s=[e['state'] for e in j.events if e['type']=='state'][-1]
        if a.command=='report':
            from .engine import Meter
            from .report import render
            render(Path(a.root),s,j.events,Meter(a.root).totals());return
        record=s['records'][a.record]
        version=record['deps']['challenger'];case=next(c for c in s['suites'][version]['cases'] if c['id']==record['task'])
        if not record.get('usable',True):raise RuntimeError('record has no valid oracle verdict; inspect original error')
        answer=scenarios.oracle(case['oracle'],record['trace']['observation'])
        expected=record['trace']['evidence']['checks'][0]['ok']
        print(json.dumps({'oracle':answer,'original':expected,'reproduced':answer is expected}))
        if answer is not expected:raise SystemExit(1)
        return
    def interrupted(signum,frame):raise KeyboardInterrupt('signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    (ROOT/'runs').mkdir(exist_ok=True)
    with (ROOT/'runs/.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from .doctor import check
        check()
        lab=Experiment(a.root,model=a.model,first_checkpoint=a.first_checkpoint,min_regression=a.min_regression,
                       max_calls=a.max_api_calls,max_tokens=a.max_reserved_tokens,parallel=a.parallel)
        try:print(json.dumps(lab.run(a.budget),ensure_ascii=False))
        except (BudgetExceeded,KeyboardInterrupt) as e:
            lab.event('stopped',reason=type(e).__name__);lab.report()
            print(json.dumps({'stopped':type(e).__name__,'resume':'rerun same root/config; increase budgets if needed'}));raise SystemExit(130 if isinstance(e,KeyboardInterrupt) else 2)
        except Exception as e:
            lab.event('failure',error=str(e));lab.report();raise
        finally:lab.close()
if __name__=='__main__':main()
