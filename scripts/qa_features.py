"""Live compiled UI acceptance: general research/four formats and approved pages.

Use scripts.qa_features_server on port8005. Synthetic credentials stay in tmp.
Browsers close during model inference and the server's own Chromium reading.
"""
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import secrets
import sys
import time
import httpx
import psutil
from playwright.sync_api import sync_playwright, expect
from nexus.files import extract_upload
from pptx import Presentation
from openpyxl import load_workbook
from scripts.qa_followups import ui

ROOT=Path(__file__).resolve().parent.parent
BASE='http://127.0.0.1:8005'
STATE=ROOT/'tmp/features-qa-session.json'
RESEARCH='Research SQLite and PostgreSQL database design differences. Compare reliable sources. Create a PDF report, Word document, PowerPoint presentation and Excel comparison table with source references.'
BROWSER='Read https://example.com and https://www.python.org/about/ and capture both public pages.'


def submit(page, prompt, mode):
    page.get_by_label('Task mode',exact=True).select_option(mode)
    page.get_by_label('Your task',exact=True).fill(prompt)
    with page.expect_response(lambda r:r.url.endswith('/api/tasks') and r.request.method=='POST') as pending:
        page.get_by_role('button',name='Start task',exact=True).click()
    assert pending.value.status==202,pending.value.text()
    return pending.value.json()


def wait(client, task_id, report, expected='completed'):
    started=time.monotonic()
    while time.monotonic()-started<330:
        report['minimum_available_bytes']=min(report['minimum_available_bytes'],psutil.virtual_memory().available)
        task=client.get('/api/tasks/'+task_id).raise_for_status().json()
        if task['status'] not in ('queued','planning','running'):
            assert task['status']==expected,dict(id=task_id,status=task['status'],error=task.get('error'))
            return task
        time.sleep(1)
    raise TimeoutError(task_id)


def downloads(client, task, output):
    downloaded=[]
    for item in task['artifacts']:
        response=client.get(item['url']).raise_for_status()
        assert item['verified'] and 'attachment' in response.headers['content-disposition']
        path=output/item['name'];path.write_bytes(response.content)
        assert sha256(response.content).hexdigest()==item['sha256']
        downloaded.append(dict(name=item['name'],format=item['format'],size=len(response.content),sha256=item['sha256']))
    return downloaded


