"""Authenticated QA against an already running isolated QA server.

Session export is deliberately outside Git; no passwords or cookies enter reports.
Create the QA session through the actual UI before running this helper.
"""
from pathlib import Path
from threading import Event, Thread
import argparse
import json
import time
import httpx
import psutil

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8005')
    parser.add_argument('--session', default=str(ROOT / 'tmp/qa-session.json'))
    parser.add_argument('--task-id')
    parser.add_argument('--checks', action='store_true')
    args = parser.parse_args()
    session = json.loads(Path(args.session).read_text())
    client = httpx.Client(base_url=args.base_url, cookies={x['name']: x['value'] for x in session['cookies']}, headers={'X-CSRF-Token': session['csrf']}, timeout=15)
    assert client.get('/api/me').status_code == 200
    report = dict(tasks=[], resources=dict(min_available_bytes=psutil.virtual_memory().available, max_backend_rss=0, max_ollama_process_rss=0, max_reported_model_bytes=0, max_loaded_models=0))
    stopped = Event()

    def monitor():
        while not stopped.is_set():
            report['resources']['min_available_bytes'] = min(report['resources']['min_available_bytes'], psutil.virtual_memory().available)
            backend_rss, ollama_rss = 0, 0
            for process in psutil.process_iter(['name', 'cmdline', 'memory_info']):
                try:
                    name = process.info['name'].lower()
                    if 'ollama' in name or 'llama' in name:
                        ollama_rss += process.info['memory_info'].rss
                    if name.startswith('python') and 'uvicorn' in ' '.join(process.info['cmdline'] or []):
                        backend_rss += process.info['memory_info'].rss
                except (psutil.Error, AttributeError):
                    continue
            report['resources']['max_backend_rss'] = max(report['resources']['max_backend_rss'], backend_rss)
            report['resources']['max_ollama_process_rss'] = max(report['resources']['max_ollama_process_rss'], ollama_rss)
            try:
                with httpx.Client(trust_env=False, timeout=2) as local:
                    models = local.get('http://127.0.0.1:11434/api/ps').json()['models']
                    loaded = len(models)
                    report['resources']['max_reported_model_bytes'] = max(report['resources']['max_reported_model_bytes'], sum(m.get('size', 0) for m in models))
                report['resources']['max_loaded_models'] = max(report['resources']['max_loaded_models'], loaded)
            except Exception:
                pass
            stopped.wait(1)

    monitor_thread = Thread(target=monitor, daemon=True)
    monitor_thread.start()

    def wait(task_id):
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            response = client.get('/api/tasks/' + task_id)
            response.raise_for_status()
            task = response.json()
            if task['status'] not in ('queued', 'planning', 'running'):
                return task
            time.sleep(1)
        raise TimeoutError('QA polling deadline')

    def record(task):
        entry = {k: task.get(k) for k in ('id', 'prompt', 'status', 'warnings', 'error', 'created_at', 'completed_at')}
        entry['answer'] = task.get('answer', '')
        entry['downloads'] = []
        for artifact in task.get('artifacts', []):
            response = client.get(artifact['url'])
            entry['downloads'].append(dict(name=artifact['name'], format=artifact['format'], bytes=len(response.content), status=response.status_code, verified=artifact['verified']))
            assert response.status_code == 200
        report['tasks'].append(entry)
        print(json.dumps(dict(task_id=task['id'], status=task['status'], files=[d['format'] for d in entry['downloads']], warnings=task.get('warnings', []), error=task.get('error'))), flush=True)
        return task

    def create(prompt, **kwargs):
        response = client.post('/api/tasks', json=dict(prompt=prompt, **kwargs))
        response.raise_for_status()
        return wait(response.json()['id'])

    try:
        if args.task_id:
            task = record(wait(args.task_id))
            (ROOT / 'tmp/final-demo-result.json').write_text(json.dumps(task, indent=2), encoding='utf-8')
        if args.checks:
            record(create('Create a seven-day Excel study timetable for Python, Linux, Networking, and Cybersecurity.'))
            upload = client.post('/api/uploads', files={'file': ('engineering-notes.txt', b'Engineering notes: The local assistant uses SQLite task history. Only one local model task runs at a time. Generated files must be reopened and verified. The team reviewed cancellation and approval races.', 'text/plain')})
            upload.raise_for_status()
            record(create('Summarize the uploaded engineering notes in a Word document.', upload_ids=[upload.json()['id']]))
            record(create('Generate Python code with a function add(a, b) returning the sum and a unittest source file. Include README. Package as ZIP.', mode='code'))
            browser = create('Visit https://example.com and create a read-only screenshot.', mode='browser')
            assert browser['status'] == 'awaiting_approval', browser
            pending = next(a for a in client.get('/api/approvals').json() if a['task_id'] == browser['id'] and a['status'] == 'pending')
            response = client.post('/api/approvals/' + pending['id'], json=dict(approved=True))
            response.raise_for_status()
            record(wait(browser['id']))
    finally:
        stopped.set()
        monitor_thread.join(timeout=4)
        (ROOT / 'tmp/integration-api-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'resources': report['resources']}), flush=True)
        client.close()


if __name__ == '__main__':
    main()
