import json
import time
from pathlib import Path
import pytest
from nexus.provider import OllamaProvider
from nexus.config import Settings
from nexus.schemas import TaskRequest
from nexus.worker import Cancelled


def test_cancel_during_tool_stops_before_artifact(signed, app):
    owner = signed.get('/api/me').json()['id']
    task = signed.post('/api/tasks', json={'prompt': 'Create PDF about engineering'}).json()
    def cancel_provider(*args, **kwargs):
        with app.state.store.connect() as db:
            db.execute('UPDATE tasks SET cancel=1 WHERE id=?', (task['id'],))
        return 'This content was computed while a user cancellation was being requested.'
    app.state.worker.provider.complete = cancel_provider
    app.state.worker.run(owner, task['id'])
    result = app.state.store.task(owner, task['id'])
    assert result['status'] == 'cancelled'
    assert result['artifacts'] == []


def test_runtime_limit_at_boundary(signed, app):
    owner = signed.get('/api/me').json()['id']
    task = signed.post('/api/tasks', json={'prompt': 'Create PDF about engineering'}).json()
    app.state.settings.task_timeout = -1
    app.state.worker.run(owner, task['id'])
    result = app.state.store.task(owner, task['id'])
    assert result['status'] == 'failed'
    assert 'runtime limit' in result['error']


def test_queue_quota_is_enforced(signed, app):
    app.state.settings.queue_limit = 2
    assert signed.post('/api/tasks', json={'prompt': 'Create a PDF'}).status_code == 202
    assert signed.post('/api/tasks', json={'prompt': 'Create another PDF'}).status_code == 202
    assert signed.post('/api/tasks', json={'prompt': 'Create third PDF'}).status_code == 429


def test_browser_disabled_is_honest(signed, app):
    owner = signed.get('/api/me').json()['id']
    app.state.settings.browser_enabled = False
    task = signed.post('/api/tasks', json={'prompt': 'Visit https://example.com', 'mode': 'browser'}).json()
    app.state.worker.run(owner, task['id'])
    result = app.state.store.task(owner, task['id'])
    assert result['status'] == 'failed' and 'disabled' in result['error']


def test_nonlocal_setup_rejected(app):
    from fastapi.testclient import TestClient
    with TestClient(app, client=('203.0.113.1', 50000)) as remote:
        response = remote.post('/api/setup', json={'username': 'remote', 'password': 'remote-long-password'})
    assert response.status_code == 403


def test_provider_context_and_timeout_limits(tmp_path):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, context_size=100000)
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, model_timeout=99999)


def test_integrations_require_connection():
    from nexus.connectors import ConnectorRegistry
    with pytest.raises(PermissionError):
        ConnectorRegistry().get('email', 'user')
