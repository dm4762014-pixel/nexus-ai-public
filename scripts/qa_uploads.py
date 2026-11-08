"""Compiled UI upload -> real local model -> four authenticated file downloads.

Run scripts.qa_uploads_server first. Synthetic credentials remain in ignored tmp.
The browser closes during inference to reduce shared laptop memory pressure.
"""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import secrets
import time
import zipfile
import httpx
import psutil
from playwright.sync_api import expect
from openpyxl import load_workbook
from pptx import Presentation
from nexus.files import extract_upload
from scripts.qa_followups import ui
from scripts.qa_features import downloads, wait

ROOT = Path(__file__).resolve().parent.parent
BASE = 'http://127.0.0.1:8005'
STATE = ROOT/'tmp/uploads-qa-session.json'
PROMPT = 'Orion pilot briefing. Summarize the attached community library pilot, including scope, staffing, costs, risks, milestones and final handover. Create a PDF report, Word document, PowerPoint presentation and Excel summary table. Use only the uploaded evidence.'
SOURCE = '''Orion community library pilot
Purpose and scope
The Orion pilot will open a small lending library in the community hall. The pilot serves residents who can walk to the hall and focuses on school reading and adult literacy. It does not offer home delivery. The team will collect feedback before considering a permanent service. Borrowing is free during the pilot, while the hall committee continues to control the room booking.

Collection and borrowing
The opening collection contains 240 donated books. The catalogue records the title, author, shelf location and condition of each book. Readers may borrow two books for a fortnight. Reference dictionaries stay in the room. Volunteers record loans on paper during the pilot so that readers do not need a phone or online account. Damaged books are set aside for review rather than returned immediately to the shelves.

Staffing and training
Mara coordinates volunteers and chairs the weekly review. Dev manages the book catalogue. Lina handles room access and the opening checklist. Each session requires two volunteers. A volunteer may cancel a shift by contacting Mara before the previous evening. The first training session covers the lending register, emergency contacts and respectful support for readers who need help filling out the borrowing form.

Opening hours and access
The library opens on Tuesday and Saturday afternoons. The hall entrance has a ramp, but the narrow internal doorway still needs an access check before launch. Lina will arrange that check with the hall committee. Notices will be printed in large type. The team will keep a quiet reading corner separate from the lending desk and leave the entrance clear during busy sessions.

Budget and purchasing
The pilot spending ceiling is 18000 rupees. Shelving has an allocation of 9000 rupees, stationery 3000 rupees, signage 2000 rupees and contingency 4000 rupees. Mara must approve any use of contingency funds before a purchase. These are spending allocations rather than actual payments. The team will retain receipts and compare actual costs with the allocations during each weekly review. Donated books are not assigned a resale value.

Privacy and safeguarding
The borrowing register contains a reader name and contact number. Volunteers must not photograph the register or publish reader names. Only Mara and the volunteer on duty may access it. The register stays in a locked cabinet when the library is closed. Guardian contact details are required for children. The pilot has no online registration form, public reader directory or automated marketing messages.

Risks and responses
The main operational risk is an uncovered volunteer shift. Mara will maintain a reserve list, and a session will close if the minimum staffing cannot be met. A roof leak is a separate facilities risk: affected books must be moved away from the leak and the hall committee notified. These responses are planned procedures; the pilot has not yet measured whether they reduce disruption.

Milestones and launch decision
Catalogue completion is planned for 12 November. Volunteer training is planned for 16 November. The target opening is 20 November, conditional on the access check and enough trained volunteers. The hall committee makes the launch decision. These dates are internal targets and do not establish that any work has already been completed. If the access check is late, the opening will be rescheduled rather than the condition waived.

Evaluation and review
The weekly review records attendance, loans, returned books, volunteer coverage and reader feedback. Attendance counts visits rather than unique residents. The pilot has no numerical success threshold yet. The team will discuss suitable thresholds after the first two sessions. A high loan count alone will not establish that adult literacy has improved; any statement about learning outcomes would require a separate evaluation.

Incident reporting
Volunteers record a facilities incident in the room log after making the area safe. The entry includes the time, affected area and person contacted. The hall committee receives the report. A complaint about a borrowing decision goes to Mara rather than into the public notice board. The pilot does not publish incident details on social media. The team will use the review meeting to decide whether a procedure needs changing.

Public communication
The launch notice will describe opening hours, the location of the lending desk and the free borrowing arrangement. It will also say that home delivery is unavailable. Lina checks the wording with the hall committee before the notice is displayed. The pilot will use the hall notice board and printed leaflets. No volunteer should announce an extension of the service before the committee has made that decision.

Room closure
The last volunteer checks that the reading corner is clear, the register is locked away and windows are closed. Returned books waiting for inspection stay on a separate shelf. The volunteer signs the room log and returns the keys to Lina. A missing key must be reported promptly to the hall committee. This checklist describes the planned closing procedure and is not evidence that a session has already run.

Final handover
The closing review will list outstanding loans, remaining funds and decisions that need hall committee approval. Dev will check the catalogue against the shelves. Lina will return the room keys. Mara must sign the final handover on 14 December before the hall committee decides whether to extend the service.
'''


