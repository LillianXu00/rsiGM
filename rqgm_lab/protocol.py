"""Public primitive contract; no task solution, architecture or private validation data."""
CONTRACT = '''The editable Python entry reads one JSON value from stdin and prints one JSON object.
Input: {input: original request, state: your JSON state (initially null), observation: last primitive result (initially null)}.
Actions:
 {action:"model", prompt:"...", system:"...", state:...} calls the role's coding runtime in an independent context.
 {action:"python", code:"...", stdin:"...", state:...} runs arbitrary Python in the current workspace, without network or credentials.
 {action:"parallel", jobs:[{action:"model",prompt:"...",system:"..."}|{action:"python",code:"...",stdin:"..."}, ...], state:...} runs at most two jobs in independent contexts and independent temporary workspaces. Each job can include files:{relative_path:text}. Results preserve input order and include stdout/text, files, timing and context ID. No memory is automatically shared. A parallel job may instead use {action:"context",files:{path:source},entry:"executor.py",input:JSON} to run a complete independent multi-step harness; nested parallel is disabled. Each context may autonomously alternate model and Python primitives.
 {action:"finish", result: JSON_value} returns your result.
You may add or change arbitrary workspace files and your own program/control flow. Workspace files persist across turns of the same scenario. Choose your own context, identity, memory, collaboration and task strategy. Processes cannot access host files or credentials. Primitive responses are returned as observation on the next entry call. Python primitives have no model access; choose model actions for model calls. Steps, child contexts, output size, wall time and API budget are bounded externally.
'''
GOALS = '''Research goals only: (1) autonomous concurrent task execution in independent contexts; (2) unified individual identity, long-term memory, user goals and behavior principles, with collaboration. Do not assume a Router/Worker, shared-memory or other target architecture. Discover weaknesses and modify your own method as well as task behavior.'''
CASE_CONTRACT = '''Write a Python program defining build_suite() which returns a dict {cases:[...]}. Return only Python source, no markdown. Use native Python dicts/lists and triple-quoted strings for oracle source, avoiding nested JSON escaping. Include exactly two novel executable cases, one goal "distributed" and one "individuality". No markdown.
Each case: {id:short_unique_string, goal, rationale, difficulty, turns:[task_string,...], files:{relative_path:text}, oracle:Python_source, positive:observation, negatives:[observation,...]}.
Use 1 to 3 turns. The executor receives only turns and files. The same workspace persists across turns. It may generate files, model calls, Python executions or parallel isolated contexts using the public primitive contract.
The oracle defines check(observation)->bool; only Python standard library. observation has answers:[string_or_JSON], files:{relative_path:text}, events:[primitive_events]. Each event has action, context, started, ended, and for parallel an ordered jobs array, each with action, context, started, ended. Timing is controller recorded. Do not require a preselected implementation architecture. Build observable objective requirements, including behavioral consistency or execution overlap if relevant.
positive and negatives are full synthetic observations used only to verify your oracle, not shown to the executor. Include at least one negative that violates the actual task. Do not merely inspect a self-reported success claim. Ensure positive passes and every negative fails; the controller executes the oracle twice for determinism. The oracle does not receive the controls or their labels. Your oracle must be executable and under 8KiB. No external network or packages. Aim for tests feasible within two parallel contexts, three model calls per turn and eight primitive steps. You choose tasks, difficulty and method. Explain in rationale why the observable checks measure the requested goal. Return compact Python source, total response within 4000 tokens. Do not print anything; the host calls build_suite().'''

def json_object(text):
    import json
    if not isinstance(text,str):return text
    t=text.strip()
    if t.startswith('```'):
        t=t.split('\n',1)[1].rsplit('```',1)[0].strip()
    value=json.loads(t)
    if not isinstance(value,dict):raise ValueError('expected JSON object')
    return value

def code_text(text):
    text=str(text).strip()
    if text.startswith('```'):return text.split('\n',1)[1].rsplit('```',1)[0].strip()
    return text
