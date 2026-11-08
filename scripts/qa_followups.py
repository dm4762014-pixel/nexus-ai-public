"""Real UI -> local model -> follow-ups -> PDF acceptance, using isolated QA.

Run: python -m scripts.qa_followups
After restarting the QA server: python -m scripts.qa_followups --verify-saved
Synthetic credentials/session stay in ignored tmp; reports omit credentials.
Chromium closes between submissions to release RAM during local inference.
"""
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
import argparse
import json
import secrets
import time
import httpx
import psutil
from playwright.sync_api import sync_playwright, expect
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parent.parent
BASE='http://127.0.0.1:8005'
STATE=ROOT/'tmp/followup-qa-session.json'


@contextmanager
def ui(session=None, width=1440):
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            context=browser.new_context(viewport=dict(width=width,height=1000),reduced_motion='reduce')
            if session:context.add_cookies(session['cookies'])
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(BASE,wait_until='networkidle')
            yield page,context,errors
            assert not errors,errors
        finally:browser.close()


def submit(page,prompt,parent=None):
    if parent:
        page.get_by_role('button',name=parent['prompt'],exact=True).first.click()
        page.get_by_role('button',name='Follow up',exact=True).click()
        assert page.get_by_role('status').inner_text().startswith('Following up on:')
    else:page.get_by_label('Task mode',exact=True).select_option('chat')
    page.get_by_label('Your task',exact=True).fill(prompt)
    with page.expect_response(lambda r:r.url.endswith('/api/tasks') and r.request.method=='POST') as response:
        page.get_by_role('button',name='Start task',exact=True).click()
    result=response.value
    assert result.status==202,result.text()
    task=result.json()
    assert task['request']['parent_task_id']==(parent['id'] if parent else None)
    return task


def wait(client,task_id,report):
    started=time.monotonic()
    while time.monotonic()-started<330:
        if report['minimum_available_bytes'] is not None:
            report['minimum_available_bytes']=min(report['minimum_available_bytes'],psutil.virtual_memory().available)
        task=client.get('/api/tasks/'+task_id).raise_for_status().json()
        if task['status'] not in ('queued','planning','running'):
            assert task['status']=='completed',dict(status=task['status'],error=task.get('error'))
            seconds=(datetime.fromisoformat(task['completed_at'])-datetime.fromisoformat(task['created_at'])).total_seconds()
            report['tasks'].append(dict(id=task['id'],status=task['status'],answer=task['answer'],seconds=round(seconds,2),context_turns=len(task.get('context',{}).get('turns',[]))))
            print(json.dumps(report['tasks'][-1]),flush=True)
            return task
        time.sleep(1)
    raise TimeoutError('Follow-up QA task deadline')


