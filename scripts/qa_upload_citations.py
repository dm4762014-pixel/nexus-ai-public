"""Verify a real upload and citation navigation in the compiled UI without Ollama."""
from datetime import datetime
import json
from pathlib import Path
from secrets import token_urlsafe
import socket
from tempfile import TemporaryDirectory
from threading import Thread
import time

from playwright.sync_api import expect, sync_playwright
import uvicorn

from nexus.app import create_app
from nexus.config import Settings

ROOT = Path(__file__).resolve().parent.parent
PROMPT = 'Summarize the uploaded pilot notes using only the uploaded evidence.'
SOURCE = '''Budget
The pilot budget is 9,000 rupees for books and 3,000 rupees for signs. The committee must approve any change before money is spent. The treasurer will record actual spending in the receipts ledger. Volunteers should list donated materials separately so that estimates are not confused with actual payments.

Handover
The final handover is 14 December. The coordinator will return the storage keys to the hall committee. The committee will receive the borrowing register and a list of remaining stock. Two volunteers will check that all receipts are filed. The handover date is a target until the hall committee confirms its availability.

Review
The committee will ask participants whether opening hours were convenient. Feedback is voluntary and does not establish whether the pilot improved reading outcomes. The final report must distinguish what people said from measured outcomes. No names will appear in the feedback summary shared with the committee.'''


class OfflineProvider:
    def health(self):
        return {'reachable': False, 'installed': False}


def verify(url, output):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)
            page.get_by_label('Username').fill('citations-qa')
            page.get_by_label('Password').fill(token_urlsafe(24))
            page.get_by_role('button', name='Create local account').click()
            with page.expect_response(lambda r: r.url.endswith('/api/uploads') and r.request.method == 'POST') as uploaded:
                page.locator('input[type=file]').set_input_files({'name': 'Pilot.txt', 'mimeType': 'text/plain', 'buffer': SOURCE.encode()})
            assert uploaded.value.status == 201
            expect(page.get_by_role('button', name='Remove Pilot.txt')).to_be_visible()
            page.get_by_label('Your task').fill(PROMPT)
            with page.expect_response(lambda r: r.url.endswith('/api/tasks') and r.request.method == 'POST') as submitted:
                page.get_by_role('button', name='Start task', exact=True).click()
            assert submitted.value.status == 202
            task_id = submitted.value.json()['id']
            second = page.get_by_role('button', name='Uploaded evidence U2: Pilot.txt', exact=True)
            expect(second).to_be_visible(timeout=20_000)
            expect(page.locator('.assistant-heading .status-badge')).to_have_text('completed')
            response = page.request.get(f'{url}/api/tasks/{task_id}')
            assert response.ok
            task = response.json()
            assert task['status'] == 'completed'
            findings = {finding['reference']: finding for finding in task['upload_findings']}
            assert {'U1', 'U2'} <= findings.keys()
            for ref, keyboard in [('U1', False), ('U2', True)]:
                panel = page.locator('details.upload-evidence')
                assert not panel.evaluate('(element) => element.open')
                trigger = page.get_by_role('button', name=f'Uploaded evidence {ref}: Pilot.txt', exact=True)
                if keyboard:
                    page.set_viewport_size({'width': 390, 'height': 900})
                    expect(page.locator('#workspace-navigation')).to_have_attribute('aria-hidden', 'true')
                    trigger.focus()
                    page.keyboard.press('Enter')
                else:
                    trigger.click()
                passage = page.get_by_role('group', name=f'[{ref}] Pilot.txt', exact=True)
                expect(passage).to_be_focused()
                expect(passage).to_be_in_viewport()
                assert passage.locator('blockquote').text_content() == findings[ref]['quote']
                assert SOURCE[findings[ref]['start']:findings[ref]['end']] == findings[ref]['quote']
                if keyboard:
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=output / 'mobile-citation.png', animations='disabled')
                else:
                    panel.locator('summary').click()
            assert not errors, errors
            (output / 'acceptance-results.json').write_text(json.dumps({
                'verified': True, 'mouse_reference': 'U1', 'keyboard_reference': 'U2',
                'quote_matches_saved_evidence': True, 'mobile_width': 390,
                'browser_errors': errors, 'model_calls': 0,
            }, indent=2), encoding='utf-8')
        finally:
            browser.close()


def main():
    frontend = ROOT / 'frontend' / 'dist'
    if not (frontend / 'index.html').is_file():
        raise SystemExit('Build the frontend first: npm.cmd run build')
    output = ROOT / 'outputs' / ('upload-citations-demo-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True)
    with TemporaryDirectory(prefix='nexus-citations-qa-') as directory, socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        app = create_app(Settings(data_dir=Path(directory), frontend_dir=frontend), OfflineProvider())
        server = uvicorn.Server(uvicorn.Config(app, log_level='warning', proxy_headers=False))
        thread = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while thread.is_alive() and not server.started and time.monotonic() < deadline:
                time.sleep(.05)
            assert server.started, 'Isolated QA server did not start'
            verify(f'http://127.0.0.1:{listener.getsockname()[1]}', output)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), 'Isolated QA server did not stop'
    print(f'Upload citations verified with mouse and keyboard: {output}')


if __name__ == '__main__':
    main()
