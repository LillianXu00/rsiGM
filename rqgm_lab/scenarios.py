"""Executable challenger-generated scenarios and controller-owned evidence semantics."""
import json,tempfile
from . import artifacts
from .engine import CandidateError
from .protocol import CONTRACT,CASE_CONTRACT,GOALS
from .sandbox import run
from .store import canonical

JUDGE_CONTRACT='''judge.py reads {checks:[{id:unique_nonempty_string,ok:exact_boolean},...], execution_error:exact_boolean} and prints {ok:exact_boolean}. Accept only a nonempty list with unique nonempty IDs, exact boolean results all True and execution_error exactly False. Missing fields, malformed fields, duplicated IDs or execution failures are not success. This evidence protocol is fixed; the implementation and testing method may evolve.'''

def oracle(source,observation):
    if not isinstance(source,str) or len(source.encode())>8192:raise CandidateError('oracle size limit')
    compile(source,'oracle.py','exec')
    with tempfile.TemporaryDirectory(prefix='rqgm-oracle-') as cwd:
        from pathlib import Path
        Path(cwd,'oracle.py').write_text(source)
        wrapper="import json,sys,runpy\nf=runpy.run_path('oracle.py')['check']\ny=f(json.load(sys.stdin))\nassert type(y) is bool\nprint(json.dumps(y))"
        r=run(['/usr/bin/python3','-I','-c',wrapper],cwd,canonical(observation),timeout=8)
        if r['code']:raise CandidateError('oracle execution failure: '+r['stderr'][-1000:])
        try:value=json.loads(r['stdout'])
        except ValueError:raise CandidateError('invalid oracle output') from None
        if type(value) is not bool:raise CandidateError('oracle must return bool')
        return value

def validate_suite(value):
    cases=value.get('cases') if isinstance(value,dict) else None
    if not isinstance(cases,list) or len(cases)!=2 or not all(isinstance(c,dict) for c in cases):raise CandidateError('suite must contain two cases')
    if {c.get('goal') for c in cases}!={'distributed','individuality'}:raise CandidateError('both goals required')
    ids=[]
    for c in cases:
        if not isinstance(c.get('id'),str) or not 1<=len(c['id'])<=80:raise CandidateError('case id')
        ids.append(c['id']);artifacts.validate(c.get('files',{}),32768)
        if not isinstance(c.get('rationale'),str) or not c['rationale']:raise CandidateError('rationale required')
        turns=c.get('turns')
        if not isinstance(turns,list) or not 1<=len(turns)<=3 or not all(isinstance(t,str) and 0<len(t)<8000 for t in turns):raise CandidateError('turn budget')
        negatives=c.get('negatives')
        if not isinstance(c.get('positive'),dict) or not isinstance(negatives,list) or not 1<=len(negatives)<=3:raise CandidateError('controls required')
        for observation,expected in [(c['positive'],True)]+[(n,False) for n in negatives]:
            if not isinstance(observation,dict):raise CandidateError('control format')
            for repeat in range(2):
                if oracle(c['oracle'],observation)!=expected:raise CandidateError('oracle failed reference or negative control')
    if len(ids)!=len(set(ids)):raise CandidateError('duplicate case IDs')
    if len(canonical(value).encode())>65536:raise CandidateError('suite size budget')
    return value

def generate(engine,files,seed_files,training,operation):
    payload={'goals':GOALS,'primitive_contract':CONTRACT,'case_contract':CASE_CONTRACT,
             'current_agent':seed_files,'training':training,'nonce':operation}
    result=engine.harness(files,'generate.py',payload,'claude',operation,max_tokens=4096,max_model_calls=2)
    return validate_suite(result['result']),result

def judge(files,evidence):
    with tempfile.TemporaryDirectory(prefix='rqgm-judge-') as cwd:
        artifacts.write(cwd,files)
        r=run(['/usr/bin/python3','-I','-c',files['judge.py']],cwd,canonical(evidence),timeout=8)
        if r['code']:raise CandidateError('judge failed')
        try:value=json.loads(r['stdout'])
        except ValueError:raise CandidateError('invalid judge JSON') from None
        if not isinstance(value,dict) or type(value.get('ok')) is not bool:raise CandidateError('invalid judge verdict')
        return value['ok']

def observe(engine,files,case,operation):
    if set(files)&set(case.get('files',{})):raise CandidateError('case overwrites agent files')
    workspace=case.get('files',{});answers=[];events=[];error=None
    for i,task in enumerate(case['turns']):
        try:
            result=engine.harness(files,'executor.py',{'task':task,'primitive_contract':CONTRACT},'pi',operation+f'/turn-{i}',workspace=workspace)
            answers.append(result['result']);workspace=result['workspace'];events+=result['events']
        except CandidateError as e:error=str(e);break
    return {'answers':answers,'files':workspace,'events':events},error

def evaluate(engine,files,challenger,case,operation):
    observation,error=observe(engine,files,case,operation)
    try:
        first=oracle(case['oracle'],observation);second=oracle(case['oracle'],observation)
        if first!=second:raise CandidateError('non-reproducible oracle')
    except CandidateError as e:
        return {'ok':False,'usable':False,'observation':observation,'evidence':None,'error':str(e),'judge_verdict':None}
    evidence={'checks':[{'id':case['id'],'ok':first}], 'execution_error':error is not None}
    verdict=judge(challenger,evidence)
    # Invalid/colluding verdicts never become success; stationary evidence protocol.
    return {'usable':True,'ok':verdict and first and error is None,'observation':observation,'evidence':evidence,'error':error,'judge_verdict':verdict}
