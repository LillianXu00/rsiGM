"""Private fixed evidence anchors. No task bank exposed to either evolving role."""
from .scenarios import judge

def cases():
    good={'id':'a','ok':True};bad={'id':'a','ok':False}
    return [
      ({'checks':[good],'execution_error':False},True),
      ({'checks':[good,{'id':'b','ok':True}],'execution_error':False},True),
      ({'checks':[bad],'execution_error':False},False),
      ({'checks':[good,{'id':'b','ok':False}],'execution_error':False},False),
      ({'checks':[],'execution_error':False},False),
      ({'checks':[good],'execution_error':True},False),
      ({'checks':[good,good],'execution_error':False},False),
      ({'checks':[{'id':'','ok':True}],'execution_error':False},False),
      ({'checks':[{'ok':True}],'execution_error':False},False),
      ({'checks':[{'id':'a','ok':1}],'execution_error':False},False),
      ({'checks':[{'id':'a','ok':'true'}],'execution_error':False},False),
      ({'checks':[good],'execution_error':0},False),
      ({'checks':[good]},False),
      ({'checks':None,'execution_error':False},False),
      ({'checks':[{'id':'a'}],'execution_error':False},False),
      ({'checks':[{'id':'c','ok':True},{'id':'d','ok':True}],'execution_error':False},True),
    ]

def score(files):
    outcomes=[]
    for evidence,label in cases():
        try:ok=judge(files,evidence) is label
        except Exception:ok=False
        outcomes.append(ok)
    return {'ok':sum(outcomes),'total':len(outcomes),'outcomes':outcomes}