def main():
    output = ROOT/'outputs'/('upload-briefing-demo-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    source_path = output/'Orion-Pilot-Source.txt'
    source_path.write_text(SOURCE, encoding='utf-8')
    report = dict(minimum_available_bytes=psutil.virtual_memory().available, tasks=[], browser_errors=[])
    with ui() as (page, context, errors):
        if page.get_by_role('button', name='Create local account', exact=True).count():
            username='uploads-'+secrets.token_hex(4); password=secrets.token_urlsafe(24)
            page.get_by_label('Username', exact=True).fill(username)
            page.get_by_label('Password', exact=True).fill(password)
            page.get_by_role('button', name='Create local account', exact=True).click()
        else:
            saved=json.loads(STATE.read_text());username=saved['username'];password=saved['password']
            page.get_by_label('Username', exact=True).fill(username)
            page.get_by_label('Password', exact=True).fill(password)
            page.get_by_role('button', name='Sign in', exact=True).click()
        page.get_by_label('Your task', exact=True).wait_for()
        with page.expect_response(lambda r: r.url.endswith('/api/uploads') and r.request.method=='POST') as uploaded:
            page.locator('input[type=file]').set_input_files(source_path)
        assert uploaded.value.status==201, uploaded.value.text()
        expect(page.get_by_role('button', name='Remove Orion-Pilot-Source.txt', exact=True)).to_be_visible()
        page.get_by_label('Task mode', exact=True).select_option('auto')
        page.get_by_label('Your task', exact=True).fill(PROMPT)
        profile=context.request.get(BASE+'/api/me').json()
        session=dict(username=username,password=password,cookies=context.cookies(),csrf=profile['csrf'],output=str(output))
        STATE.write_text(json.dumps(session), encoding='utf-8')
        with page.expect_response(lambda r:r.url.endswith('/api/tasks') and r.request.method=='POST') as created:
            page.get_by_role('button', name='Start task', exact=True).click()
        assert created.value.status==202,created.value.text()
        task_id=created.value.json()['id']
    with httpx.Client(base_url=BASE,trust_env=False,cookies={c['name']:c['value'] for c in session['cookies']},headers={'X-CSRF-Token':session['csrf']},timeout=20) as client:
        start=time.monotonic()
        task=wait(client,task_id,report)
        findings=task['upload_findings']
        assert len(findings)==9,findings
        assert sum(finding['mode'] in ('summary','source_sentence') for finding in findings)>=6,task['warnings']
        assert any(finding['mode']=='summary' for finding in findings),'No real AI summary completed'
        assert all(finding['mode']!='extract' for finding in findings),'A truncated excerpt remains in the fixture briefing'
        # Check the exact extracted text, not the source file's trailing whitespace.
        extracted=extract_upload(source_path)
        assert extracted.index('14 December') > 4500
        for finding in findings:
            assert extracted[finding['start']:finding['end']]==finding['quote']
        assert any('14 December' in finding['quote'] for finding in findings),'Final handover evidence was lost'
        assert '14 December' in task['answer'],'The final handover deadline was omitted from the briefing'
        assert 'ensures safety' not in task['answer'] and 'to minimize disruption' not in task['answer']
        assert any('Risks and responses' == finding['heading'] for finding in findings),'Requested risk coverage was lost'
        assert any(value in task['answer'] for value in ('9000','9,000','18000','18,000')),'Concrete cost information was lost'
        assert len(task['sources'])==0,'Uploaded evidence must not become invented web sources'
        assert {item['format'] for item in task['artifacts']}=={'pdf','docx','xlsx','pptx'}
        files=downloads(client,task,output)
        for artifact in task['artifacts']:
            path=output/artifact['name']; text=extract_upload(path)
            assert 'Source coverage' in text and 'Orion-Pilot-Source.txt' in text
            if artifact['format']=='xlsx':
                workbook=load_workbook(path)
                assert workbook.active.max_row==10
                assert any(finding['quote']==workbook.active.cell(row,3).value for row in range(2,11) for finding in findings)
            if artifact['format']=='pptx':assert len(Presentation(path).slides)>=6
        assert httpx.get(BASE+task['artifacts'][0]['url'],trust_env=False).status_code==401
        with ui(session) as (page,_,errors):
            page.get_by_role('button',name=PROMPT,exact=True).first.click()
            evidence=page.locator('details.upload-evidence')
            expect(evidence).to_contain_text('9 findings')
            evidence.locator('summary').click()
            expect(evidence).to_contain_text('14 December')
            assert evidence.locator('blockquote').count()==9
            for width,label in ((1440,'desktop'),(390,'mobile')):
                page.set_viewport_size(dict(width=width,height=1000))
                assert page.evaluate('document.documentElement.scrollWidth')==width
                page.screenshot(path=str(output/('briefing-'+label+'.png')),full_page=True)
            report['browser_errors']+=errors
        report.update(verified=True, elapsed_seconds=round(time.monotonic()-start,2), task_id=task_id,
                      answer=task['answer'], findings=findings, coverage=task['upload_coverage'],
                      model_metrics=task.get('upload_model_metrics'),warnings=task['warnings'],downloads=files,
                      summary_count=sum(finding['mode']=='summary' for finding in findings),
                      source_sentence_count=sum(finding['mode']=='source_sentence' for finding in findings),
                      source_sha256=sha256(source_path.read_bytes()).hexdigest(),
                      evidence_validation='Exact passage membership and file integrity; not independent semantic verification')
        (output/'acceptance-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        with zipfile.ZipFile(output/'NEXUS-Upload-Briefing-Demo.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for path in output.iterdir():
                if path.is_file() and path.suffix!='.zip':archive.write(path,path.name)
        session['task_id']=task_id;STATE.write_text(json.dumps(session),encoding='utf-8')
        print(json.dumps(dict(verified=True,task_id=task_id,output=str(output),summaries=report['summary_count'],findings=len(findings),seconds=report['elapsed_seconds'])),flush=True)

if __name__=='__main__': main()
