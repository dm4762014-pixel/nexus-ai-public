# Windows setup and troubleshooting

## This checkout

Python 3.14.7, Node, Git, Ollama, the virtual environment and qwen3:1.7b were found. Existing user outputs are preserved and ignored by Git. There is no need to reinstall Ollama or download another model.

```powershell
cd D:\nexus-ai
.\setup.ps1 -Development
.\start.ps1
```

The setup script installs pinned runtime/test packages and runs `npm ci` and a production build. Node is needed only during builds. If PowerShell policy prevents running a local script, inspect it first, then use `powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1` for that process. Do not change machine-wide execution policy.

Open http://127.0.0.1:8000 and create your owner account. There are no default passwords. Additional independent accounts can be created locally:

```powershell
.\.venv\Scripts\python.exe -m nexus.manage add-user
.\.venv\Scripts\python.exe -m nexus.manage reset-password --username YOUR_USERNAME
```

Passwords are prompted without echo and are never passed on the command line. Reset invalidates existing sessions. These commands have local file access equivalent to the account running them; they are not remotely exposed administration endpoints.

## Optional settings

Copy `.env.example` to `.env` and edit documented values. `start.ps1` loads `NEXUS_` values as literal environment values; direct Uvicorn runs inherit shell environment only. Keep 2048 context and one worker on this 8GB laptop. The tuned defaults are `NEXUS_MODEL_THREADS=4` (allowed 1–8), `NEXUS_MODEL_BATCH=64` (16–256), and a 120-second total model deadline (10–180). Structured research uses a 220-token output budget. Streaming progress appears in execution history; the model unloads before file rendering. Monitor actual memory in Settings and task history; Windows and other applications still share RAM.

Optional browser snapshot support:

```powershell
.\setup.ps1 -Browser
```

Set `NEXUS_BROWSER=1` in `.env`, restart, submit a public HTTPS URL and approve the read-only snapshot request. This installs an optional Chromium download. Live forms and arbitrary code execution remain disabled. Docker CLI exists on this laptop but its engine was unavailable during verification; no coding sandbox has been assumed.

## Troubleshooting

| Symptom | Action |
|---|---|
| Port in use | Use the already running window or `.\start.ps1 -Port 8005`; do not kill unrelated processes. |
| Another server owns data directory | Stop the previous server with Ctrl+C. The OS lease releases when its worker stops/process exits; do not delete the lock to bypass it. |
| Model unavailable | Ensure Ollama is running, use `ollama list`, and verify `qwen3:1.7b`. Model listening must remain loopback. |
| Task takes a long time | Check memory/CPU, close unnecessary programs, keep one local model and 2048 context. Cancellation waits for blocking tools to return. |
| No research sources | Review retrieval failures; search may be blocked, offline or rate limited. Retry later or upload a permitted source. Do not bypass CAPTCHAs/paywalls. |
| Excerpt fallback | The small model returned invalid evidence JSON or timed out. Real retrieved excerpts are labeled; they are not a synthesized comparison. |
| PDF unsupported character | Use DOCX, or install a legally licensed system font supporting that script. No third-party font files are bundled. Complex script shaping is limited. |
| Upload rejected | Use supported signatures, UTF-8 for text, at most 5MB, no encryption/macros/embedded objects. Scans require unavailable OCR. |
| Session/CSRF error | Reload and sign in. Remote HTTPS requires secure cookie and exact allowed host configuration. |
| Storage quota | Run `python -m nexus.manage storage`; back up and review owner data manually. No user artifacts are automatically deleted. |

## Backups and retention

Stop the server before copying `data/` for a consistent backup. Also preserve `outputs/` and `backups/` outside Git as private files. Avoid synchronizing live SQLite WAL files without a database-aware backup. Retention is indefinite until the owner explicitly reviews/removes files while the service is stopped. Reconcile metadata when manually removing artifacts; missing files return 404. No automatic cleanup job runs.
