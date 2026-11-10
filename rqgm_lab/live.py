"""Explicit live runtime integration; mock evolution never silently spends tokens."""
import argparse,json,tempfile,fcntl
from contextlib import nullcontext
from .sandbox import ROOT,run
from .bigmodel import Broker,MODEL

class EmptyModelResponse(RuntimeError):
    def __init__(self,diagnostic):
        self.diagnostic=diagnostic
        super().__init__('empty model response: '+json.dumps(diagnostic,ensure_ascii=False))

def invoke(tool,request,model=MODEL,max_tokens=512, *, managed=False, charge=None):
    (ROOT/'runs').mkdir(exist_ok=True)
    with (nullcontext(None) if managed else (ROOT/'runs/.execution.lock').open('a')) as lock:
        if lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with Broker(tool,model,max_tokens,max_requests=1,charge=charge) as broker, tempfile.TemporaryDirectory(prefix='rqgm-live-') as cwd:
            if tool=='pi':
                command=['/usr/bin/node',str(ROOT/'runtime/pi-bridge.mjs')]
                payload=json.dumps({**request,'mode':'bigmodel','model':model,'max_tokens':max_tokens,'base_url':broker.base_url,'token':broker.token})
                env={};read=[ROOT/'runtime']
            else:
                command=['/usr/bin/claude','--bare','-p','--model',model,'--effort','low','--output-format','json','--tools','','--no-session-persistence','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}']
                payload=request.get('prompt') or json.dumps(request)
                if request.get('system'):command+=['--system-prompt',request['system']]
                env={'ANTHROPIC_BASE_URL':broker.base_url,'ANTHROPIC_API_KEY':broker.token,'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','DISABLE_AUTOUPDATER':'1','API_TIMEOUT_MS':'90000','CLAUDE_CODE_MAX_OUTPUT_TOKENS':str(max_tokens)};read=[]
            r=run(command,cwd,payload,read=read,timeout=120,memory_mb=0,port=broker.port,extra_env=env)
            if r['code'] or r['timeout']:raise RuntimeError(broker.redact('runtime failed: '+r['stderr'][-2000:]+' '+r['stdout'][-2000:]))
            data=json.loads(r['stdout'])
            if data.get('is_error'):raise RuntimeError(broker.redact(str(data.get('result','provider failed'))))
            text=data.get('text',data.get('result',''))
            usage=data.get('usage',{});usage.pop('cost',None)
            if not isinstance(text,str) or not text.strip():
                raise EmptyModelResponse({'runtime':tool,'model':model,'usage':usage,
                    'http_statuses':broker.statuses,'stop_reason':data.get('stop_reason'),
                    'content_types':data.get('content_types',[]),'requests':broker.calls})
            return {'text':broker.redact(text),'usage':usage,'cost_usd':None,'model':model,'runtime':tool,
                    'requests':broker.calls,'http_statuses':broker.statuses,'peak_rss_kb':r['peak_rss_kb'],'simulated':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--tool',choices=['pi','claude','both'],default='both');p.add_argument('--model',default=MODEL);p.add_argument('--max-tokens',type=int,default=512);p.add_argument('--prompt',default='Write a Python function add(a, b) that returns their sum. Return only the code, no explanation.');a=p.parse_args()
    for tool in (['pi','claude'] if a.tool=='both' else [a.tool]):
        try:print(json.dumps(invoke(tool,{'prompt':a.prompt},a.model,a.max_tokens),ensure_ascii=False),flush=True)
        except Exception as e:print(json.dumps({'runtime':tool,'error':str(e)},ensure_ascii=False),flush=True);raise SystemExit(1)
if __name__=='__main__':main()
