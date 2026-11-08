"""Revise only the saved demo's presentation; never repeat AI/network work.

Run as: python -m scripts.qa_rerender_comparison
Original artifacts and the previous answer/claims remain in the QA database.
"""
from pathlib import Path
import json
from nexus.files import generate_files
from nexus.store import Store
from nexus.synthesis import synthesize_comparison

root=Path(__file__).resolve().parent.parent
session=json.loads((root/'tmp/qa-session.json').read_text())
user=session['user_id']
task_id=(root/'tmp/demo-task-id.txt').read_text().strip()
store=Store(root/'tmp/qa-data/nexus.sqlite3')
task=store.task(user,task_id)
assert task and task['status']=='completed' and task['research_mode']=='evidence_id_comparison'


class SavedDraft:
    def complete_json(self,*args,**kwargs):
        return dict(findings=[dict(id=i,text=claim['text']) for i,claim in enumerate(task['claims'],1)])


revision=synthesize_comparison(task['prompt'],task['sources'],SavedDraft())
assert [c['source_numbers'] for c in revision['claims']]==[c['source_numbers'] for c in task['claims']]
content=revision['answer']+'\n\nEvidence limitations\n'+'\n'.join(dict.fromkeys(task['warnings']))
rows=[['Application','Summary','Source comparison','References']]+[[c['application'],c['summary'],c['comparison'],' '.join(f'[{n}]' for n in c['source_numbers'])] for c in revision['comparison']]
directory=root/'tmp/qa-data'/user/task_id
replacements={}
for generated in generate_files(directory,task['execution_plan']['title'],content,['pdf','docx','xlsx','pptx'],sources=task['sources'],rows=rows):
    generated['path']=str((directory/generated['filename']).resolve())
    replacements[generated['format']]=store.add_artifact(user,task_id,generated)
previous=task.get('presentation_revisions',[])+[dict(answer=task['answer'],claims=task['claims'],artifacts=task['artifacts'])]
store.update(user,task_id,answer=revision['answer'],claims=revision['claims'],comparison=revision['comparison'],
             artifacts=[replacements[a['format']] for a in task['artifacts']],presentation_revisions=previous)
store.event(user,task_id,'renderer_revision','Regenerated four formats after layout repairs and explicit historical-preview framing. Reused the saved model draft and identical retrieved evidence; no new model/search call. Prior answer and artifacts retained.')
(root/'tmp/final-demo-result.json').write_text(json.dumps(store.task(user,task_id),indent=2),encoding='utf-8')
print('Four comparison formats revised and verified; prior answer and artifacts retained:',task_id)
