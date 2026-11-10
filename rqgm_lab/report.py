"""Standalone operator-only report: no server, dependencies or external resources."""
import html,json
from pathlib import Path
from .search import active,counts

def node_results(root,state,events):
    """Derive operator-only results from original evidence; never alter selection state."""
    nodes={}
    def ensure(node,kind='seed',**metadata):
        if node:
            nodes.setdefault(node,{'node':node,'kind':kind,'status':'archived',
                                  'regressions':{},'challenges':[],'training':[]}).update(metadata)
        return nodes.get(node)
    for kind,tree in state['trees'].items():
        for node,meta in tree.items():ensure(node,kind,status='accepted',**meta)
    for item in state.get('rejected',[]):
        ensure(item.get('commit'),item['kind'],status='rejected',parent=item.get('parent'))
    # A task event survives interruption before the aggregate result is saved.
    for event in events:
        if event.get('type')=='private_regression_task':
            entry=ensure(event['node'])
            run=entry['regressions'].setdefault(event['operation'],{'source':'automatic','complete':False,'tasks':{}})
            run['tasks'][event['row']['task']]=event['row']
        if event.get('type')!='state':continue
        details=event.get('details',{})
        if event.get('reason')=='training':
            pending=event['state'].get('pending') or {}
            node=details.get('node') or (pending.get('parent') if pending.get('kind')=='expand_seed' else None)
            if node:
                public=details['public'];result=public['result'];case=public['case']
                ensure(node)['training'].append({'transaction':details.get('transaction'),
                    'task':case['id'],'goal':case['goal'],'challenger':event['state']['slots']['challenger'],
                    'result':('pass' if result['ok'] else 'fail') if result.get('usable',True) else 'invalid test',
                    'error':result.get('error')})
        result=details.get('private_result')
        if result is None:continue
        snapshot=event['state'];node=details.get('candidate')
        if event.get('reason')=='baseline':
            node=next(n for n,m in snapshot['trees']['seed'].items() if m['parent'] is None)
        if not node:continue
        entry=ensure(node)
        matches=[r for r in entry['regressions'].values() if not r['complete']]
        run=matches[-1] if matches else entry['regressions'].setdefault('summary-'+str(event.get('time',len(entry['regressions']))),{})
        run.update(source='automatic',complete=True,passed=result['ok'],total=result['total'],
                   tasks={r['task']:r for r in result.get('details',[])})
    for path in sorted(Path(root,'manual-evaluations').glob('*.json')):
        record=json.loads(path.read_text());entry=ensure(record['node'])
        entry['regressions']['manual/'+path.name]={'source':'manual','complete':True,
            'passed':record['passed'],'total':record['total'],
            'tasks':{r['task']:r for r in record['details']}}
    valid_ids={r['id'] for r in active(state['records'],state['slots'])}
    for record in state['records']:
        usable=record.get('usable',True)
        ensure(record['node'])['challenges'].append({
            'record':record['id'],'task':record['task'],'goal':record.get('role'),
            'epoch':record.get('epoch'),'challenger':record['deps'].get('challenger'),
            'test_version':record.get('test_version'),
            'result':('pass' if record['ok'] else 'fail') if usable else 'invalid test',
            'evidence':'active' if record['id'] in valid_ids else ('invalidated' if usable else 'excluded'),
            'error':record.get('trace',{}).get('error')})
    return list(nodes.values())

