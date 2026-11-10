import json,tempfile
from pathlib import Path
from .sandbox import ROOT,run

def pi(request,response=None):
    if response is None:
        from .live import invoke
        return invoke("pi",request)
    with tempfile.TemporaryDirectory(prefix='rqgm-pi-') as cwd:
        r=run(['/usr/bin/node',str(ROOT/'runtime/pi-bridge.mjs')],cwd,
              json.dumps(dict(request,mode='mock',mock_response=response)),
              read=[ROOT/'runtime'],memory_mb=0,timeout=30)
        if r['code']:raise RuntimeError('Pi failed: '+r['stderr'][-2000:])
        result=json.loads(r['stdout']);result['resources']={'peak_rss_kb':r['peak_rss_kb']}
        return result

def editable(archive,commit,script,payload):
    with tempfile.TemporaryDirectory(prefix='rqgm-task-') as cwd:
        archive.materialize(commit,cwd)
        r=run(['/usr/bin/python3','-I',str(Path(cwd)/script)],cwd,json.dumps(payload))
        if r['code']:raise RuntimeError('editable program failed: '+r['stderr'][-1000:])
        return json.loads(r['stdout'])

def proposal(archive,commit,kind,training):
    files=archive.files(commit)
    if kind=='seed':
        request=editable(archive,commit,'meta.py',{'files':files,'training':training,'goals':['independent concurrent task execution','unified identity, memory, goals and principles']})
        files['meta.py']+='\n# Mock mutation: ask for a reproducible counterexample before revising.\n'
        files['executor.py']+='\n# Mock mutation: validate the output against the request.\n'
        result=pi(request,json.dumps({'files':files,'strategy':'mock: validation reminder; no capability claim'}))
    else:
        files['.claude/skills/challenge/SKILL.md']+='\nCalibrate verdicts using both positive and negative controls.\n'
        files['generate.py']=files['generate.py'].replace('randrange(1,1000)','randrange(1,2000)')
        files['judge.py']="import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({'ok':x['observed']==x['expected']}))\n"
        result=claude({'files':files,'training':training},json.dumps({'files':files,'strategy':'mock: replace unconditional acceptance with equality oracle'}))
    return json.loads(result['text']),result

# Claude Code uses its real CLI against a local synthetic Anthropic endpoint.
def claude(request,response=None):
    if response is None:
        from .live import invoke
        return invoke("claude",request)
    import http.server,threading,os
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length',0)))
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            message={'id':'msg_mock','type':'message','role':'assistant','model':'claude-mock','content':[], 'stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':0,'output_tokens':0}}
            events=[('message_start',{'type':'message_start','message':message}),('content_block_start',{'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}}),('content_block_delta',{'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':response}}),('content_block_stop',{'type':'content_block_stop','index':0}),('message_delta',{'type':'message_delta','delta':{'stop_reason':'end_turn','stop_sequence':None},'usage':{'output_tokens':0}}),('message_stop',{'type':'message_stop'})]
            for event,data in events:self.wfile.write(('event: '+event+'\ndata: '+json.dumps(data)+'\n\n').encode())
    server=http.server.HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='rqgm-claude-') as cwd:
            r=run(['/usr/bin/claude','--bare','-p','--model','claude-mock','--output-format','json','--tools','','--no-session-persistence','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}'],cwd,json.dumps(request),timeout=40,memory_mb=0,port=server.server_port,
                  extra_env={'ANTHROPIC_BASE_URL':f'http://127.0.0.1:{server.server_port}','ANTHROPIC_API_KEY':'mock-not-secret','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','DISABLE_AUTOUPDATER':'1'})
            if r['code']:raise RuntimeError('Claude failed: '+r['stderr'][-1500:]+' '+r['stdout'][-1500:])
            result=json.loads(r['stdout'])
            if result.get('is_error'):raise RuntimeError('Claude error: '+str(result))
            return {'text':result['result'],'usage':{'input':0,'output':0,'simulated':True},'runtime':'claude-code-2.1.81','trace':result}
    finally:server.shutdown();server.server_close();thread.join()
