"""Controller-only regression and evaluator anchor. Never include in agent context."""
import gzip,hashlib,json,tempfile
from pathlib import Path
from .sandbox import ROOT,run
from .providers import editable,pi

IDS=[3,4,6,7,8,17,18,19,58,59,62,65]

def prepare():
    source=ROOT/'private/MbppPlus.jsonl.gz'
    rows=[json.loads(x) for x in gzip.open(source,'rt')]
    rows=[r for r in rows if int(r['task_id'].split('/')[1]) in IDS]
    if len(rows)!=12:raise RuntimeError('incomplete MBPP+ release')
    bundle={'source':'https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz',
            'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'tasks':rows}
    dest=ROOT/'private/regression.json';dest.write_text(json.dumps(bundle));dest.chmod(0o600)
    return bundle

def execute(code,entry,inputs):
    # Only the implementation sees its individual arguments, never the oracle/reference.
    with tempfile.TemporaryDirectory(prefix='rqgm-exec-') as cwd:
        p=Path(cwd);(p/'solution.py').write_text(code)
        (p/'call.py').write_text("import json,sys,runpy\nn=runpy.run_path('solution.py')\nx=json.load(sys.stdin)\nprint(json.dumps([n[x['entry']](*a) for a in x['inputs']]))\n")
        r=run(['/usr/bin/python3','-I',str(p/'call.py')],cwd,json.dumps({'entry':entry,'inputs':inputs}),timeout=8)
        if r['code']:return None,r
        try:return json.loads(r['stdout']),r
        except ValueError:return None,r

def regression(archive,commit,calibrate=False):
    bundle=json.loads((ROOT/'private/regression.json').read_text());out=[]
    for task in bundle['tasks']:
        inputs=task['base_input']+task['plus_input']
        expected,_=execute(task['canonical_solution'],task['entry_point'],inputs)
        if expected is None:raise RuntimeError('reference failed: '+task['task_id'])
        if calibrate:code=task['canonical_solution']
        else:
            # Strip embedded sample assertions from the task statement. Never send IDs,
            # dataset name, contract, hidden tests, reference, or selection feedback.
            prompt=task['prompt'].split('assert ')[0].strip('"\n ')
            req=editable(archive,commit,'executor.py',{'task':prompt,'entry_point':task['entry_point']})
            code=pi(req,f"def {task['entry_point']}(*args):\n    return None\n")['text']
        observed,trace=execute(code,task['entry_point'],inputs)
        ok=observed==expected
        out.append({'task':task['task_id'],'ok':ok,'cases':len(inputs),'trace':trace})
    return {'ok':sum(r['ok'] for r in out),'total':len(out),'details':out,'dataset_sha256':bundle['sha256']}

def anchor(archive,commit):
    # Fixed hidden labelled verdict cases, independent of challenger training tasks.
    # This MOCK anchor validates equality-oracle calibration only, not Personal Agent competence.
    cases=[{'observed':i,'expected':i if i%2==0 else i+100} for i in range(16)]
    outcomes=[]
    for case in cases:
        try:answer=editable(archive,commit,'judge.py',case);ok=(answer.get('ok') is (case['observed']==case['expected']))
        except Exception:ok=False
        outcomes.append(ok)
    return {'ok':sum(outcomes),'total':len(outcomes),'outcomes':outcomes}
