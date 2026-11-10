"""Short-lived, bounded credential broker for Pi/Claude. No payload/key logging."""
import http.server
import json
import secrets
import time
import threading
import urllib.request
import urllib.error
from .sandbox import ROOT

MODEL='glm-5.3-flash'
ENDPOINTS={'pi':('https://open.bigmodel.cn/api/coding/paas/v4/chat/completions','/v1/chat/completions'),
           'claude':('https://open.bigmodel.cn/api/anthropic/v1/messages','/v1/messages')}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class Broker:
    def __init__(self,tool,model=MODEL,max_tokens=512,max_requests=2, charge=None):
        if tool not in ENDPOINTS:raise ValueError('unsupported runtime')
        if not 1<=max_tokens<=4096 or not 1<=max_requests<=4:raise ValueError('budget outside bounds')
        if model not in ('glm-5.3-flash','glm-5.3','glm-4.7','glm-4.5-air'):raise ValueError('model not allowed')
        self.tool=tool;self.model=model;self.max_tokens=max_tokens;self.max_requests=max_requests;self.charge=charge
        self.token=secrets.token_urlsafe(32);self.calls=0;self.statuses=[]
        self._key=(ROOT/'apikey.bin').read_text(encoding='utf-8-sig').strip()
        if not self._key or any(c.isspace() for c in self._key):raise ValueError('apikey.bin must contain one plaintext API key')
    def redact(self,text):return text.replace(self._key,'[REDACTED]').replace(self.token,'[SESSION_TOKEN]')
    def __enter__(self):
        broker=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def error(self,status,message):
                data=json.dumps({'type':'error','error':{'type':'api_error','message':message}}).encode()
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_POST(self):
                upstream,path=ENDPOINTS[broker.tool]
                auth=self.headers.get('Authorization','').removeprefix('Bearer ') or self.headers.get('x-api-key','')
                if not secrets.compare_digest(auth,broker.token):return self.error(401,'invalid session token')
                if self.path.split('?')[0]!=path:return self.error(404,'route not allowed')
                if broker.calls>=broker.max_requests:return self.error(429,'local request budget exhausted')
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=262144:return self.error(413,'request too large')
                    body=json.loads(self.rfile.read(size));body['model']=broker.model
                    body['max_tokens']=max(1,min(int(body.get('max_tokens',broker.max_tokens)),broker.max_tokens))
                    body.pop('max_completion_tokens',None)
                    body['thinking']={'type':'disabled'}
                    if broker.tool=='claude':body.pop('output_config',None)
                    if broker.charge:broker.charge(body)
                    broker.calls+=1
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+broker._key}
                    for key in ('User-Agent','anthropic-version','anthropic-beta','x-app'):
                        if self.headers.get(key):headers[key]=self.headers[key]
                    req=urllib.request.Request(upstream,json.dumps(body).encode(),headers,method='POST')
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
                    with opener.open(req,timeout=90) as response:
                        broker.statuses.append(response.status)
                        self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','text/event-stream'));self.end_headers()
                        total=0;deadline=time.monotonic()+90
                        while True:
                            chunk=response.read1(16384)
                            if not chunk:break
                            total+=len(chunk)
                            if total>1048576 or time.monotonic()>deadline:raise TimeoutError('response budget')
                            self.wfile.write(chunk);self.wfile.flush()
                except urllib.error.HTTPError as e:
                    broker.statuses.append(e.code)
                    # Error response only: strip credential and cap diagnostic size.
                    detail=broker.redact(e.read(2048).decode(errors='replace'))
                    self.error(e.code,'BigModel HTTP '+str(e.code)+': '+detail)
                except (BrokenPipeError,ConnectionResetError):pass
                except Exception as e:
                    self.error(502,'broker transport failure: '+type(e).__name__)
        self.server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        self.server.timeout=90
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_port;self.base_url=f'http://127.0.0.1:{self.port}'
        return self
    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join();self._key=''
