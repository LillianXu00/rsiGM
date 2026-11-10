"""RQGM B.2/B.3; HGM CMP counts and temperature schedule."""
from .vendor.beta import best_belief

def active(records, slots):
    return [r for r in records if r.get('usable',True) and all(slots.get(k)==v for k,v in r['deps'].items())]

def counts(records, nodes):
    s=sum(r['ok'] for r in records if r['node'] in nodes)
    n=sum(1 for r in records if r['node'] in nodes)
    return s,n-s

def clade(tree, node):
    result={node}
    while True:
        more={k for k,v in tree.items() if v['parent'] in result}
        if more <= result:return result
        result |= more

def sample(tree, records, rng, expand=False, tau=1):
    draws={}
    for node in sorted(tree):
        s,f=counts(records, clade(tree,node) if expand else {node})
        draws[node]=rng.betavariate(tau*(1+s),tau*(1+f))
    return max(draws,key=draws.get),draws

def cell(records,node,cells,rng):
    own=[r for r in records if r['node']==node]
    roles=sorted({r for r,d in cells})
    rc={r:sum(x['role']==r for x in own) for r in roles}
    role=rng.choice([r for r in roles if rc[r]==min(rc.values())])
    dc={d:sum(x['role']==role and x['task']==d for x in own) for r,d in cells if r==role}
    return role,rng.choice([d for d in dc if dc[d]==min(dc.values())])

def best(tree,records):
    return max(sorted(tree),key=lambda n:best_belief(*counts(records,{n})))