def main():
    output=ROOT/'outputs'/('features-demo-'+datetime.now().strftime('%Y%m%d-%H%M%S'));output.mkdir()
    report=dict(minimum_available_bytes=psutil.virtual_memory().available,tasks=[],browser_errors=[])
    with ui() as (page,context,errors):
        if page.get_by_role('button',name='Create local account',exact=True).count():
            username='features-'+secrets.token_hex(4);password=secrets.token_urlsafe(24)
            page.get_by_label('Username',exact=True).fill(username);page.get_by_label('Password',exact=True).fill(password)
            page.get_by_role('button',name='Create local account',exact=True).click()
        else:
            saved=json.loads(STATE.read_text());username=saved['username'];password=saved['password']
            page.get_by_label('Username',exact=True).fill(username);page.get_by_label('Password',exact=True).fill(password)
            page.get_by_role('button',name='Sign in',exact=True).click()
        page.get_by_label('Your task',exact=True).wait_for()
        profile=context.request.get(BASE+'/api/me').json()
        session=dict(username=username,password=password,cookies=context.cookies(),csrf=profile['csrf'],output=str(output))
        STATE.write_text(json.dumps(session),encoding='utf-8')
        research=submit(page,RESEARCH,'research') if '--browser-only' not in sys.argv else None
    with httpx.Client(base_url=BASE,trust_env=False,cookies={c['name']:c['value'] for c in session['cookies']},headers={'X-CSRF-Token':session['csrf']},timeout=20) as client:
        if research:
            research=wait(client,research['id'],report)
            assert research['research_mode']=='general_evidence_comparison',dict(mode=research.get('research_mode'),warnings=research['warnings'])
            assert len(research['sources'])>=2 and len(research['comparison'])>len(research['sources']),dict(points=len(research['comparison']),warnings=research['warnings'])
            assert all(row['summary'].endswith(('.', '!', '?')) for row in research['comparison']),research['comparison']
            assert {a['format'] for a in research['artifacts']}=={'pdf','docx','pptx','xlsx'}
            for claim in research['claims']:
                for evidence in claim['evidence']:
                    source=next(s for s in research['sources'] if s['number']==evidence['source_number'])
                    assert evidence['quote'] in source['text']
            report['tasks'].append(dict(id=research['id'],kind='general_research',mode=research['research_mode'],answer=research['answer'],sources=[{k:s.get(k) for k in ('number','title','url')} for s in research['sources']],comparison=research['comparison'],model_metrics=research.get('model_metrics'),downloads=downloads(client,research,output)))
            for item in research['artifacts']:
                path=output/item['name'];text=extract_upload(path)
                assert text.strip()
                if item['format']=='xlsx':assert load_workbook(path).active.cell(1,1).value=='Aspect'
                if item['format']=='pptx':
                    deck=Presentation(path)
                    assert any(shape.name=='Comparison overview root' for slide in deck.slides for shape in slide.shapes),'No editable diagram'
            (output/'acceptance-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(dict(stage='research',id=research['id'],mode=research['research_mode'],output=str(output))),flush=True)
        with ui(session) as (page,_,errors):
            if research:
                page.get_by_role('button',name=RESEARCH,exact=True).first.click()
                expect(page.locator('.details-id')).to_have_text(research['id'][:8])
                page.screenshot(path=str(output/'research-desktop.png'),full_page=True)
                for width in (1440,390):
                    page.set_viewport_size(dict(width=width,height=1000))
                    assert page.evaluate('document.documentElement.scrollWidth')==width
                page.screenshot(path=str(output/'research-mobile.png'),full_page=True)
                page.set_viewport_size(dict(width=1440,height=1000))
                page.get_by_role('button',name='New task',exact=False).first.click()
            browser=submit(page,BROWSER,'browser')
        browser=wait(client,browser['id'],report,'awaiting_approval')
        with ui(session) as (page,_,errors):
            approval=page.get_by_role('region',name='Approval requests')
            expect(approval).to_contain_text('https://example.com')
            expect(approval).to_contain_text('https://www.python.org/about/')
            page.screenshot(path=str(output/'browser-approval.png'),full_page=True)
            page.get_by_role('button',name='Approve',exact=True).click()
        browser=wait(client,browser['id'],report)
        assert len(browser['browser_pages'])==2
        browser_files=downloads(client,browser,output)
        assert len(browser_files)==3
        log=json.loads((output/next(a['name'] for a in browser_files if a['format']=='json')).read_text(encoding='utf-8'))
        assert not log['live_interaction'] and len(log['pages'])==2
        report['tasks'].append(dict(id=browser['id'],kind='browser_readings',pages=browser['browser_pages'],downloads=browser_files))
        with ui(session) as (page,_,errors):
            page.get_by_role('button',name=BROWSER,exact=True).first.click()
            previews=page.get_by_role('region',name='Browser page previews');expect(previews).to_be_visible()
            previews.locator('summary').first.click()
            expect(previews.locator('img').first).to_be_visible()
            assert previews.locator('img').first.evaluate('(image)=>image.complete && image.naturalWidth>0')
            for width,label in ((1440,'desktop'),(390,'mobile')):
                page.set_viewport_size(dict(width=width,height=1000))
                assert page.evaluate('document.documentElement.scrollWidth')==width
                page.screenshot(path=str(output/('browser-'+label+'.png')),full_page=True)
            report['browser_errors']+=errors
        report['verified']=True
        session['task_ids']=([research['id']] if research else [])+[browser['id']];STATE.write_text(json.dumps(session),encoding='utf-8')
        (output/'acceptance-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(dict(verified=True,output=str(output),task_ids=session['task_ids'])),flush=True)

if __name__=='__main__':main()
