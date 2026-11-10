# Evidence judge. The controller executes submitted oracles; this layer adjudicates evidence.
import json,sys
x=json.load(sys.stdin)
checks=x.get('checks',[])
# Deliberately minimal starting implementation; methods remain editable.
ok=bool(checks) and all(c.get('ok') is True for c in checks) and not x.get('execution_error',False)
print(json.dumps({'ok':ok}))
