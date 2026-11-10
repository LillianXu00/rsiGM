# Editable mock generator. Its distribution is frozen with the evaluator version.
import json,sys,random
request=json.load(sys.stdin)
x=random.Random(request['nonce']).randrange(1,1000)
print(json.dumps({'prompt':f'Return the integer square of {x}.','input':x,'expected':x*x,'oracle':'integer equality','reference':x*x,'negative_control':x*x+1}))
