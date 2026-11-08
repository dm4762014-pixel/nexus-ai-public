"""Test the compiled schedule UI with a real worker and an isolated account.

Build with `npm.cmd run build -- --outDir ../tmp/schedules-dist` in frontend first.
Move the due time forward in the test database instead of waiting an hour.
"""
import csv
from datetime import datetime
import json
from pathlib import Path
import re
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
PROMPT = 'Create a seven-day CSV study timetable for Python and Linux.'


class NoInference:
    def health(self):
        return dict(reachable=False, installed=False)

    def complete(self, *_args, **_kwargs):
        raise AssertionError('The deterministic timetable should not require inference')


def verify(app, base_url, output):
    def make_due():
        with app.state.store.connect() as db:
            assert db.execute('UPDATE schedules SET next_run=?', (time.time() - 86400,)).rowcount == 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, accept_downloads=True, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base_url)
            page.get_by_label('Username').fill('schedule-qa')
            page.get_by_label('Password').fill(token_urlsafe(24))
            page.get_by_role('button', name='Create local account').click()
            scheduled = page.get_by_role('button', name='Scheduled tasks')
            scheduled.click()
            page.get_by_label('What should NEXUS do?').fill(PROMPT)
            page.get_by_role('button', name='Add schedule').click()
            expect(page.get_by_text('No recorded runs yet.')).to_be_visible()
            pause = page.get_by_role('button', name='Pause schedule', exact=True)
            resume = page.get_by_role('button', name='Resume schedule', exact=True)
            pause.click()
            expect(resume).to_be_enabled()
            make_due()
            page.reload()
            scheduled.click()
            expect(resume).to_be_enabled()
            expect(page.get_by_text('No recorded runs yet.')).to_be_visible()
            earliest = time.time() + 1440 * 60
            resume.click()
            expect(pause).to_be_enabled()
            schedule, = page.request.get(base_url + '/api/schedules').json()
            assert schedule['enabled'] == 1 and schedule['next_run'] >= earliest
            assert schedule['recent_runs'] == []
            make_due()
            completed = page.get_by_text('Recent runs (1) · Completed', exact=True)
            expect(completed).to_be_visible(timeout=25_000)
            completed.click()
            page.get_by_role('button', name='Open run', exact=True).click()
            with page.expect_download() as event:
                page.get_by_role('link', name=re.compile(r'\.csv\b', re.I)).click()
            path = output / 'seven-day-study-plan.csv'
            event.value.save_as(path)
            with path.open(encoding='utf-8-sig', newline='') as file:
                rows = list(csv.DictReader(file))
            assert len(rows) == 7 and {row['Subject'] for row in rows} == {'Python', 'Linux'}, rows
            assert sum(int(row['Minutes']) for row in rows) == 420

            scheduled.click()
            expect(completed).to_be_visible()
            make_due()
            skipped = page.get_by_text('Recent runs (2) · Skipped', exact=True)
            expect(skipped).to_be_visible(timeout=15_000)
            page.reload()
            scheduled.click()
            pause.click()
            expect(resume).to_be_enabled()
            skipped.click()
            expect(page.get_by_text('The daily task limit was reached.')).to_be_visible()
            expect(page.get_by_role('button', name='Open run', exact=True)).to_have_count(1)
            page.set_viewport_size({'width': 390, 'height': 900})
            expect(page.locator('#workspace-navigation')).to_have_attribute('aria-hidden', 'true')
            page.wait_for_function("document.querySelector('#workspace-navigation').getBoundingClientRect().right <= 0.5")
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=output / 'schedule-history.png', full_page=True, animations='disabled')
            assert not errors, errors

            response = page.request.get(base_url + '/api/schedules')
            assert response.ok
            runs = response.json()[0]['recent_runs']
            assert [run['status'] for run in runs] == ['skipped', 'completed']
            (output / 'acceptance-results.json').write_text(json.dumps({
                'verified': True, 'run_statuses': [run['status'] for run in runs],
                'pause_persisted_after_reload': True, 'resume_started_fresh_interval': True,
                'skip_reason': runs[0]['skip_reason'], 'download_rows': len(rows), 'study_minutes': 420,
                'browser_errors': errors, 'mobile_width': 390, 'model_calls': 0,
                'timing': 'Due timestamps adjusted in isolated QA database; real worker executed schedule.',
            }, indent=2), encoding='utf-8')
        finally:
            browser.close()


def main():
    frontend = ROOT / 'tmp' / 'schedules-dist'
    if not (frontend / 'index.html').is_file():
        raise SystemExit('Build frontend into tmp/schedules-dist first.')
    output = ROOT / 'outputs' / ('schedules-demo-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True)
    with TemporaryDirectory(prefix='nexus-schedule-qa-') as directory, socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        app = create_app(Settings(data_dir=Path(directory), frontend_dir=frontend, daily_tasks=1), NoInference())
        server = uvicorn.Server(uvicorn.Config(app, log_level='warning', proxy_headers=False))
        thread = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while thread.is_alive() and not server.started and time.monotonic() < deadline:
                time.sleep(.05)
            assert server.started, 'Isolated QA server did not start'
            verify(app, f'http://127.0.0.1:{listener.getsockname()[1]}', output)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), 'Isolated QA server did not stop'
    print(f'Scheduled run, real download, quota skip and mobile view verified: {output}')


if __name__ == '__main__':
    main()
