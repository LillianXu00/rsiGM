import json,tempfile,unittest
from pathlib import Path
from rqgm_lab.report import node_results,render,final_winner,evolution_tree

class ReportTests(unittest.TestCase):
    def test_tree_shows_branches_winner_and_only_current_evidence(self):
        base={'kind':'seed','regressions':{},'challenges':[],'training':[],'status':'accepted'}
        nodes=[dict(base,node='root',parent=None),dict(base,node='child1',parent='root'),
               dict(base,node='child2',parent='root',status='rejected')]
        nodes[1]['regressions']={'auto':{'source':'automatic','passed':8,'total':12,'complete':True,'tasks':{}}}
        nodes[1]['challenges']=[{'result':'pass','evidence':'active'},
                                {'result':'fail','evidence':'invalidated'},
                                {'result':'invalid test','evidence':'excluded'}]
        tree=evolution_tree(nodes,'child1')
        self.assertEqual(tree.count('<path '),2)
        self.assertIn('#16803c',tree)
        self.assertIn('MBPP+: 8/12',tree)
        self.assertIn('Challenger: 1/1',tree)
        self.assertIn('另 2 条失效/无效',tree)
        self.assertIn('已拒绝',tree)
        self.assertEqual(final_winner([{'type':'state'},{'type':'result','winner':'child1'}]),'child1')
        self.assertIsNone(final_winner([{'type':'result','winner':'child1'},{'type':'state'}]))

    def test_per_node_hidden_regression_and_versioned_challenges(self):
        state={'trees':{'seed':{'seed':{'parent':None,'strategy':'root'}},
                        'challenger':{'new':{'parent':None,'strategy':'root'}}},
               'slots':{'challenger':'new'},'rejected':[{'commit':'rejected','kind':'seed','parent':'seed'}],
               'records':[], 'epoch':1,'n':3,'config':{},'pending':None,'suites':{}}
        for i,(node,version,usable,ok) in enumerate([
            ('seed','old',True,True),('seed','new',True,False),('seed','new',False,False)]):
            state['records'].append({'id':i,'node':node,'deps':{'challenger':version},
                'task':'task-<x>','role':'distributed','epoch':i,'test_version':str(i),
                'usable':usable,'ok':ok,'trace':{}})
        events=[{'type':'private_regression_task','node':'rejected','operation':'candidate',
                 'row':{'task':'Mbpp/3','ok':False,'cases':100}},
                {'type':'state','reason':'baseline','state':state,
                 'details':{'private_result':{'ok':1,'total':1,'details':[{'task':'Mbpp/4','ok':True,'cases':99}]}}}]
        with tempfile.TemporaryDirectory() as d:
            manual=Path(d,'manual-evaluations');manual.mkdir()
            (manual/'one.json').write_text(json.dumps({'node':'seed','passed':0,'total':1,
                'details':[{'task':'Mbpp/4','ok':False,'cases':99}]}))
            results={n['node']:n for n in node_results(d,state,events)}
            self.assertEqual(len(results['seed']['regressions']),2)
            self.assertEqual(results['seed']['regressions']['manual/one.json']['source'],'manual')
            self.assertFalse(results['rejected']['regressions']['candidate']['complete'])
            self.assertEqual([r['evidence'] for r in results['seed']['challenges']],['invalidated','active','excluded'])
            self.assertEqual(results['seed']['challenges'][2]['result'],'invalid test')
            render(d,state,events,{})
            report=Path(d,'report.html').read_text()
            for text in ['Mbpp/3','Mbpp/4','partial / 未完成','not applicable','task-&lt;x&gt;','invalidated']:
                self.assertIn(text,report)
            self.assertEqual(len(state['records']),3)
