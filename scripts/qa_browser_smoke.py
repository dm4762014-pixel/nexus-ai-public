"""Actual owner-approved browser lifecycle check on the isolated QA server."""
from pathlib import Path
import json
import time
import httpx

root=Path(__file__).resolve().parent.parent
session=json.loads((root/'tmp/qa-session.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8005',cookies={cookie['name']:cookie['value'] for cookie in session['cookies']},headers={'X-CSRF-Token':session['csrf']},timeout=15) as client:
    response=client.post('/api/tasks',json=dict(prompt='Visit https://example.com and create a read-only screenshot.',mode='browser'))
    response.raise_for_status(); task_id=response.json()['id']
    deadline=time.monotonic()+90; approved=False
    while time.monotonic()<deadline:
        response=client.get('/api/tasks/'+task_id); response.raise_for_status(); task=response.json()
        if task['status']=='awaiting_approval' and not approved:
            approval=next(item for item in client.get('/api/approvals').json() if item['task_id']==task_id and item['status']=='pending')
            decision=client.post('/api/approvals/'+approval['id'],json={'approved':True}); decision.raise_for_status(); approved=True
        if task['status'] in ('completed','failed','cancelled'):
            break
        time.sleep(.5)
    report={key:task.get(key) for key in ('id','status','error','warnings','events')}
    report['approved']=approved
    report['downloads']=[dict(status=client.get(artifact['url']).status_code,format=artifact['format'],verified=artifact['verified']) for artifact in task['artifacts']]
    (root/'tmp/final-browser-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    assert task['status']=='completed',report
    assert any('Released local model before Chromium' in event['message'] for event in task['events'])
