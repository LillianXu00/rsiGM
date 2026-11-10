"""Editable meta-agent. Both this program and executor.py belong to one node."""
import json,sys
x=json.load(sys.stdin)
print(json.dumps({'system':'Improve the complete agent, including your own modification method. Preserve user goals and principles. Choose architecture yourself.', 'prompt':json.dumps(x,ensure_ascii=False)}))
