import json,sys
x=json.load(sys.stdin);state=x.get('state') or {};obs=x.get('observation')
SYSTEM='Improve the complete coding agent, including its modification method and executor, based on public training failures. Preserve the primitive entry protocol. Return only Python source defining build_patch() -> {files:{path:full_text}, strategy:description}; return the complete workspace. Use triple-quoted strings for file contents. No markdown. Choose the architecture yourself. Do not print anything.'
if obs is None:
    pass
    print(json.dumps({'action':'model','system':SYSTEM,'prompt':json.dumps(x['input'],ensure_ascii=False),'state':{'stage':'model','attempt':0}}))
elif state['stage']=='model':
    code=obs['text'].strip()
    if code.startswith('```'):code=code.split('\n',1)[1].rsplit('```',1)[0]
    program=code+'\nimport json\nprint(json.dumps(build_patch()))\n'
    print(json.dumps({'action':'python','code':program,'state':{'stage':'execute','attempt':state['attempt'],'source':code}}))
else:
    try:
        if obs['code']!=0:raise ValueError(obs['stderr'][-1800:])
        result=json.loads(obs['stdout'])
        print(json.dumps({'action':'finish','result':result}))
    except (ValueError,KeyError) as e:
        if state['attempt']>=1:raise
        print(json.dumps({'action':'model','system':SYSTEM,'prompt':json.dumps({'request':x['input'],'previous_source':state['source'],'error':str(e)}),'state':{'stage':'model','attempt':1}}))
