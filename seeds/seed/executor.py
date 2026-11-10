"""Minimal editable executor; no prescribed delegation or memory architecture."""
import json,sys
x=json.load(sys.stdin)
print(json.dumps({'system':'Solve the user task. Return executable Python where requested.', 'prompt':json.dumps(x,ensure_ascii=False)}))