def verify(client,session,report):
    child=client.get('/api/tasks/'+session['task_ids'][-1]).raise_for_status().json()
    assert child['status']=='completed' and len(child['context']['turns'])==2
    assert child['context']['parent_task_id']==session['task_ids'][-2]
    assert child['context']['text_characters']<=2400
    assert not child['execution_plan']['research'] and not child['execution_plan']['code']
    assert not child['execution_plan']['browser_url']
    for term in (session['project_code'],'Leena','Wednesday'):
        assert term.lower() in child['answer'].lower(),(term,child['answer'])
    output=Path(session['output'])
    for artifact in child['artifacts']:
        response=client.get(artifact['url']).raise_for_status()
        assert 'attachment' in response.headers['content-disposition'] and artifact['verified']
        assert artifact['format']=='pdf'
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
        assert all(term.lower() in text.lower() for term in (session['project_code'],'Leena','Wednesday'))
        (output/'Project-handoff.pdf').write_bytes(response.content)
    assert len(child['artifacts'])==1
    with ui(session) as (page,_,errors):
        page.get_by_role('button',name=child['prompt'],exact=True).first.click()
        page.get_by_role('button',name='View previous task',exact=True).wait_for()
        expect(page.locator('.details-id')).to_have_text(child['id'][:8])
        assert 'Uses 2 prior results' in page.locator('.context-note').inner_text()
        page.screenshot(path=str(output/'followup-desktop.png'),full_page=True)
        for width in (1440,390):
            page.set_viewport_size(dict(width=width,height=1000))
            assert page.evaluate('document.documentElement.scrollWidth')==width
        page.screenshot(path=str(output/'followup-mobile.png'),full_page=True)
        page.get_by_role('button',name='View previous task',exact=True).click()
        expect(page.locator('.user-message p')).to_have_text(session['followup_prompt'])
        expect(page.locator('.details-id')).to_have_text(session['task_ids'][-2][:8])
        page.get_by_role('button',name='Follow up',exact=True).click()
        page.get_by_label('Your task',exact=True).fill('A separate editable question')
        for width,label in ((390,'mobile'),(1440,'desktop')):
            page.set_viewport_size(dict(width=width,height=1000))
            assert page.evaluate('document.documentElement.scrollWidth')==width
            page.screenshot(path=str(output/('followup-composer-'+label+'.png')),full_page=True)
        page.get_by_role('button',name='Remove prior context',exact=True).click()
        assert page.get_by_label('Your task',exact=True).input_value()=='A separate editable question'
        assert page.locator('.followup-context').count()==0
        report['browser_errors']=errors
    report['verified']=True
    report['final_task_id']=child['id']
    (output/'acceptance-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(verified=True,output=str(output),task_id=child['id'])),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-saved',action='store_true');args=parser.parse_args()
    report=dict(tasks=[],minimum_available_bytes=psutil.virtual_memory().available)
    if args.verify_saved:
        session=json.loads(STATE.read_text())
        saved_report=Path(session['output'])/'acceptance-results.json'
        if saved_report.exists():report=json.loads(saved_report.read_text())
        else:report['minimum_available_bytes']=None
        report['saved_results_reopened']=True
    else:
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
        output=ROOT/'outputs'/('followup-demo-'+stamp);output.mkdir(exist_ok=False)
        with ui() as (page,context,_):
            username='followup-'+secrets.token_hex(4);password=secrets.token_urlsafe(24)
            if page.get_by_role('button',name='Create local account',exact=True).count():
                page.get_by_label('Username',exact=True).fill(username)
                page.get_by_label('Password',exact=True).fill(password)
                page.get_by_role('button',name='Create local account',exact=True).click()
            else:
                # Reuse only our previous isolated QA login, never production.
                saved=json.loads(STATE.read_text());username=saved['username'];password=saved['password']
                page.get_by_label('Username',exact=True).fill(username);page.get_by_label('Password',exact=True).fill(password)
                page.get_by_role('button',name='Sign in',exact=True).click()
            page.get_by_label('Your task',exact=True).wait_for()
            profile=context.request.get(BASE+'/api/me').json()
            session=dict(username=username,password=password,cookies=context.cookies(),csrf=profile['csrf'],output=str(output),task_ids=[],project_code='CORAL-'+secrets.token_hex(2).upper())
            STATE.write_text(json.dumps(session),encoding='utf-8')
            prompt=f"Project facts: code {session['project_code']}; owner Leena; review Wednesday. Create a TXT brief in three short bullets. Use only these facts."
            root=submit(page,prompt)
        session['task_ids'].append(root['id'])
    with httpx.Client(base_url=BASE,trust_env=False,cookies={c['name']:c['value'] for c in session['cookies']},timeout=15) as client:
        assert client.get('/api/me').status_code==200
        if not args.verify_saved:
            root=wait(client,root['id'],report)
            session['followup_prompt']='State the project code, owner and review day from the previous result in one sentence.'
            with ui(session) as (page,_,__):child=submit(page,session['followup_prompt'],root)
            session['task_ids'].append(child['id']);child=wait(client,child['id'],report)
            for term in (session['project_code'],'Leena','Wednesday'):assert term.lower() in child['answer'].lower(),child['answer']
            with ui(session) as (page,_,__):final=submit(page,'Create a PDF handoff note with the same project code, owner and review day. Use one short paragraph and no additional facts.',child)
            session['task_ids'].append(final['id']);wait(client,final['id'],report)
            STATE.write_text(json.dumps(session),encoding='utf-8')
        elif not report['tasks']:
            for task_id in session['task_ids']:wait(client,task_id,report)
        report['verified']=False
        (Path(session['output'])/'acceptance-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        verify(client,session,report)


if __name__=='__main__':main()
