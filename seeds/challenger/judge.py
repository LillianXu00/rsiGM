# Mock starting defect: accepting every execution. Only used for plumbing tests.
import json,sys
x=json.load(sys.stdin)
print(json.dumps({'ok':True}))
