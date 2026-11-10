import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from rqgm_lab.engine import Engine,BudgetExceeded,CandidateError,Meter
from rqgm_lab.experiment import Experiment
from rqgm_lab import artifacts,scenarios,anchors
from rqgm_lab.recovery import recover,valid_prefix
from rqgm_lab.store import Archive,Journal
from rqgm_lab.node_tools import list_nodes,export_node,resolve,parse_tasks

STRICT_JUDGE='''import json,sys
x=json.load(sys.stdin);c=x.get('checks');ok=type(x.get('execution_error')) is bool and x['execution_error'] is False and isinstance(c,list) and bool(c)
if ok:
 ids=[v.get('id') for v in c if isinstance(v,dict)]
 ok=len(ids)==len(c) and all(isinstance(i,str) and bool(i) for i in ids) and len(set(ids))==len(ids) and all(type(v.get('ok')) is bool and v['ok'] for v in c)
print(json.dumps({'ok':bool(ok)}))
'''

def suite():
    return {'cases':[{'id':g,'goal':g,'rationale':'Offline fixture only; not a research capability claim','difficulty':'fixture','turns':['Return OK'],'files':{},'oracle':"def check(o):\n return o.get('answers') == ['OK']\n",'positive':{'answers':['OK'],'files':{},'events':[]},'negatives':[{'answers':['BAD'],'files':{},'events':[]}]} for g in ('distributed','individuality')]}

class FakeProvider:
    def __init__(self):self.calls=[]
    def __call__(self,tool,request,operation,max_tokens):
        self.calls.append((tool,request,operation))
        try:body=json.loads(request['prompt'])
        except ValueError:body={}
        if not isinstance(body,dict):body={}
        if 'case_contract' in body:value=suite()
        elif 'files' in body:
            files=dict(body['files'])
            if 'meta.py' in files:files['meta.py']+='\n# offline fixture mutation\n'
            else:
                files['judge.py']=STRICT_JUDGE
                files['.claude/skills/challenge/SKILL.md']+='\nValidate duplicate evidence IDs.\n'
            value={'files':files,'strategy':'offline fixture proposal'}
        else:return {'text':'OK','usage':{'input':10,'output':2},'simulated':True}
        return {'text':('def build_suite():\n    return ' if 'case_contract' in body else 'def build_patch():\n    return ')+repr(value),'usage':{'input':10,'output':20},'simulated':True}

def fake_regression(*args,**kwargs):return {'ok':12,'total':12,'details':[],'dataset_sha256':'fixture'}

