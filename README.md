# NEXUS AI

Give it a goal. Let AI do the work.

A local FastAPI + React work assistant continued from the original NEXUS v4 prototype. It uses Ollama `qwen3:1.7b`, a single background task worker, SQLite history and real file tools. Core software needs no paid API key. This is a local MVP, not a certified public multi-tenant service.

## Start on this Windows laptop

The existing virtual environment and compiled frontend are ready. In PowerShell:

```powershell
cd D:\nexus-ai
.\start.ps1
```

Open http://127.0.0.1:8000 and create your own first local account (password at least 12 characters). There are no shipped credentials. Ollama must be running with `qwen3:1.7b`. For a fresh checkout run `.\setup.ps1 -Development` once. See [SETUP_WINDOWS.md](SETUP_WINDOWS.md).

## What works

- Goal routing into sequential research, document, upload-summary, approved multi-page browser readings and code-package workflows.
- Attach a document and ask for a briefing: up to nine findings draw from passages across the retained text. Select a citation such as **[U2]** to jump to its original passage and extracted line numbers, or open **Check uploaded evidence** to review all passages. Ask for a brief summary for three findings. The same task can create PDF, Word, PowerPoint and Excel files; Excel retains the selected exact passages and locations.
- Passages that explicitly limit outcome or verification claims keep their original statements and qualifications. Failed rewrites prefer complete source sentences over cut-off excerpts. Review AI summaries against the expandable evidence; source membership does not prove their meaning is correct.
- Real HTTPS search/retrieval with bounded HTML/PDF extraction, pinned public IP sockets and source provenance. Cybersecurity-agent research produces concise application summaries, source coverage and preview/corroboration qualifications. Invalid model synthesis falls back to clearly labeled source excerpts.
- PDF, Word, Excel, PowerPoint, CSV, TXT and JSON generation; parser reopening, expected-text checks and SHA256 verification. Code projects become inspected ZIP packages.
- Local accounts, salted scrypt passwords, expiring HttpOnly sessions, CSRF tokens, owner-scoped history/uploads/downloads, quotas and audit records.
- Progress, cancellation at tool boundaries, explicit retry, approval for optional browser snapshots, restart recovery and basic recurring tasks while the application is running.
- In **Scheduled tasks**, expand **Recent runs** to see the last five attempts, open their results and downloads, or see why an attempt was skipped. Removing a schedule keeps its tasks and files in the workspace.
- Use **Pause schedule** to stop future runs without interrupting tasks already queued or running. **Resume schedule** starts a fresh interval and keeps past results.
- Explicit follow-ups to completed tasks: retain bounded prior context, ask another question, or create a document without repeating the facts. Parent links and context-shortening notices remain visible.
- Production React assets served by FastAPI; no Node server needed at runtime.

Optional browser tooling reads up to **three explicitly approved public HTTPS pages**, producing semantic offline snapshots, PNG previews and a verified JSON journey log through temporary Chromium with JavaScript/network disabled. It does not interact with live forms. Coding tools **never execute generated code** on Windows. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and [SECURITY.md](SECURITY.md).

## Example

“Research the real-world applications of AI Agents in cybersecurity. Compare reliable sources. Prepare a professional PDF report, a Word document, a PowerPoint presentation, and an Excel summary table. Include source references and give me all downloadable files.”

The workflow retrieves evidence once, prepares a cited comparison or explicit excerpt fallback, writes four artifacts and retains the plan/results. Excel includes application, summary, source comparison and references columns. Multiple sources do not automatically establish independent corroboration. Review claims against linked source evidence.

## Follow-up tasks

To continue a result, open it from history and click **Follow up**. Ask a question or request a file such as “Turn this into a short PDF action plan.” The composer shows which task supplies context. Remove that context to start independently. Follow-ups use up to three linked prior results (2,400 text characters), inherit source links without fetching pages again, and support answers/documents. Start a new task for fresh web research, browsing or code generation. Long results may be shortened; the full original stays available through **View previous task**.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd test -- --run
npm.cmd run build
```

Real integration tests are opt-in: `$env:NEXUS_LIVE_TESTS='1'` then `.\.venv\Scripts\python.exe -m pytest tests/test_live.py -q`. They need the internet, Ollama and optional installed Chromium. Mocked tests do not prove live connectivity. Actual observations are recorded in [TEST_RESULTS.md](TEST_RESULTS.md).

## Files and operation

`main.py` is the single production entry point. Original v1/v2/v3/v31 files remain for preservation. `webapp_v4.py` is a repaired legacy local dashboard; it remains unauthenticated and must never be served remotely. Original outputs remain untouched. New protected user files and SQLite state live under ignored `data/`.

Documentation: [audit](PROJECT_AUDIT.md), [architecture](ARCHITECTURE.md), [current status](PROJECT_STATE.md), [deployment](DEPLOYMENT.md), [user actions](USER_ACTIONS_REQUIRED.md).

The original prompt has been mapped section by section in [REQUIREMENTS_STATUS.md](REQUIREMENTS_STATUS.md). General research now uses compact source perspectives with exact passage attribution; PowerPoint comparisons can include editable cited overview diagrams. See the latest live and deterministic results in [TEST_RESULTS.md](TEST_RESULTS.md).

The workflow stays simple: enter a task and download the results. Reports now include more source-linked detail (up to nine findings when supported), larger readable result text and practical cybersecurity review questions. Ask for a brief report to keep the output short. More detail can take longer on this8GB laptop; source-linked AI drafts still need review.
