"""Submit the acceptance demonstration through the real compiled frontend.

Uses an already-created isolated QA session; never creates a production login.
"""
from pathlib import Path
import json
import re
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
session = json.loads((root / 'tmp/qa-session.json').read_text())
prompt = re.search(r"const DEMO = '([^']+)'", (root / 'frontend/src/App.tsx').read_text(encoding='utf-8')).group(1)
errors = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(viewport=dict(width=1440, height=1000))
        context.add_cookies(session['cookies'])
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8005', wait_until='networkidle')
        page.get_by_label('Your task', exact=True).fill(prompt)
        with page.expect_response(lambda response: response.url.endswith('/api/tasks') and response.request.method == 'POST') as created:
            page.get_by_role('button', name='Start task', exact=True).click()
        response = created.value
        task = response.json()
        assert response.status == 202, task
        (root / 'tmp/demo-task-id.txt').write_text(task['id'])
        print(json.dumps(dict(accepted=True, task_id=task['id'], errors=errors)))
    finally:
        browser.close()
