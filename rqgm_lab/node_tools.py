"""Operator tools for immutable node inspection and controller-owned regression.

These commands are deliberately separate from the evolution loop.  In particular,
``evaluate`` passes no MBPP+ reference, test program, expected result, or prior
score into an editable Seed node.
"""
import argparse,json,os,tempfile,time
from pathlib import Path

from . import artifacts
from .doctor import check
from .engine import Engine
from .regression_live import regression
from .store import Archive,Journal

def latest_state(root):
    events=Journal(Path(root)/'events.jsonl').events
    states=[x['state'] for x in events if x.get('type')=='state']
    if not states:raise RuntimeError('experiment has no saved state')
    return states[-1]

def known_nodes(state,role):
    if role not in ('seed','challenger'):raise ValueError('role must be seed or challenger')
    return set(state['trees'][role])

def resolve(root,role,node):
    state=latest_state(root);nodes=known_nodes(state,role)
    matches=[x for x in nodes if x.startswith(node)]
    if len(matches)!=1:raise ValueError('node must uniquely identify an archived '+role+' commit')
    return matches[0]

def list_nodes(root,role=None):
    state=latest_state(root);roles=(role,) if role else ('seed','challenger')
    result=[]
    for current in roles:
        for commit,info in sorted(state['trees'][current].items()):
            result.append({'role':current,'commit':commit,'parent':info['parent'],
                           'strategy':info['strategy'],'incumbent':state['slots'].get(current)==commit})
    return result

def export_node(root,role,node,destination):
    commit=resolve(root,role,node);dest=Path(destination).resolve()
    if dest.exists():raise ValueError('destination must not already exist')
    if not dest.parent.is_dir():raise ValueError('destination parent does not exist')
    dest.mkdir(mode=0o700)
    try:
        artifacts.write(dest,Archive(Path(root)/'objects.git').files(commit))
    except Exception:
        dest.rmdir();raise
    return {'role':role,'commit':commit,'destination':str(dest)}

def parse_tasks(value):
    if not value:return None
    result=[]
    for item in value.split(','):
        item=item.strip()
        if not item:continue
        result.append(item if item.startswith('Mbpp/') else 'Mbpp/'+item)
    if not result:raise ValueError('provide one or more comma-separated task numbers')
    return result

def evaluate_node(root,node,tasks=None,model='glm-5.3-flash',max_calls=24,max_tokens=180000):
    """Run a Seed node through disposable real Pi executors under controller control."""
    commit=resolve(root,'seed',node);files=Archive(Path(root)/'objects.git').files(commit)
    if not {'executor.py','meta.py'}<=set(files):raise ValueError('selected commit is not a complete Seed node')
    root=Path(root).resolve();manual=root/'manual-evaluations';manual.mkdir(mode=0o700,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rqgm-node-',dir=manual) as directory:
        engine=Engine(directory,model,max_calls,max_tokens)
        result=regression(engine,files,'manual-node-regression',task_ids=tasks)
        record={'time':time.time(),'node':commit,'requested_tasks':tasks,
                'passed':result['ok'],'total':result['total'],'usage':engine.meter.totals(),
                'details':result['details'],'dataset_sha256':result['dataset_sha256']}
        # This remains under the trusted experiment directory, never in the node workspace.
        path=manual/(str(time.time_ns())+'.json');path.write_text(json.dumps(record,ensure_ascii=False));path.chmod(0o600)
    return {'role':'seed','commit':commit,'passed':result['ok'],'total':result['total'],
            'usage':record['usage'],'record':str(path)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['list','export','evaluate'])
    parser.add_argument('--root',required=True)
    parser.add_argument('--role',choices=['seed','challenger'])
    parser.add_argument('--node')
    parser.add_argument('--destination')
    parser.add_argument('--tasks',help='operator-only MBPP+ task numbers, for example 3,4')
    parser.add_argument('--model',default='glm-5.3-flash')
    parser.add_argument('--max-api-calls',type=int,default=24)
    parser.add_argument('--max-reserved-tokens',type=int,default=180000)
    args=parser.parse_args()
    if args.command=='list':
        print(json.dumps(list_nodes(args.root,args.role),ensure_ascii=False,indent=2));return
    if not args.role or not args.node:parser.error('--role and --node are required')
    if args.command=='export':
        if not args.destination:parser.error('--destination is required')
        print(json.dumps(export_node(args.root,args.role,args.node,args.destination),ensure_ascii=False));return
    if args.role!='seed':parser.error('evaluate supports Seed nodes only')
    if args.max_api_calls<1 or args.max_reserved_tokens<1:parser.error('invalid API bounds')
    check()
    print(json.dumps(evaluate_node(args.root,args.node,parse_tasks(args.tasks),args.model,
                                   args.max_api_calls,args.max_reserved_tokens),ensure_ascii=False))

if __name__=='__main__':main()
