from pathlib import Path
from uuid import uuid4
import json
import time
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from nexus.app import InstanceLease
from nexus.planner import plan_task
from nexus.schemas import Plan, TaskRequest
from nexus.security import password_check, password_hash
from nexus.store import Store, now


def test_password_salts():
    one, two = password_hash('some-long-password'), password_hash('some-long-password')
    assert one != two
    assert password_check('some-long-password', one)
    assert not password_check('incorrect', one)


def test_auth_and_csrf(client, signed):
    assert signed.get('/api/me').json()['username'] == 'testuser'
    assert signed.post('/api/setup', json=dict(username='other', password='long-enough-password')).status_code == 409
    csrf = signed.headers.pop('X-CSRF-Token')
    assert signed.post('/api/tasks', json={'prompt': 'Create PDF'}).status_code == 403
    signed.headers['X-CSRF-Token'] = csrf
    assert signed.post('/api/tasks', json={'prompt': 'Create PDF'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert signed.post('/api/logout').status_code == 200
    assert signed.get('/api/tasks').status_code == 401
    assert signed.post('/api/login', json=dict(username='testuser', password='wrong-password')).status_code == 401
    assert signed.post('/api/login', json=dict(username='testuser', password='test-only-long-password')).status_code == 200


def test_schema_and_combined_routing():
    prompt = 'Research the real-world applications of AI Agents in cybersecurity. Compare reliable sources. Prepare a professional PDF report, a Word document, a PowerPoint presentation, and an Excel summary table. Include source references and give me all downloadable files.'
    plan = plan_task(TaskRequest(prompt=prompt))
    assert plan.research and not plan.code
    assert set(plan.formats) == {'pdf', 'docx', 'pptx', 'xlsx'}
    with pytest.raises(ValidationError):
        TaskRequest(prompt='some task', shell='format C:')
    with pytest.raises(ValidationError):
        Plan(formats=['exe'])
    with pytest.raises(ValueError):
        plan_task(TaskRequest(prompt='Visit a page', mode='browser'))


def test_model_tool_arguments_are_validated():
    from nexus.provider import OllamaProvider
    from nexus.config import Settings
    provider = OllamaProvider.__new__(OllamaProvider)
    provider._chat = lambda *args: {'tool_calls': [{'function': {'name': 'shell', 'arguments': {'cmd': 'bad'}}}]}
    with pytest.raises(ValueError, match='permitted tool'):
        provider.select_plan('do a task')
    provider._chat = lambda *args: {'tool_calls': [{'function': {'name': 'plan_task', 'arguments': {'formats': ['exe']}}}]}
    with pytest.raises(ValidationError):
        provider.select_plan('do a task')


def test_create_persist_and_cancel(signed, app):
    created = signed.post('/api/tasks', json={'prompt': 'Create a PDF about cloud computing'})
    assert created.status_code == 202
    task = created.json()
    assert task['status'] == 'queued'
    assert signed.get('/api/tasks?q=cloud').json()[0]['id'] == task['id']
    assert signed.post('/api/tasks/' + task['id'] + '/cancel').json()['status'] == 'cancelled'
    assert signed.post('/api/tasks/' + task['id'] + '/retry').status_code == 202
    persisted = Store(app.state.store.path)
    assert persisted.task(signed.get('/api/me').json()['id'], task['id'])['status'] == 'cancelled'


def test_multistep_with_mocked_research(signed, app, monkeypatch):
    import nexus.research
    source = dict(number=1, title='Test Evidence', url='https://example.com/evidence', text='Cybersecurity agents can triage alerts and assist investigations based on reported evidence. ' * 4)
    monkeypatch.setattr(nexus.research, 'research_web', lambda *a, **k: dict(answer='Agents assist cybersecurity alert triage [1].', sources=[source], claims=[], warnings=['Mock research; not live retrieval.'], failures=[]))
    created = signed.post('/api/tasks', json={'prompt': 'Research cybersecurity and create PDF, Word, Excel, PowerPoint files'}).json()
    user = signed.get('/api/me').json()['id']
    app.state.worker.run(user, created['id'])
    task = signed.get('/api/tasks/' + created['id']).json()
    assert task['status'] == 'completed', task
    assert {a['format'] for a in task['artifacts']} == {'pdf', 'docx', 'xlsx', 'pptx'}
    assert all(s['status'] == 'completed' for s in task['plan'])
    for artifact in task['artifacts']:
        response = signed.get(artifact['url'])
        assert response.status_code == 200 and response.content
        assert 'attachment' in response.headers['content-disposition']


def test_upload_summary_and_validation(signed, app):
    response = signed.post('/api/uploads', files={'file': ('notes.txt', b'Quarterly engineering notes: improve reliability and finish the local assistant. ' * 4, 'text/plain')})
    assert response.status_code == 201, response.text
    upload_id = response.json()['id']
    task = signed.post('/api/tasks', json=dict(prompt='Summarize the uploaded evidence in a Word document', upload_ids=[upload_id])).json()
    app.state.worker.run(signed.get('/api/me').json()['id'], task['id'])
    result = signed.get('/api/tasks/' + task['id']).json()
    assert result['status'] == 'completed', result
    assert not result['sources']
    assert any('Uploaded content' in warning for warning in result['warnings'])
    assert signed.post('/api/uploads', files={'file': ('bad.exe', b'not a document')}).status_code == 415
    assert signed.post('/api/uploads', files={'file': ('bad.pdf', b'not a pdf')}).status_code == 422


def test_user_isolation_download_and_path(signed, app):
    task = signed.post('/api/tasks', json=dict(prompt='Create a PDF about local software')).json()
    owner = signed.get('/api/me').json()['id']
    app.state.worker.run(owner, task['id'])
    task = signed.get('/api/tasks/' + task['id']).json()
    assert task['status'] == 'completed', task
    other_id = uuid4().hex
    with app.state.store.connect() as db:
        db.execute('INSERT INTO users VALUES(?,?,?,?)', (other_id, 'second', password_hash('second-user-password'), now()))
    other = TestClient(app, raise_server_exceptions=False)
    assert other.post('/api/login', json=dict(username='second', password='second-user-password')).status_code == 200
    assert other.get('/api/tasks/' + task['id']).status_code == 404
    assert other.get(task['artifacts'][0]['url']).status_code == 404
    assert other.get('/api/artifacts').json() == []
    other.close()
    assert signed.get('/api/artifacts/../../.env').status_code in (404, 307)
    item = app.state.store.artifacts(owner)[0]
    Path(item['path']).write_bytes(b'tampered')
    assert signed.get(item['url']).status_code == 409


def test_restart_and_lease(signed, app, tmp_path):
    task = signed.post('/api/tasks', json=dict(prompt='Research something')).json()
    owner = signed.get('/api/me').json()['id']
    app.state.store.update(owner, task['id'], status='running', answer='Partial output')
    app.state.store.recover()
    result = app.state.store.task(owner, task['id'])
    assert result['status'] == 'failed'
    assert 'restart' in result['error']
    assert result['answer'] == 'Partial output'
    one = InstanceLease(tmp_path / 'lock')
    try:
        with pytest.raises(RuntimeError, match='Another NEXUS'):
            InstanceLease(tmp_path / 'lock')
    finally:
        one.close()


def test_browser_approval_and_denial(signed, app):
    task = signed.post('/api/tasks', json=dict(prompt='Visit https://example.com and take a screenshot', mode='browser')).json()
    owner = signed.get('/api/me').json()['id']
    app.state.worker.run(owner, task['id'])
    assert signed.get('/api/tasks/' + task['id']).json()['status'] == 'awaiting_approval'
    approval = signed.get('/api/approvals').json()[0]
    response = signed.post('/api/approvals/' + approval['id'], json={'approved': False})
    assert response.json()['status'] == 'cancelled'
    assert signed.post('/api/approvals/' + approval['id'], json={'approved': True}).status_code == 404


def test_approved_browser_executes_only_snapshot(signed, app, monkeypatch):
    import nexus.browser
    seen = []
    def snapshot(url, directory, checkpoint):
        checkpoint()
        seen.append(url)
        raise RuntimeError('Test stops before real Chromium')
    monkeypatch.setattr(nexus.browser, 'browser_snapshot', snapshot)
    task = signed.post('/api/tasks', json=dict(prompt='Visit https://example.com', mode='browser')).json()
    owner = signed.get('/api/me').json()['id']
    app.state.worker.run(owner, task['id'])
    approval = signed.get('/api/approvals').json()[0]
    assert signed.post('/api/approvals/' + approval['id'], json={'approved': True}).json()['status'] == 'queued'
    app.state.worker.run(owner, task['id'])
    assert seen == ['https://example.com']
    assert signed.get('/api/tasks/' + task['id']).json()['status'] == 'failed'


def test_offline_research_fails_honestly(signed, app, monkeypatch):
    import nexus.research
    monkeypatch.setattr(nexus.research, 'research_web', lambda *a, **k: dict(answer='Search offline', sources=[], warnings=['Provider unavailable']))
    task = signed.post('/api/tasks', json=dict(prompt='Research cybersecurity and create PDF')).json()
    app.state.worker.run(signed.get('/api/me').json()['id'], task['id'])
    result = signed.get('/api/tasks/' + task['id']).json()
    assert result['status'] == 'failed'
    assert not result['artifacts']
    assert 'No readable' in result['error']


def test_sensitive_operations_disabled(signed, app):
    task = signed.post('/api/tasks', json=dict(prompt='Send an email message to someone')).json()
    app.state.worker.run(signed.get('/api/me').json()['id'], task['id'])
    result = signed.get('/api/tasks/' + task['id']).json()
    assert result['status'] == 'failed'
    assert 'not enabled' in result['error']


def test_scheduling_no_catchup_and_delete(signed, app):
    schedule = signed.post('/api/schedules', json=dict(prompt='Create PDF research summary', interval_minutes=15)).json()
    assert schedule['enabled']
    with app.state.store.connect() as db:
        db.execute('UPDATE schedules SET next_run=?', (time.time() - 86400,))
    app.state.worker.tick_schedules()
    app.state.worker.tick_schedules()
    assert len(signed.get('/api/tasks').json()) == 1
    assert signed.delete('/api/schedules/' + schedule['id']).status_code == 200
    assert not signed.get('/api/schedules').json()
    assert signed.post('/api/schedules', json=dict(prompt='Frequent task', interval_minutes=1)).status_code == 422


def test_invalid_requests_and_headers(signed):
    assert signed.post('/api/tasks', json={'prompt': 'x', 'mode': 'shell'}).status_code == 422
    assert signed.post('/api/tasks', json={'prompt': 'x' * 4001}).status_code == 422
    response = signed.get('/api/health')
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert "object-src 'none'" in response.headers['content-security-policy']
    assert signed.get('/api/health', headers={'host': 'evil.example'}).status_code == 400
    assert signed.post('/api/tasks', content=b'x' * 5_500_001).status_code == 413
