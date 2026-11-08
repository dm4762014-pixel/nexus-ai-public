import sqlite3
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nexus.security import password_hash
from nexus.store import Store, now


def create_schedule(signed):
    response = signed.post('/api/schedules', json={
        'prompt': 'Create a study timetable for Python and Linux.', 'interval_minutes': 15,
    })
    assert response.status_code == 201
    assert response.json()['recent_runs'] == []
    return response.json()['id']


def make_due(store, schedule_id):
    due = time.time() - 86400
    with store.connect() as db:
        db.execute('UPDATE schedules SET next_run=? WHERE id=?', (due, schedule_id))
    return due


def test_run_status_persists_and_history_retention_keeps_tasks(signed, app):
    store = app.state.store
    worker = app.state.worker
    owner = signed.get('/api/me').json()['id']
    schedule_id = create_schedule(signed)
    make_due(store, schedule_id)
    worker.tick_schedules()
    worker.tick_schedules()
    run, = signed.get('/api/schedules').json()[0]['recent_runs']
    task_id = run['task_id']
    assert run['status'] == 'queued'
    worker.run(owner, task_id)
    task = signed.get(f'/api/tasks/{task_id}').json()
    assert task['status'] == 'completed'
    assert Store(store.path).schedules(owner)[0]['recent_runs'][0]['status'] == 'completed'

    app.state.settings.queue_limit = 0
    for _ in range(6):
        make_due(store, schedule_id)
        worker.tick_schedules()
    recent = signed.get('/api/schedules').json()[0]['recent_runs']
    assert len(recent) == 5 and all(run['status'] == 'skipped' for run in recent)
    assert all(run['skip_reason'] == 'The task queue was full.' for run in recent)
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM schedule_runs').fetchone()[0] == 5
    assert signed.delete(f'/api/schedules/{schedule_id}').status_code == 200
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM schedule_runs').fetchone()[0] == 0
    assert signed.get(task['artifacts'][0]['url']).status_code == 200


def test_schedule_attempt_rolls_back_if_logging_fails(signed, app):
    store = app.state.store
    schedule_id = create_schedule(signed)
    due = make_due(store, schedule_id)
    with store.connect() as db:
        db.execute("CREATE TRIGGER fail_run BEFORE INSERT ON schedule_runs BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='test failure'):
        app.state.worker.tick_schedules()
    schedule, = signed.get('/api/schedules').json()
    assert schedule['next_run'] == due and schedule['recent_runs'] == []
    assert signed.get('/api/tasks').json() == []


def test_pause_stops_due_runs_and_resume_starts_one_fresh_interval(signed, app):
    store = app.state.store
    worker = app.state.worker
    schedule_id = create_schedule(signed)
    url = f'/api/schedules/{schedule_id}'
    make_due(store, schedule_id)
    worker.tick_schedules()
    previous, = signed.get('/api/tasks').json()

    assert signed.patch(url, json={'enabled': 'false'}).status_code == 422
    response = signed.patch(url, json={'enabled': False})
    assert response.status_code == 200 and response.json()['enabled'] == 0
    make_due(store, schedule_id)
    worker.tick_schedules()
    assert signed.get('/api/tasks').json() == [previous]
    owner = signed.get('/api/me').json()['id']
    paused, = Store(store.path).schedules(owner)
    assert paused['enabled'] == 0
    assert paused['recent_runs'][0]['task_id'] == previous['id']

    earliest = time.time() + 15 * 60
    resumed = signed.patch(url, json={'enabled': True}).json()
    assert resumed['enabled'] == 1
    assert earliest <= resumed['next_run'] <= time.time() + 15 * 60
    assert signed.patch(url, json={'enabled': True}).json() == resumed
    worker.tick_schedules()
    assert signed.get('/api/tasks').json() == [previous]
    make_due(store, schedule_id)
    worker.tick_schedules()
    assert len(signed.get('/api/tasks').json()) == 2


def test_schedule_runs_are_owner_scoped(signed, app):
    store = app.state.store
    schedule_id = create_schedule(signed)
    make_due(store, schedule_id)
    app.state.worker.tick_schedules()
    run, = signed.get('/api/schedules').json()[0]['recent_runs']
    with store.connect() as db:
        db.execute('INSERT INTO users VALUES(?,?,?,?)', (uuid4().hex, 'second', password_hash('second-test-password'), now()))
    other = TestClient(app)
    try:
        assert other.get('/api/schedules').status_code == 401
        assert other.post('/api/login', json={'username': 'second', 'password': 'second-test-password'}).status_code == 200
        assert other.get('/api/schedules').json() == []
        assert other.get(f"/api/tasks/{run['task_id']}").status_code == 404
        csrf = other.get('/api/me').json()['csrf']
        url = f'/api/schedules/{schedule_id}'
        assert other.patch(url, json={'enabled': False}).status_code == 403
        assert other.patch(url, json={'enabled': False}, headers={'X-CSRF-Token': csrf}).status_code == 404
        assert other.delete(f'/api/schedules/{schedule_id}', headers={'X-CSRF-Token': csrf}).status_code == 404
    finally:
        other.close()
