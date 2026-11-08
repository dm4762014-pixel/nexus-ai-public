"""Apply reviewed wording corrections to the isolated fuller-report QA sample.

No new model/search call. Prior AI draft and files are preserved as a revision.
This is a specific acceptance review, not a general automated fact checker.
"""
from pathlib import Path
import json
import shutil
import httpx
from nexus.files import generate_files
from nexus.store import Store
ROOT=Path(__file__).resolve().parent.parent
session=json.loads((ROOT/'tmp/features-qa-session.json').read_text())
store=Store(ROOT/'tmp/features-qa-data/nexus.sqlite3')
task_id='88a17dfbaa794fb5b57722e26a7d205b'
assert session.get('task_ids', [None])[0] == task_id, 'This wording review applies only to its recorded acceptance task; do not apply it to a different run.'
with store.connect() as db:owner=db.execute('SELECT user_id FROM tasks WHERE id=?',(task_id,)).fetchone()[0]
task=store.task(owner,task_id)
assert task['status']=='completed' and len(task['claims'])==6
revisions=task.get('review_revisions',[])
if not revisions:
    original=dict(answer=task['answer'],claims=task['claims'],comparison=task['comparison'],artifacts=task['artifacts'])
    corrections={
        task['claims'][0]['text']:'PostgreSQL and SQLite pursue different goals, and those differences shape their design.',
        task['claims'][1]['text']:'SQLite in WAL mode allows readers and a writer to work concurrently, with only one writer active at a time.',
        task['claims'][2]['text']:'SQLite supports multiple concurrent readers while allowing only one process to write at a time.',
    }
    answer=task['answer']
    for before,after in corrections.items():answer=answer.replace(before,after)
    claims=[dict(claim,text=corrections.get(claim['text'],claim['text'])) for claim in task['claims']]
    comparison=[dict(row,summary=corrections.get(row['summary'],row['summary'])) for row in task['comparison']]
    rows=[['Aspect','Summary','Source comparison','References']]+[[r['application'],r['summary'],r['comparison'],' '.join(f'[{n}]' for n in r['source_numbers'])] for r in comparison]
    directory=ROOT/'tmp/features-qa-data'/owner/task_id
    replacements=[]
    content=answer+'\n\nEvidence limitations\n'+'\n'.join(dict.fromkeys(task['warnings']))
    for item in generate_files(directory,task['execution_plan']['title'],content,['pdf','docx','xlsx','pptx'],sources=task['sources'],rows=rows):
        item['path']=str((directory/item['filename']).resolve());replacements.append(store.add_artifact(owner,task_id,item))
    store.update(owner,task_id,answer=answer,claims=claims,comparison=comparison,artifacts=replacements,review_revisions=[original])
    store.event(owner,task_id,'review_revision','Acceptance review removed unsupported product attributes and an unstated purpose from two sentences; simplified one further sentence. Source evidence and earlier AI draft/files retained. No new inference or retrieval.')
task=store.task(owner,task_id);output=Path(session['output']);prior=output/'original-ai-draft';prior.mkdir(exist_ok=True)
for path in output.iterdir():
    if path.is_file() and path.suffix in ('.pdf','.docx','.pptx','.xlsx','.json') and not (prior/path.name).exists():shutil.copy2(path,prior/path.name)
with httpx.Client(base_url='http://127.0.0.1:8005',trust_env=False,cookies={c['name']:c['value'] for c in session['cookies']},timeout=20) as client:
    for artifact in task['artifacts']:
        response=client.get(artifact['url']).raise_for_status();assert artifact['verified'];(output/artifact['name']).write_bytes(response.content)
report=json.loads((output/'acceptance-results.json').read_text());report['tasks'][0]['answer']=task['answer'];report['tasks'][0]['comparison']=task['comparison'];report['tasks'][0]['downloads']=[dict(name=a['name'],format=a['format'],size=a['size'],sha256=a['sha256']) for a in task['artifacts']];report['review_revision']=dict(new_inference=False,new_retrieval=False,prior_draft_retained=True,note='Reviewed sample wording corrected to match selected evidence. Automated provenance checks alone do not verify factual entailment.')
(output/'acceptance-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(ROOT/'tmp/features-final-output.txt').write_text(str(output));(ROOT/'tmp/features-final-basename.txt').write_text(next(output.glob('*.pptx')).stem)
print(json.dumps(dict(reviewed_task=task_id,findings=len(task['claims']),output=str(output),downloads=4)))
