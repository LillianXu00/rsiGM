import json,sys
x=json.load(sys.stdin);state=x.get('state') or {};obs=x.get('observation')
SYSTEM='Design executable tests using the supplied contracts. Return only Python source defining build_suite(), no markdown. Do not print anything.'
if obs is None:
    SYSTEM=open('.claude/skills/challenge/SKILL.md').read()+'\n'+SYSTEM
    print(json.dumps({'action':'model','system':SYSTEM,'prompt':json.dumps(x['input'],ensure_ascii=False),'state':{'stage':'model','attempt':0}}))
elif state['stage']=='model':
    code=obs['text'].strip()
    if code.startswith('```'):code=code.split('\n',1)[1].rsplit('```',1)[0]
    program=code+'\nimport json\nprint(json.dumps(build_suite()))\n'
    print(json.dumps({'action':'python','code':program,'state':{'stage':'execute','attempt':state['attempt'],'source':code}}))
else:
    try:
        if obs['code']!=0:raise ValueError(obs['stderr'][-1800:])
        result=json.loads(obs['stdout'])
        print(json.dumps({'action':'finish','result':result}))
    except (ValueError,KeyError) as e:
        if state['attempt']>=1:raise
        print(json.dumps({'action':'model','system':SYSTEM,'prompt':json.dumps({'request':x['input'],'previous_source':state['source'],'error':str(e)}),'state':{'stage':'model','attempt':1}}))