class ExperimentTests(unittest.TestCase):
    def test_real_control_path_resume_epoch_and_no_hidden_feedback(self):
        provider=FakeProvider()
        with tempfile.TemporaryDirectory() as d,patch('rqgm_lab.experiment.regression',fake_regression):
            lab=Experiment(d,provider=provider,max_tokens=1000000)
            result=lab.run(2)
            self.assertEqual(lab.s['epoch'],1);self.assertIsNone(result['winner'])
            self.assertEqual(len(lab.s['records']),2);self.assertEqual(len(lab.s['trees']['seed']),2)
            self.assertTrue((Path(d)/'report.html').exists());lab.close()
            resumed=Experiment(d,provider=provider,max_tokens=1000000)
            result=resumed.run(3);self.assertEqual(result['evaluations'],3);self.assertIsNotNone(result['winner'])
            self.assertEqual(len(resumed.s['records']),3);resumed.close()
            prompts=json.dumps(provider.calls)
            for hidden in ('Mbpp/','canonical_solution','private_regression','baseline','anchor_scores'):
                self.assertNotIn(hidden,prompts)
    def test_budget_stop_and_cached_model_response(self):
        with tempfile.TemporaryDirectory() as d:
            p=FakeProvider();e=Engine(d,provider=p,max_calls=1)
            e.model_call('pi',{'prompt':'a'},'a');e.model_call('pi',{'prompt':'a'},'a')
            self.assertEqual(len(p.calls),1)
            with self.assertRaises(BudgetExceeded):e.model_call('pi',{'prompt':'b'},'b')
            self.assertEqual(e.meter.totals()['requests'],1)
    def test_invalid_candidate_no_commit_to_tree(self):
        p=FakeProvider()
        with tempfile.TemporaryDirectory() as d,patch('rqgm_lab.experiment.regression',fake_regression):
            lab=Experiment(d,provider=p,max_tokens=1000000);lab.initialize();lab.begin('expand_seed')
            with patch.object(lab,'proposal',side_effect=CandidateError('invalid')):lab.expand_seed()
            self.assertEqual(len(lab.s['trees']['seed']),1);self.assertIsNone(lab.s['pending']);lab.close()
    def test_parallel_isolated_contexts_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            engine=Engine(d,provider=FakeProvider())
            files={'executor.py':'''import json,sys
x=json.load(sys.stdin)
if x['observation'] is None:
 print(json.dumps({'action':'parallel','jobs':[{'action':'python','code':"import time;open('private.txt','w').write('a');time.sleep(0.3);print('a')"},{'action':'python','code':"import time,os;assert not os.path.exists('private.txt');time.sleep(0.3);print('b')"}]}))
else:print(json.dumps({'action':'finish','result':x['observation']}))
'''}
            result=engine.harness(files,'executor.py',{},'pi','parallel-test')
            jobs=result['events'][0]['jobs'];self.assertNotEqual(jobs[0]['context'],jobs[1]['context'])
            self.assertLess(max(j['started'] for j in jobs),min(j['ended'] for j in jobs))
            self.assertEqual(result['result'][0]['result']['code'],0);self.assertEqual(result['result'][1]['result']['code'],0)
    def test_suite_controls_reject_vacuous_oracle(self):
        data=suite();data['cases'][0]['oracle']='def check(o):\n return True\n'
        with self.assertRaises(CandidateError):scenarios.validate_suite(data)
    def test_strict_anchor_judge(self):self.assertEqual(anchors.score({'judge.py':STRICT_JUDGE})['ok'],16)
    def test_symlink_export_denied(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):artifacts.collect(d)
    def test_corrupt_tail_recovery_retains_original(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source';src.mkdir();j=Journal(src/'events.jsonl');j.append({'value':1})
            with (src/'events.jsonl').open('ab') as f:f.write(b'{"partial":')
            original=(src/'events.jsonl').read_bytes();dst=Path(d)/'recovered'
            recover(src,dst)
            self.assertEqual((src/'events.jsonl').read_bytes(),original)
            self.assertEqual((dst/'events.jsonl.original').read_bytes(),original)
            self.assertEqual(Journal(dst/'events.jsonl').events,[{'value':1}])
    def test_journal_state_is_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            j=Journal(Path(d)/'events');state={'n':1};j.append(state);state['n']=2
            self.assertEqual(j.events[0]['n'],1)

class AdditionalBoundaryTests(unittest.TestCase):
    def test_independent_contexts_can_run_multiple_steps(self):
        child='''import json,sys
x=json.load(sys.stdin)
if x['observation'] is None:print(json.dumps({'action':'model','prompt':x['input']['task']}))
else:print(json.dumps({'action':'finish','result':x['observation']['text']}))
'''
        jobs=[{'action':'context','entry':'executor.py','files':{'executor.py':child},'input':{'task':str(i)}} for i in range(2)]
        with tempfile.TemporaryDirectory() as d:
            provider=FakeProvider();engine=Engine(d,provider=provider)
            result,event=engine.primitive({'action':'parallel','jobs':jobs},d,'pi','independent',512)
            self.assertEqual([x['result']['result'] for x in result],['OK','OK'])
            self.assertEqual(len(provider.calls),2)
            self.assertEqual(len(set(x[2] for x in provider.calls)),2)
    def test_invalid_oracle_observation_is_not_seed_failure_evidence(self):
        from rqgm_lab.search import active
        case=suite()['cases'][0];case['oracle']="def check(o):\n return o['missing']\n"
        with patch('rqgm_lab.scenarios.observe',return_value=({'answers':[]},None)):
            result=scenarios.evaluate(None,{}, {},case,'invalid-oracle')
            self.assertFalse(result['usable'])
            self.assertEqual(active([{'ok':False,'usable':False,'deps':{}}],{}),[])
    def test_local_imports_in_editable_harness(self):
        with tempfile.TemporaryDirectory() as d:
            e=Engine(d,provider=FakeProvider())
            result=e.harness({'helper.py':'VALUE=7\n','executor.py':"import helper,json\nprint(json.dumps({'action':'finish','result':helper.VALUE}))\n"},'executor.py',{},'pi','local-import')
            self.assertEqual(result['result'],7)
    def test_capabilities_are_zero(self):
        from rqgm_lab.sandbox import run
        code='''import ctypes as C,json
class H(C.Structure):_fields_=[('version',C.c_uint32),('pid',C.c_int)]
class D(C.Structure):_fields_=[('effective',C.c_uint32),('permitted',C.c_uint32),('inheritable',C.c_uint32)]
h=H(0x20080522,0);d=(D*2)();assert C.CDLL(None).capget(C.byref(h),C.byref(d))==0
print(json.dumps([v.effective|v.permitted|v.inheritable for v in d]))
'''
        with tempfile.TemporaryDirectory() as d:
            result=run(['/usr/bin/python3','-I','-S','-c',code],d)
            self.assertEqual(json.loads(result['stdout']),[0,0])

class NodeToolTests(unittest.TestCase):
    def test_list_resolve_and_export_immutable_node(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);archive=Archive(root/'objects.git')
            seed=archive.commit({'executor.py':'# executor\n','meta.py':'# meta\n'})
            challenger=archive.commit({'generate.py':'# generate\n','improve.py':'# improve\n',
                'judge.py':'# judge\n','.claude/skills/challenge/SKILL.md':'# skill\n'})
            state={'trees':{'seed':{seed:{'parent':None,'strategy':'root'}},
                    'challenger':{challenger:{'parent':None,'strategy':'root'}}},
                   'slots':{'challenger':challenger}}
            Journal(root/'events.jsonl').append({'type':'state','state':state})
            self.assertEqual(resolve(root,'seed',seed[:12]),seed)
            self.assertEqual(len(list_nodes(root)),2)
            exported=export_node(root,'challenger',challenger[:12],root/'exported')
            self.assertEqual(Path(exported['destination'],'.claude/skills/challenge/SKILL.md').read_text(),'# skill\n')
            self.assertEqual(parse_tasks('3, Mbpp/4'),['Mbpp/3','Mbpp/4'])
