import pytest
from fastapi.testclient import TestClient
from nexus.app import create_app
from nexus.config import Settings


class FakeProvider:
    def complete(self, system, prompt, tokens=500):
        return 'Summary of supplied inputs\nThis is a deterministic test response, not a real model call. The supplied data describes a local task with actual generated files and parser verification.'

    def select_plan(self, prompt):
        raise ValueError('No tool selected')

    def health(self):
        return dict(reachable=True, installed=True)


@pytest.fixture
def app(tmp_path, monkeypatch):
    import psutil
    from types import SimpleNamespace
    # Deterministic unit tests must not depend on unrelated desktop RAM usage.
    # Real integration QA separately records actual system memory.
    monkeypatch.setattr(psutil, 'virtual_memory', lambda: SimpleNamespace(available=2 * 1024**3))
    return create_app(Settings(data_dir=tmp_path, browser_enabled=True, allowed_hosts=['localhost', '127.0.0.1', 'testserver']), FakeProvider(), start_worker=False)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def signed(client):
    response = client.post('/api/setup', json=dict(username='testuser', password='test-only-long-password'))
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf']
    return client
