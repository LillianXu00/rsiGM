import json,sys
x=json.load(sys.stdin)
if x['observation'] is None:
    print(json.dumps({'action':'model','system':'You are a coding agent. Solve the task accurately. Return requested code or answer without markdown fences. Return the task answer itself, not a Harness action envelope.','prompt':json.dumps({k:v for k,v in x['input'].items() if k!='primitive_contract'},ensure_ascii=False),'state':{}}))
else:
    print(json.dumps({'action':'finish','result':x['observation']['text']}))
