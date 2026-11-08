from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import hmac
import json
import os
import secrets
import sqlite3
import time

from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .schemas import Credentials, TaskRequest, ScheduleRequest, ScheduleState, Decision
from .security import RateLimit, password_hash, password_check, token_hash
from .store import Store, now
from .provider import OllamaProvider
from .worker import Worker
from .context import capture_context, MAX_TURNS, MAX_TEXT


class InstanceLease:
    """An OS lock prevents a second server using the same SQLite task worker."""
    def __init__(self, path):
        self.file = open(path, 'a+b')
        try:
            self.file.seek(0)
            if self.file.read(1) == b'':
                self.file.write(b'0')
                self.file.flush()
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('Another NEXUS server already owns this data directory. Use one Uvicorn worker.')

    def close(self):
        self.file.close()


def create_app(settings=None, provider=None, start_worker=True):
    settings = settings or Settings()
    store = Store(settings.data_dir / 'nexus.sqlite3')
    provider = provider or OllamaProvider(settings)
    worker = Worker(store, settings, provider)
    rate = RateLimit()

    @asynccontextmanager
    async def lifespan(app):
        lease = InstanceLease(settings.data_dir / '.worker.lock')
        app.state.lease = lease
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()
            if not worker.thread or not worker.thread.is_alive():
                lease.close()

    app = FastAPI(title='NEXUS AI', version='0.6.0', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.worker, app.state.settings = store, worker, settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = request.headers.get('origin')
            expected = str(request.base_url).rstrip('/')
            if origin and origin.rstrip('/') != expected:
                return JSONResponse({'detail': 'Cross-origin request rejected'}, status_code=403)
            # Check actual streamed size, including requests without Content-Length.
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > settings.max_upload + 500_000:
                    return JSONResponse({'detail': 'Request body exceeds upload limit'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers.update({
            'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
            'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
        })
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def setup_required():
        with store.connect() as db:
            return not db.execute('SELECT 1 FROM users LIMIT 1').fetchone()

    def auth(request: Request):
        token = request.cookies.get('nexus_session', '')
        with store.connect() as db:
            session = db.execute('SELECT s.*,u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=? AND expires>?', (token_hash(token), time.time())).fetchone()
        if not session:
            raise HTTPException(401, 'Sign in to continue')
        if not rate.allow('api:' + session['user_id'], 240):
            raise HTTPException(429, 'Too many requests; wait a minute')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
                raise HTTPException(403, 'Invalid CSRF token; reload and sign in again')
        return dict(session)

    def issue_session(user, username):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with store.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token_hash(token), user, csrf, time.time() + 43200))
        response = JSONResponse(dict(id=user, username=username, csrf=csrf))
        response.set_cookie('nexus_session', token, max_age=43200, httponly=True, secure=settings.secure_cookies, samesite='strict', path='/')
        return response

    @app.get('/api/health')
    def health():
        return dict(status='ok', setup_required=setup_required())

    @app.post('/api/setup')
    def setup(body: Credentials, request: Request):
        # Setup is only available on the loopback deployment. Do it before configuring remote access.
        if request.url.hostname not in ('127.0.0.1', 'localhost', 'testserver') or (request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient')):
            raise HTTPException(403, 'Create the owner account locally before remote access')
        if not rate.allow('setup:' + (request.client.host if request.client else 'local'), 5, 600):
            raise HTTPException(429, 'Too many setup attempts')
        user = uuid4().hex
        encoded = password_hash(body.password)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise HTTPException(409, 'Setup already completed; sign in')
            db.execute('INSERT INTO users VALUES(?,?,?,?)', (user, body.username, encoded, now()))
        store.audit(user, 'owner_created')
        return issue_session(user, body.username)

    @app.post('/api/login')
    def login(body: Credentials, request: Request):
        address = request.client.host if request.client else 'local'
        if not rate.allow('login:' + address, 8, 600):
            raise HTTPException(429, 'Too many sign-in attempts; wait ten minutes')
        with store.connect() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (body.username,)).fetchone()
        # Run a real KDF even for an unknown username to reduce account timing differences.
        encoded = row['password'] if row else password_hash('invalid-account-password')
        valid = password_check(body.password, encoded)
        if not row or not valid:
            store.audit(None, 'login_failed')
            raise HTTPException(401, 'Invalid username or password')
        store.audit(row['id'], 'login')
        return issue_session(row['id'], row['username'])

    @app.get('/api/me')
    def me(user=Depends(auth)):
        return dict(id=user['user_id'], username=user['username'], csrf=user['csrf'])

    @app.post('/api/logout')
    def logout(request: Request, user=Depends(auth)):
        with store.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (user['token'],))
        response = JSONResponse({'ok': True})
        response.delete_cookie('nexus_session', path='/')
        return response

    @app.get('/api/capabilities')
    def capabilities(user=Depends(auth)):
        import psutil
        return dict(model=settings.model, context_size=settings.context_size, browser_enabled=settings.browser_enabled,
                    followup_context=dict(max_turns=MAX_TURNS, max_text_characters=MAX_TEXT),
                    browser_mode='up to three approved public pages; offline snapshots and journey log; no forms', code_execution=False,
                    formats=['pdf', 'docx', 'xlsx', 'pptx', 'csv', 'txt', 'json', 'zip'],
                    limits=dict(active_tasks=1, max_steps=settings.max_steps, upload_bytes=settings.max_upload,
                                task_seconds=settings.task_timeout, daily_tasks=settings.daily_tasks,
                                backend_rss_bytes=psutil.Process().memory_info().rss,
                                available_memory_bytes=psutil.virtual_memory().available),
                    ollama=provider.health() if hasattr(provider, 'health') else dict(reachable=None, installed=None))

    def task_or_404(user_id, task_id):
        task = store.task(user_id, task_id)
        if not task:
            raise HTTPException(404, 'Task not found')
        return public_task(task)

    def public_task(task):
        task = dict(task)
        task.pop('user_id', None)
        task.pop('cancel', None)
        task['artifacts'] = [{k: v for k, v in a.items() if k not in ('path',)} for a in task.get('artifacts', [])]
        return task

    def enqueue(body, user_id):
        with store.connect() as db:
            # Atomic quota check and task creation protects concurrent clients.
            db.execute('BEGIN IMMEDIATE')
            pending = db.execute("SELECT count(*) FROM tasks WHERE status IN ('queued','planning','running','awaiting_approval')").fetchone()[0]
            daily = db.execute('SELECT count(*) FROM tasks WHERE user_id=? AND created_at>=?', (user_id, now()[:10])).fetchone()[0]
            for upload_id in body.upload_ids:
                if not db.execute('SELECT 1 FROM uploads WHERE id=? AND user_id=?', (upload_id, user_id)).fetchone():
                    raise HTTPException(404, 'Upload not found')
            context = None
            if body.parent_task_id:
                try:
                    context = capture_context(db, user_id, body.parent_task_id)
                except LookupError as exc:
                    raise HTTPException(404, str(exc)) from exc
                except ValueError as exc:
                    raise HTTPException(409, str(exc)) from exc
            if pending >= settings.queue_limit or daily >= settings.daily_tasks:
                raise HTTPException(429, 'Task queue or daily quota reached')
            if disk_usage(user_id) >= settings.max_user_bytes:
                raise HTTPException(429, 'User storage quota reached')
            task_id = uuid4().hex
            payload = dict(plan=[], answer='', sources=[], claims=[], artifacts=[], events=[], warnings=[], error=None)
            if context:
                payload['context'] = context
            db.execute('INSERT INTO tasks(id,user_id,prompt,status,request,payload,created_at) VALUES(?,?,?,?,?,?,?)', (task_id, user_id, body.prompt, 'queued', body.model_dump_json(), json.dumps(payload), now()))
        store.audit(user_id, 'task_queued', task_id)
        return task_or_404(user_id, task_id)

    def disk_usage(user_id):
        path = settings.data_dir / user_id
        return sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.exists() else 0

    @app.get('/api/tasks')
    def tasks(q: str = '', user=Depends(auth)):
        return store.tasks(user['user_id'], q)

    @app.post('/api/tasks', status_code=202)
    def create_task(body: TaskRequest, user=Depends(auth)):
        return enqueue(body, user['user_id'])

    @app.get('/api/tasks/{task_id}')
    def task(task_id: str, user=Depends(auth)):
        return task_or_404(user['user_id'], task_id)

    @app.post('/api/tasks/{task_id}/cancel')
    def cancel(task_id: str, user=Depends(auth)):
        task = task_or_404(user['user_id'], task_id)
        with store.connect() as db:
            db.execute('UPDATE tasks SET cancel=1 WHERE id=? AND user_id=?', (task_id, user['user_id']))
            db.execute("UPDATE approvals SET status='cancelled',decided_at=? WHERE task_id=? AND user_id=? AND status='pending'", (now(), task_id, user['user_id']))
        if task['status'] in ('queued', 'awaiting_approval'):
            store.update(user['user_id'], task_id, status='cancelled', error='Cancelled before execution')
        return task_or_404(user['user_id'], task_id)

    @app.post('/api/tasks/{task_id}/retry', status_code=202)
    def retry(task_id: str, user=Depends(auth)):
        task = task_or_404(user['user_id'], task_id)
        if task['status'] not in ('failed', 'cancelled'):
            raise HTTPException(409, 'Only failed or cancelled tasks can be retried')
        return enqueue(TaskRequest.model_validate(task['request']), user['user_id'])

    @app.get('/api/artifacts')
    def artifacts(user=Depends(auth)):
        return [{k: v for k, v in a.items() if k != 'path'} for a in store.artifacts(user['user_id'])]

    @app.get('/api/artifacts/{artifact_id}')
    def download(artifact_id: str, user=Depends(auth)):
        with store.connect() as db:
            row = db.execute('SELECT payload FROM artifacts WHERE id=? AND user_id=?', (artifact_id, user['user_id'])).fetchone()
        if not row:
            raise HTTPException(404, 'File not found')
        item = json.loads(row[0])
        path = Path(item['path']).resolve()
        task_root = (settings.data_dir / user['user_id'] / item['task_id']).resolve()
        if not path.is_relative_to(task_root) or not path.is_file():
            raise HTTPException(404, 'Artifact missing or invalid path')
        from hashlib import sha256
        if path.stat().st_size != item['size'] or sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise HTTPException(409, 'Artifact changed since verification')
        return FileResponse(path, filename=item['name'], content_disposition_type='attachment')

    @app.post('/api/uploads', status_code=201)
    async def upload(file: UploadFile = File(...), user=Depends(auth)):
        from .files import extract_upload
        if not rate.allow('upload:' + user['user_id'], 15, 3600):
            raise HTTPException(429, 'Upload rate limit reached')
        original = file.filename or ''
        suffix = Path(original).suffix.lower()
        if suffix not in ('.txt', '.csv', '.json', '.pdf', '.docx', '.xlsx', '.pptx'):
            raise HTTPException(415, 'Supported uploads: TXT CSV JSON PDF DOCX XLSX PPTX')
        content = await file.read(settings.max_upload + 1)
        await file.close()
        if not content or len(content) > settings.max_upload:
            raise HTTPException(413, 'Upload is empty or exceeds 5 MB')
        upload_id = uuid4().hex
        directory = settings.data_dir / user['user_id'] / 'uploads'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (upload_id + suffix)
        def save_extract():
            with store.file_lock:
                if disk_usage(user['user_id']) + len(content) > settings.max_user_bytes:
                    raise ValueError('User storage quota reached')
                path.write_bytes(content)
                return extract_upload(path)
        try:
            # Parse off the async event loop. Inputs are bounded by the file agent.
            from starlette.concurrency import run_in_threadpool
            text = await run_in_threadpool(save_extract)
        except Exception as exc:
            path.unlink(missing_ok=True)  # Only the just-created rejected upload.
            raise HTTPException(422, 'Upload rejected: ' + str(exc)[:250]) from exc
        name = original.replace('\\', '/').split('/')[-1][:150]
        with store.connect() as db:
            # The parser already enforces the 100,000-character extraction cap.
            # Retain all accepted text so later sections remain available.
            db.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?,?)', (upload_id, user['user_id'], name, str(path), text, len(content), now()))
        store.audit(user['user_id'], 'upload_created', upload_id)
        return dict(id=upload_id, name=name, text_preview=text[:500])

    @app.get('/api/uploads')
    def uploads(user=Depends(auth)):
        return store.uploads(user['user_id'])

    @app.get('/api/approvals')
    def approvals(user=Depends(auth)):
        with store.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM approvals WHERE user_id=? ORDER BY created_at DESC LIMIT 100', (user['user_id'],))]

    @app.post('/api/approvals/{approval_id}')
    def decide(approval_id: str, body: Decision, user=Depends(auth)):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM approvals WHERE id=? AND user_id=? AND status='pending'", (approval_id, user['user_id'])).fetchone()
            if not row:
                raise HTTPException(404, 'Pending approval not found')
            task = db.execute('SELECT status,cancel FROM tasks WHERE id=?', (row['task_id'],)).fetchone()
            if not task or task['status'] != 'awaiting_approval' or task['cancel']:
                raise HTTPException(409, 'Task no longer awaits approval')
            status = 'approved' if body.approved else 'denied'
            db.execute('UPDATE approvals SET status=?,decided_at=? WHERE id=?', (status, now(), approval_id))
            db.execute('UPDATE tasks SET status=? WHERE id=?', ('queued' if body.approved else 'cancelled', row['task_id']))
        if not body.approved:
            store.update(user['user_id'], row['task_id'], status='cancelled', error='Permission denied by user')
        store.audit(user['user_id'], 'approval_' + status, approval_id)
        return task_or_404(user['user_id'], row['task_id'])

    @app.get('/api/schedules')
    def schedules(user=Depends(auth)):
        return store.schedules(user['user_id'])

    @app.post('/api/schedules', status_code=201)
    def create_schedule(body: ScheduleRequest, user=Depends(auth)):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM schedules WHERE user_id=?', (user['user_id'],)).fetchone()[0] >= 10:
                raise HTTPException(429, 'Schedule limit reached')
            schedule_id = uuid4().hex
            db.execute('INSERT INTO schedules VALUES(?,?,?,?,?,?)', (schedule_id, user['user_id'], body.prompt, body.interval_minutes, time.time() + body.interval_minutes * 60, 1))
        store.audit(user['user_id'], 'schedule_created', schedule_id)
        return next(s for s in store.schedules(user['user_id']) if s['id'] == schedule_id)

    @app.patch('/api/schedules/{schedule_id}')
    def set_schedule_state(schedule_id: str, body: ScheduleState, user=Depends(auth)):
        owner = user['user_id']
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            schedule = db.execute('SELECT enabled,next_run,interval_minutes FROM schedules WHERE id=? AND user_id=?',
                                  (schedule_id, owner)).fetchone()
            if not schedule:
                raise HTTPException(404, 'Schedule not found')
            next_run = schedule['next_run']
            if bool(schedule['enabled']) != body.enabled:
                if body.enabled:
                    next_run = time.time() + schedule['interval_minutes'] * 60
                db.execute('UPDATE schedules SET enabled=?,next_run=? WHERE id=? AND user_id=?',
                           (int(body.enabled), next_run, schedule_id, owner))
                db.execute('INSERT INTO audit(user_id,event,detail,at) VALUES(?,?,?,?)',
                           (owner, 'schedule_resumed' if body.enabled else 'schedule_paused', schedule_id, now()))
        return {'enabled': int(body.enabled), 'next_run': next_run}

    @app.delete('/api/schedules/{schedule_id}')
    def delete_schedule(schedule_id: str, user=Depends(auth)):
        with store.connect() as db:
            if db.execute('DELETE FROM schedules WHERE id=? AND user_id=?', (schedule_id, user['user_id'])).rowcount != 1:
                raise HTTPException(404, 'Schedule not found')
        store.audit(user['user_id'], 'schedule_deleted', schedule_id)
        return {'ok': True}

    if (settings.frontend_dir / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=settings.frontend_dir / 'assets'), name='assets')

    @app.get('/favicon.svg')
    def favicon():
        path = settings.frontend_dir / 'favicon.svg'
        if not path.is_file():
            raise HTTPException(404, 'Icon not found')
        return FileResponse(path)

    @app.get('/')
    def index():
        path = settings.frontend_dir / 'index.html'
        if not path.is_file():
            return JSONResponse({'detail': 'Frontend not built. Run setup.ps1, then start.ps1.'}, status_code=503)
        return FileResponse(path, headers={'Cache-Control': 'no-cache'})

    return app