def results_html(results):
    esc=lambda value:html.escape(str(value))
    def table(headers,rows):
        return '<table><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr>'+''.join(
            '<tr>'+''.join('<td>'+esc(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</table>'
    body='<h2>Per-node MBPP+ and Challenger results / 逐节点测评</h2>'
    body+='<p>MBPP+ is controller-only. Manual retests are separate observations. Missing evaluations are not failures. Challenger nodes generate/judge tasks; MBPP+ applies to Seed executors only.</p>'
    for node in results:
        body+='<h3 id="node-'+esc(node['node'])+'">'+esc(node['kind']+' '+node['node'])+'</h3><p>Status: '+esc(node['status'])+'</p>'
        if node['kind']!='seed':
            body+='<p>MBPP+: not applicable (Challenger node).</p>';continue
        if not node['regressions']:body+='<p>MBPP+: not evaluated / 未测评</p>'
        for operation,run in node['regressions'].items():
            rows=list(run['tasks'].values());passed=run.get('passed',sum(bool(r['ok']) for r in rows))
            total=run.get('total',len(rows))
            body+='<h4>MBPP+ '+esc(operation)+'</h4><p>'+esc(f"{run['source']}: {passed}/{total}; "+('complete' if run['complete'] else 'partial / 未完成'))+'</p>'
            body+=table(['Task','Result','Test inputs','Execution error'],[
                [r['task'],'pass' if r['ok'] else 'fail',r.get('cases',''),
                 r.get('error') or r.get('trace',{}).get('stderr','')] for r in rows])
        body+='<h4>Challenger selection tasks</h4>'
        if not node['challenges']:body+='<p>Not evaluated / 未测评</p>'
        else:
            body+=table(['Record','Task','Goal','Epoch','Challenger commit','Test version','Result','Evidence','Error'],[
                [r[k] for k in ('record','task','goal','epoch','challenger','test_version','result','evidence','error')]
                for r in node['challenges']])
        body+='<h4>Challenger training tasks (excluded from selection statistics)</h4>'
        if node['training']:
            body+=table(['Transaction','Task','Goal','Challenger commit','Result','Error'],[
                [r[k] for k in ('transaction','task','goal','challenger','result','error')] for r in node['training']])
        else:body+='<p>No attributable training record / 无可归属的训练记录</p>'
    return body

def final_winner(events):
    # A prior result is stale after any later state transition, including resume.
    for event in reversed(events):
        if event.get('type')=='result':return event.get('winner')
        if event.get('type')=='state' and event.get('reason')!='report_update':return None
    return None

def evolution_tree(results,winner):
    """Render archived Seed ancestry; evaluation labels are explicitly scoped."""
    nodes={n['node']:n for n in results if n['kind']=='seed'}
    if not nodes:return '<p>没有已归档的 Seed 节点。</p>'
    children={n:[] for n in nodes};roots=[]
    for node,info in nodes.items():
        parent=info.get('parent')
        if parent in nodes and parent!=node:children[parent].append(node)
        else:roots.append(node)
    for group in children.values():group.sort()
    positions={};next_row=0;visiting=set()
    def place(node,depth):
        nonlocal next_row
        if node in positions or node in visiting:return
        visiting.add(node)
        for child in children[node]:place(child,depth+1)
        rows=[positions[c][1] for c in children[node] if c in positions]
        if rows:y=sum(rows)/len(rows)
        else:y=next_row;next_row+=1
        positions[node]=(depth,y);visiting.remove(node)
    for node in sorted(roots):place(node,0)
    for node in sorted(nodes):
        if node not in positions:place(node,0)
    def coord(node):
        depth,row=positions[node];return 25+depth*265,25+row*125
    width=max(620,(max(p[0] for p in positions.values())+1)*265+35)
    height=max(155,next_row*125+30)
    out=[f'<svg class="tree" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Seed evolution tree">']
    for parent,kids in children.items():
        for child in kids:
            x1,y1=coord(parent);x2,y2=coord(child)
            out.append(f'<path d="M{x1+230},{y1+48} C{x1+248},{y1+48} {x2-18},{y2+48} {x2},{y2+48}" fill="none" stroke="#687782" stroke-width="2"/>')
    for node,info in nodes.items():
        x,y=coord(node);color='#16803c' if node==winner and info['status']=='accepted' else '#66717a'
        automatic=[r for r in info['regressions'].values() if r['source']=='automatic']
        if automatic:
            run=automatic[-1];rows=list(run['tasks'].values())
            mbpp=f"{run.get('passed',sum(bool(r['ok']) for r in rows))}/{run.get('total',len(rows))}"
            if not run['complete']:mbpp+=' 未完成'
        else:mbpp='未测评'
        active_challenges=[r for r in info['challenges'] if r['evidence']=='active']
        if active_challenges:
            challenges=f"{sum(r['result']=='pass' for r in active_challenges)}/{len(active_challenges)}"
        else:challenges='未测评'
        excluded=sum(r['evidence']!='active' for r in info['challenges'])
        suffix=f'（另 {excluded} 条失效/无效）' if excluded else ''
        label='最终选择' if node==winner and info['status']=='accepted' else ('已拒绝' if info['status']=='rejected' else '中间节点')
        esc=html.escape
        out.append(f'<a href="#node-{esc(node,quote=True)}"><title>{esc(node)} — {esc(label)}</title><rect x="{x}" y="{y}" width="230" height="96" rx="8" fill="{color}"/><text x="{x+10}" y="{y+20}" fill="white" font-size="13">{esc(node[:12])} · {label}</text><text x="{x+10}" y="{y+44}" fill="white" font-size="13">MBPP+: {esc(mbpp)}</text><text x="{x+10}" y="{y+67}" fill="white" font-size="13">Challenger: {esc(challenges)}</text><text x="{x+10}" y="{y+86}" fill="white" font-size="11">{esc(suffix)}</text></a>')
    out.append('</svg>')
    return ''.join(out)

def render(root,state,events,usage):
    rows=[];valid=active(state['records'],state['slots'])
    for kind,tree in state['trees'].items():
        for node,metadata in sorted(tree.items()):
            s,f=counts(valid,{node})
            fields=[kind,node[:12],(metadata['parent'] or 'root')[:12],str(s),str(f),metadata['strategy']]
            rows.append('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in fields)+'</tr>')
    transitions=[e['details'] for e in events if e.get('reason')=='checkpoint']
    points=[]
    for r in state['records']:
        points.append(f'<circle cx="{30+r["id"]*22}" cy="{35 if r["ok"] else 100}" r="5" fill="{"#087f5b" if r in valid else "#adb5bd"}"/>')
    chart=f'<svg viewBox="0 0 {max(400,len(points)*22+60)} 135" role="img" aria-label="Each dot is one original evaluation, upper row pass, lower row fail, grey invalidated">'+''.join(points)+'</svg>'
    details={'epoch':state['epoch'],'evaluations':state['n'],'active_records':len(valid),
             'original_records':len(state['records']),'usage':usage,'config':state['config'],
             'pending':state['pending'],'rejected_candidates':state['rejected']}
    body='<h1>RQGM real experiment</h1><p>Operator-only report. A running experiment is not evidence of emergent capabilities. Fixed evidence anchors validate verdict semantics; generated scenario relevance still requires research review.</p>'
    body+='<h2>State and budgets</h2><pre>'+html.escape(json.dumps(details,ensure_ascii=False,indent=2))+'</pre>'
    body+='<h2>Evaluation history</h2><p>Upper: pass; lower: fail. Grey: invalidated, retained in journal.</p>'+chart
    results=node_results(root,state,events);winner=final_winner(events)
    body+='<h2>Seed 进化树</h2><p>绿色：本次已完成运行的最终选择；灰色：其他节点（包括已拒绝候选）。点击节点查看逐题明细。MBPP+ 显示最近一次自动回归，人工复测见明细；Challenger 显示当前有效选择任务通过数/总数，不含训练、失效或无效任务。没有当前最终结果时不标绿。</p><div class="tree-scroll">'+evolution_tree(results,winner)+'</div>'
    body+='<h2>Evolution trees</h2><table><tr><th>Tree</th><th>Commit</th><th>Parent</th><th>Pass</th><th>Fail</th><th>Modification</th></tr>'+''.join(rows)+'</table>'
    body+=results_html(results)
    body+='<h2>Epoch boundaries</h2><pre>'+html.escape(json.dumps(transitions,ensure_ascii=False,indent=2))+'</pre>'
    body+='<h2>Scenario versions</h2><ul>'+''.join('<li>'+html.escape(version[:12]+': '+', '.join(c['id'] for c in suite['cases']))+'</li>' for version,suite in state['suites'].items())+'</ul>'
    Path(root,'report.html').write_text('<!doctype html><meta charset="utf-8"><title>RQGM experiment</title><style>body{font:16px system-ui;margin:32px auto;max-width:1150px;background:#fafafa;color:#123}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:10px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}svg:not(.tree){max-width:100%}.tree-scroll{overflow:auto}.tree{max-width:none;display:block}.tree a:hover rect{stroke:#111;stroke-width:3}</style>'+body)
