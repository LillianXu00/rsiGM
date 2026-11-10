"""Independent disposable executor instances. Only controller receives labels/traces."""
import json
from .sandbox import ROOT
from .engine import CandidateError
from .protocol import code_text,CONTRACT
from .validation import execute

def regression(engine,files,operation,save=None,completed=None,task_ids=None):
    """Evaluate selected controller-owned tasks without exposing answers to the node.

    ``task_ids`` is an operator-side filter.  The selected task's natural-language
    prompt is still the only task content sent into the Pi harness; references,
    inputs, expected results and aggregate history remain outside it.
    """
    bundle=json.loads((ROOT/'private/regression.json').read_text());rows=list(completed or [])
    tasks=list(bundle['tasks'])
    if task_ids is not None:
        wanted=set(task_ids);available={x['task_id'] for x in tasks}
        missing=wanted-available
        if missing:raise ValueError('unknown controller task id')
        tasks=[x for x in tasks if x['task_id'] in wanted]
    for task in tasks:
        if any(x['task']==task['task_id'] for x in rows):continue
        inputs=task['base_input']+task['plus_input']
        expected,_=execute(task['canonical_solution'],task['entry_point'],inputs)
        if expected is None:raise RuntimeError('reference calibration failed')
        request={'task':task['prompt'].split('assert ')[0].strip('"\n ')+'\nReturn only Python function source, no markdown.',
                 'entry_point':task['entry_point'],'primitive_contract':CONTRACT}
        try:
            result=engine.harness(files,'executor.py',request,'pi',operation+'/'+task['task_id'],max_tokens=1024)
            code=code_text(result['result']);observed,trace=execute(code,task['entry_point'],inputs)
            row={'task':task['task_id'],'ok':observed==expected,'cases':len(inputs),'trace':trace,'events':result['events']}
        except CandidateError as e:row={'task':task['task_id'],'ok':False,'error':str(e),'cases':len(inputs)}
        rows.append(row)
        if save:save(rows)
    return {'ok':sum(x['ok'] for x in rows),'total':len(rows),'details':rows,'dataset_sha256':bundle['sha256']}
