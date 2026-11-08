"""Regression cases found by the independent platform security review."""
import time

from nexus.schemas import Plan
from nexus.store import now


def owner_id(signed):
    return signed.get('/api/me').json()['id']


def test_scheduled_tasks_obey_owner_disk_quota(signed, app):
    user = owner_id(signed)
    settings = app.state.settings
    settings.max_user_bytes = 10
    directory = settings.data_dir / user
    directory.mkdir(exist_ok=True)
    (directory / 'existing-user-file.txt').write_bytes(b'X' * 11)
    created = signed.post('/api/schedules', json={'prompt': 'Create a study timetable for Python', 'interval_minutes': 15})
    assert created.status_code == 201
    with app.state.store.connect() as db:
        db.execute('UPDATE schedules SET next_run=? WHERE id=?', (time.time() - 1, created.json()['id']))
    app.state.worker.tick_schedules()
    assert signed.get('/api/tasks').json() == []
    run, = signed.get('/api/schedules').json()[0]['recent_runs']
    assert run['status'] == 'skipped' and run['task_id'] is None
    assert run['skip_reason'] == 'The workspace storage limit was reached.'


def test_restart_resolves_stale_approval_cards(signed, app):
    user = owner_id(signed)
    task = signed.post('/api/tasks', json={'prompt': 'Read https://example.com', 'mode': 'browser'}).json()
    app.state.worker.run(user, task['id'])
    assert signed.get('/api/approvals').json()[0]['status'] == 'pending'
    app.state.store.recover()
    assert signed.get('/api/tasks/' + task['id']).json()['status'] == 'failed'
    assert all(a['status'] != 'pending' for a in signed.get('/api/approvals').json())


def test_exact_maximum_planned_steps_can_execute(signed, app):
    app.state.settings.max_steps = 2  # compose + verify
    task = signed.post('/api/tasks', json={'prompt': 'Explain local network concepts', 'mode': 'chat'}).json()
    app.state.worker.run(owner_id(signed), task['id'])
    result = signed.get('/api/tasks/' + task['id']).json()
    assert result['status'] == 'completed', result.get('error')


def test_browser_approval_binds_exact_destination(signed, app, monkeypatch):
    import nexus.browser
    selected, visited = [], []
    first = 'https://first.example/page'
    second = 'https://second.example/page'
    def select_plan(prompt):
        selected.append(prompt)
        return Plan(browser_url=first if len(selected) == 1 else second)
    app.state.worker.provider.select_plan = select_plan
    def browser_snapshot(url, *args):
        visited.append(url)
        raise RuntimeError('Browser should await approval of the exact destination')
    monkeypatch.setattr(nexus.browser, 'browser_snapshot', browser_snapshot)
    # No deterministic route; local function calling selects one supplied URL.
    task = signed.post('/api/tasks', json={'prompt': f'Read evidence at {first} and {second}'}).json()
    user = owner_id(signed)
    app.state.worker.run(user, task['id'])
    approval = signed.get('/api/approvals').json()[0]
    assert first in approval['detail']
    assert signed.post('/api/approvals/' + approval['id'], json={'approved': True}).status_code == 200
    app.state.worker.run(user, task['id'])
    assert second not in visited


def test_cancel_during_approval_creation_cannot_restore_active_status(signed, app, monkeypatch):
    task = signed.post('/api/tasks', json={'prompt': 'Read https://example.com', 'mode': 'browser'}).json()
    user = owner_id(signed)
    original_approval = app.state.store.approval
    def approval_then_cancel(*args, **kwargs):
        result = original_approval(*args, **kwargs)
        # Reproduce the API cancellation arriving between approval insertion
        # and the worker's transition into awaiting_approval.
        response = signed.post('/api/tasks/' + task['id'] + '/cancel')
        assert response.status_code == 200
        return result
    monkeypatch.setattr(app.state.store, 'approval', approval_then_cancel)
    app.state.worker.run(user, task['id'])
    assert signed.get('/api/tasks/' + task['id']).json()['status'] == 'cancelled'
