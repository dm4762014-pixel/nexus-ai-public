"""Owner-scoped SQLite persistence. Connections are short lived and thread safe."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import sqlite3
import time
from threading import RLock


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.file_lock = RLock()
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), prompt TEXT NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT, cancel INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(user_id,created_at);
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL, text TEXT NOT NULL, size INTEGER NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_id TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, status TEXT DEFAULT 'pending', created_at TEXT NOT NULL, decided_at TEXT);
            CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, prompt TEXT NOT NULL, interval_minutes INTEGER NOT NULL, next_run REAL NOT NULL, enabled INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS schedule_runs(
                id INTEGER PRIMARY KEY,
                schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
                task_id TEXT REFERENCES tasks(id),
                attempted_at TEXT NOT NULL,
                skip_reason TEXT,
                CHECK ((task_id IS NULL) != (skip_reason IS NULL))
            );
            CREATE INDEX IF NOT EXISTS schedule_runs_recent ON schedule_runs(schedule_id, id DESC);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, user_id TEXT, event TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def audit(self, user, event, detail=''):
        with self.connect() as db:
            db.execute('INSERT INTO audit(user_id,event,detail,at) VALUES(?,?,?,?)', (user, event, str(detail)[:2000], now()))

    def create_task(self, user, request):
        task_id = uuid4().hex
        payload = dict(plan=[], answer='', sources=[], claims=[], artifacts=[], events=[], warnings=[], error=None)
        with self.connect() as db:
            db.execute('INSERT INTO tasks(id,user_id,prompt,status,request,payload,created_at) VALUES(?,?,?,?,?,?,?)',
                       (task_id, user, request['prompt'], 'queued', json.dumps(request), json.dumps(payload), now()))
        return self.task(user, task_id)

    def task(self, user, task_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=? AND user_id=?', (task_id, user)).fetchone()
        if not row:
            return None
        data = dict(row)
        data.update(json.loads(data.pop('payload')))
        data['request'] = json.loads(data['request'])
        return data

    def tasks(self, user, query=''):
        with self.connect() as db:
            rows = db.execute('SELECT id,prompt,status,created_at,completed_at FROM tasks WHERE user_id=? AND instr(lower(prompt),lower(?))>0 ORDER BY created_at DESC LIMIT 200', (user, query[:200])).fetchall()
        return [dict(r) for r in rows]

    def update(self, user, task_id, **changes):
        # Called by the sole worker; cancel is an independent column, never overwritten.
        with self.connect() as db:
            row = db.execute('SELECT payload,cancel FROM tasks WHERE id=? AND user_id=?', (task_id, user)).fetchone()
            if not row:
                raise ValueError('Task missing')
            payload = json.loads(row['payload'])
            status = changes.pop('status', None)
            payload.update(changes)
            if status and row['cancel'] and status != 'cancelled':
                status = 'cancelled'
                payload['error'] = 'Cancellation requested; execution stopped at tool boundary'
                db.execute("UPDATE approvals SET status='cancelled',decided_at=? WHERE user_id=? AND task_id=? AND status='pending'", (now(), user, task_id))
            db.execute('UPDATE tasks SET payload=? WHERE id=? AND user_id=?', (json.dumps(payload, ensure_ascii=False), task_id, user))
            if status:
                terminal = status in ('completed', 'failed', 'cancelled')
                db.execute('UPDATE tasks SET status=?,completed_at=? WHERE id=? AND user_id=?', (status, now() if terminal else None, task_id, user))

    def event(self, user, task_id, tool, message):
        task = self.task(user, task_id)
        self.update(user, task_id, events=(task['events'] + [dict(tool=tool, message=str(message)[:2000], at=now())])[-100:])

    def recover(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,user_id FROM tasks WHERE status IN ('planning','running','awaiting_approval')").fetchall()
        for row in rows:
            self.update(row['user_id'], row['id'], status='failed', error='Interrupted by application restart. Review partial artifacts and retry explicitly; no tool was automatically replayed.')
        with self.connect() as db:
            db.execute("UPDATE approvals SET status='cancelled',decided_at=? WHERE status='pending' AND task_id IN (SELECT id FROM tasks WHERE status IN ('failed','cancelled','completed'))", (now(),))

    def add_artifact(self, user, task_id, item):
        artifact = dict(item, id=uuid4().hex, task_id=task_id)
        artifact['url'] = '/api/artifacts/' + artifact['id']
        with self.connect() as db:
            db.execute('INSERT INTO artifacts VALUES(?,?,?,?)', (artifact['id'], user, task_id, json.dumps(artifact)))
        return artifact

    def artifacts(self, user):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM artifacts WHERE user_id=? ORDER BY rowid DESC LIMIT 1000', (user,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def uploads(self, user):
        with self.connect() as db:
            rows = db.execute('SELECT id,name,size,created_at FROM uploads WHERE user_id=? ORDER BY created_at DESC', (user,)).fetchall()
        return [dict(r) for r in rows]

    def approval(self, user, task_id, action, detail):
        approval_id = uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO approvals(id,user_id,task_id,action,detail,created_at) VALUES(?,?,?,?,?,?)', (approval_id, user, task_id, action, detail, now()))
        return approval_id

    def schedules(self, user):
        with self.connect() as db:
            schedules = [dict(r) for r in db.execute('SELECT * FROM schedules WHERE user_id=? ORDER BY next_run', (user,))]
            for schedule in schedules:
                schedule['recent_runs'] = [dict(r) for r in db.execute('''
                    SELECT r.id, r.attempted_at, t.id AS task_id, t.completed_at,
                           COALESCE(t.status, 'skipped') AS status, r.skip_reason
                    FROM schedule_runs r
                    LEFT JOIN tasks t ON t.id=r.task_id AND t.user_id=?
                    WHERE r.schedule_id=? AND (r.task_id IS NULL OR t.id IS NOT NULL)
                    ORDER BY r.id DESC LIMIT 5
                ''', (user, schedule['id']))]
            return schedules
