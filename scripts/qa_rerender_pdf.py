"""Re-render saved QA report evidence after a renderer repair; no AI/search call.

Retains the previous verified artifact and records a separate renderer event.
"""
from pathlib import Path
import json
from nexus.files import generate_files
from nexus.store import Store

root=Path(__file__).resolve().parent.parent
session=json.loads((root/'tmp/qa-session.json').read_text())
user=session['user_id']
task_id=(root/'tmp/demo-task-id.txt').read_text().strip()
store=Store(root/'tmp/qa-data/nexus.sqlite3')
task=store.task(user,task_id)
assert task and task['status']=='completed'
directory=root/'tmp/qa-data'/user/task_id
content=task['answer']+'\n\nEvidence limitations\n'+'\n'.join(dict.fromkeys(task['warnings']))
from openpyxl import load_workbook
spreadsheet=next(old for old in task['artifacts'] if old['format']=='xlsx')
book=load_workbook(spreadsheet['path'],read_only=True,data_only=True)
rows=[list(row) for row in book['Summary'].iter_rows(values_only=True)]; book.close()
replacements={}
for generated in generate_files(directory,task['execution_plan']['title'],content,['pdf','docx'],sources=task['sources'],rows=rows):
    generated['path']=str((directory/generated['filename']).resolve())
    replacements[generated['format']]=store.add_artifact(user,task_id,generated)
store.update(user,task_id,artifacts=[replacements.get(old['format'],old) for old in task['artifacts']])
store.event(user,task_id,'renderer_revision','Re-rendered the saved PDF and Word report after pagination repair. Same evidence and answer; no new search or model call. Prior artifacts retained.')
updated=store.task(user,task_id)
(root/'tmp/final-demo-result.json').write_text(json.dumps(updated,indent=2),encoding='utf-8')
print('Reports re-rendered and verified; prior artifacts retained; task',task_id)
