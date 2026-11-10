import tempfile,unittest
from unittest.mock import patch
from rqgm_lab.engine import Engine,BudgetExceeded,TransportError
from rqgm_lab.live import EmptyModelResponse

class EmptyResponseTests(unittest.TestCase):
    def exercise(self,root,mode,max_calls=4):
        engine=Engine(root,max_calls=max_calls)
        def invoke(*args,charge,**kwargs):
            charge({'max_tokens':100})
            if mode=='empty' or engine.meter.totals()['requests']==1:
                raise EmptyModelResponse({'runtime':'pi','usage':{'input':10,'output':20},'stop_reason':'length'})
            return {'text':'answer','usage':{'input':10,'output':2}}
        with patch('rqgm_lab.live.invoke',side_effect=invoke),patch('rqgm_lab.engine.time.sleep'):
            return engine.model_call('pi',{'prompt':'task'},'operation')

    def test_retry_usage_cache_and_restart_limit(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.exercise(root,'recover')['text'],'answer')
            engine=Engine(root)
            self.assertEqual(engine.meter.totals()['requests'],2)
            self.assertEqual(engine.meter.totals()['reported_output_tokens'],22)
            with patch('rqgm_lab.live.invoke',side_effect=AssertionError('must use cache')):
                self.assertEqual(engine.model_call('pi',{'prompt':'task'},'operation')['text'],'answer')
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TransportError):self.exercise(root,'empty')
            with self.assertRaises(TransportError):self.exercise(root,'empty')
            self.assertEqual(Engine(root).meter.totals()['requests'],2)

    def test_retry_respects_total_budget(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(BudgetExceeded):self.exercise(root,'recover',max_calls=1)
            self.assertEqual(Engine(root).meter.totals()['requests'],1)
