import json,os,random,sys,tempfile,unittest
from pathlib import Path
from rqgm_lab.sandbox import ROOT,run
from rqgm_lab.search import active,clade,counts,sample,cell
from rqgm_lab.store import Journal,Archive
from rqgm_lab.vendor.beta import best_belief

class SearchTests(unittest.TestCase):
    def test_dependency_erasure(self):
        records=[{'node':'a','ok':True,'deps':{}},{'node':'b','ok':False,'deps':{'x':'v1'}},{'node':'b','ok':True,'deps':{'y':'v1'}}]
        self.assertEqual(len(active(records,{'x':'v2','y':'v1'})),2)
        self.assertEqual(len(records),3)
        self.assertEqual(counts(active(records,{'x':'v2','y':'v1'}),{'a','b'}),(2,0))
    def test_cmp_and_quantile(self):
        tree={'a':{'parent':None},'b':{'parent':'a'},'c':{'parent':'b'}}
        self.assertEqual(clade(tree,'a'),set(tree));self.assertEqual(clade(tree,'b'),{'b','c'})
        self.assertAlmostEqual(best_belief(0,0),.05,places=8)
        self.assertGreater(best_belief(16,0),best_belief(8,8))
    def test_balancing(self):
        records=[{'node':'a','role':'r1','task':'t1'}]
        self.assertEqual(cell(records,'a',[('r1','t1'),('r2','t2')],random.Random(1)),('r2','t2'))
    def test_journal_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events';j=Journal(p);j.append({'n':1});j.append({'n':2})
            self.assertEqual(len(Journal(p).events),2)
            p.write_text(p.read_text().replace('"n":1','"n":3'))
            with self.assertRaises(RuntimeError):Journal(p)
    def test_git_parent_and_path(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'objects');p=a.commit({'a.py':'print(1)\n'});c=a.commit({'a.py':'print(2)\n'},p)
            self.assertEqual(a.git('rev-parse',c+'^'),p)
            with self.assertRaises(ValueError):a.commit({'../escape':'x'})

class IsolationTests(unittest.TestCase):
    def probe(self,code,**kw):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'probe.py';p.write_text(code)
            return run(['/usr/bin/python3','-I',str(p)],d,**kw)
    def test_hidden_read_and_write(self):
        with tempfile.TemporaryDirectory() as trusted:
            secret=Path(trusted)/'secret';secret.write_text('hidden')
            r=self.probe(f'''import os,json
out=[]
for mode in ['r','w']:
 try:open({str(secret)!r},mode);out.append(False)
 except PermissionError:out.append(True)
print(json.dumps(out))
''')
            self.assertEqual(json.loads(r['stdout']),[True,True]);self.assertEqual(secret.read_text(),'hidden')
    def test_proc_network_fork_and_symlink(self):
        r=self.probe(f'''import os,json,socket
out=[]
os.symlink({str(ROOT/'private/regression.json')!r},'link')
for fn in [lambda:open('link'),lambda:open('/proc/1/environ'),lambda:socket.socket(),lambda:os.fork(),lambda:open({str(ROOT/'rqgm_lab/controller.py')!r})]:
 try:fn();out.append(False)
 except PermissionError:out.append(True)
print(json.dumps(out))
''')
        self.assertEqual(json.loads(r['stdout']),[True]*5)
    def test_timeout(self):
        r=self.probe('while True: pass',timeout=.2);self.assertTrue(r['timeout'])
    def test_output_limit(self):
        r=self.probe("import os\nwhile True: os.write(1,b'x'*65536)")
        self.assertNotEqual(r['code'],0);self.assertLessEqual(len(r['stdout']),1048576)

if __name__=='__main__':unittest.main()

class RecoveryTests(unittest.TestCase):
    def test_checkpoint_resume_and_tie(self):
        from unittest.mock import patch
        from rqgm_lab.controller import Lab
        lab=Lab.__new__(Lab);lab.archive=None
        lab.s={'checkpoint_candidate_ready':True,'slots':{'challenger':'old'},'trees':{'challenger':{'old':{},'new':{}}},'records':[],'epoch':1,'checkpoint':8,'step':2}
        events=[];lab.commit=lambda reason,**details:events.append(details)
        lab.expand=lambda kind:self.fail('checkpoint candidate must not be generated twice after resume')
        with patch('rqgm_lab.controller.anchor',return_value={'ok':16,'total':16,'outcomes':[True]*16}):lab.checkpoint()
        self.assertEqual(lab.s['slots']['challenger'],'old')
        self.assertEqual(lab.s['checkpoint'],16)
        self.assertNotIn('checkpoint_candidate_ready',lab.s)
        self.assertEqual(events[0]['invalidated'],[])
    def test_invalid_candidate_rolls_back_after_restart(self):
        from unittest.mock import patch
        from rqgm_lab.controller import Lab
        with tempfile.TemporaryDirectory() as d:
            lab=Lab(d);before=json.dumps(lab.s,sort_keys=True)
            with patch('rqgm_lab.controller.proposal',return_value=({'files':{},'strategy':'broken'},{})):
                with self.assertRaises(ValueError):lab.expand('seed')
            lab.lock.close()
            resumed=Lab(d)
            self.assertEqual(json.dumps(resumed.s,sort_keys=True),before)
            resumed.lock.close()

class DeterminismTests(unittest.TestCase):
    def test_resume_order_does_not_change_sampling(self):
        from rqgm_lab.search import sample,best
        tree={'z':{'parent':None},'a':{'parent':'z'}}
        restored=json.loads(json.dumps(tree,sort_keys=True))
        self.assertEqual(sample(tree,[],random.Random(9)),sample(restored,[],random.Random(9)))
        self.assertEqual(best(tree,[]),best(restored,[]))
