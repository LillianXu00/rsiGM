import http.client,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from rqgm_lab.bigmodel import Broker,ENDPOINTS,NoRedirect
from rqgm_lab.sandbox import run

class FakeResponse:
    status=200
    headers={'Content-Type':'application/json'}
    def __enter__(self):self.sent=False;return self
    def __exit__(self,*args):pass
    def read1(self,n):
        if self.sent:return b''
        self.sent=True;return b'{"ok":true}'

class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'apikey.bin').write_text('test-private-credential')
        self.patch=patch('rqgm_lab.bigmodel.ROOT',self.root);self.patch.start()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def post(self,b,path,body,token=None):
        conn=http.client.HTTPConnection('127.0.0.1',b.port,timeout=3)
        conn.request('POST',path,json.dumps(body),{'Authorization':'Bearer '+(token or b.token),'Content-Type':'application/json'})
        response=conn.getresponse();result=(response.status,response.read());conn.close();return result
    def test_auth_route_budget_and_pinned_upstream(self):
        with patch('rqgm_lab.bigmodel.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=FakeResponse()
            with Broker('pi',max_tokens=64,max_requests=1) as b:
                self.assertEqual(self.post(b,'/v1/chat/completions',{},'wrong')[0],401)
                self.assertEqual(self.post(b,'/anywhere',{})[0],404)
                self.assertEqual(self.post(b,'/v1/chat/completions',{'model':'other','max_tokens':9999})[0],200)
                req=opener.return_value.open.call_args.args[0]
                self.assertEqual(req.full_url,ENDPOINTS['pi'][0])
                self.assertEqual(req.headers['Authorization'],'Bearer test-private-credential')
                self.assertEqual(json.loads(req.data)['max_tokens'],64)
                self.assertEqual(json.loads(req.data)['model'],b.model)
                self.assertEqual(self.post(b,'/v1/chat/completions',{})[0],429)
                self.assertEqual(b.calls,1)
    def test_errors_redact_credentials(self):
        import io
        failure=urllib.error.HTTPError('https://open.bigmodel.cn',401,'bad',{},io.BytesIO(b'test-private-credential'))
        with patch('rqgm_lab.bigmodel.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=failure
            with Broker('claude') as b:
                status,body=self.post(b,'/v1/messages',{})
                self.assertEqual(status,401);self.assertNotIn(b'test-private-credential',body)
    def test_no_redirects(self):self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))
    def test_candidate_cannot_read_key(self):
        with tempfile.TemporaryDirectory() as cwd:
            p=Path(cwd)/'probe.py';p.write_text(f"open({str(self.root/'apikey.bin')!r}).read()")
            result=run(['/usr/bin/python3','-I',str(p)],cwd)
            self.assertNotEqual(result['code'],0)
            self.assertIn('PermissionError',result['stderr'])
            self.assertNotIn('test-private-credential',result['stderr'])
