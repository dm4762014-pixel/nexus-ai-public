# NEXUS AI baseline audit

Audit date: 21 October 2026 (Asia/Kolkata). Repository: `D:\nexus-ai`.

## Preservation and inventory

Before source changes, all 22 original Python files were copied to `backups/20261021-212529`, with SHA256 source and original output manifests. Eleven existing user documents remain in `outputs`; no user files were deleted. Git was absent and has now been initialized. Backups, outputs, runtime data and secrets are excluded from Git.

The original application is a sequence of standalone FastAPI prototypes (`webapp`, v2, v3, v31, v4), duplicate backups, research v1/v31/v4, report helpers, two executable agent demonstrations, a model smoke script, and text-replacement upgrade scripts. There is no package definition, frontend project, SQLite database, deployment setup, or automated test suite. All original Python files parse and v4 imports successfully. Earlier dashboards differ primarily in added manual modes and duplicated inline HTML.

## Environment and verified baseline

Python 3.14.7 virtual environment works. FastAPI 0.157.0, HTTPX 0.28.1, Ollama 0.6.3, DDGS 9.16.0, openpyxl 3.1.5, python-docx 1.2.0, pypdf 6.21.1 and ReportLab 5.0.1 are installed. Node, npm, Git, Ollama, Docker CLI and WSL commands exist. Docker's Linux engine is not running; its CLI alone does not establish safe execution isolation. WSL reports Ubuntu version 2 but is not a configured coding sandbox.

Ollama responds on **127.0.0.1:11434** with qwen3:1.7b installed. Two other models exist on disk; they will not be used. Ports 8000–8004 are free at audit time; no old app processes need termination. Model inference and full workflows are tracked separately in TEST_RESULTS.md; a successful model listing is not inference proof.

## Working versus unverified

- Verified by inspection/runtime import: timetable workbook writer, DOCX/PDF parsers, functioning FastAPI routes and local model API connection. Existing user documents are present.
- Existing history reports successful inference, tool calling and document creation; these are historical reports until rerun.
- v4 research-to-PDF/Word is implemented, but no reproducible full regression suite exists. It needs a real integration run.
- No browser/coding execution, PPTX, uploads, natural-language combined routing, approvals, authentication, per-user ownership, history, scheduling or production frontend exists.

## Defects and vulnerabilities

1. Research checks DNS before HTTPX resolves again: DNS rebinding/time-of-check gap. Redirects are simply rejected; PDFs are rejected as non-HTML. Decoded streaming can allocate unexpectedly for compressed data. Retrieval errors are silently converted to empty strings.
2. Long tasks pass the API's 500-character limit but fail the research helper's 300-character maximum. Query stopword removal includes deliverable words and can lose useful subject terms.
3. Numeric citation validation only occurs for research_report. Empty/no-citation answers pass, and citation membership is not claim support or independent corroboration. Extracts contain little evidence; source dates and claim mappings are absent.
4. All download endpoints are unauthenticated. Random filenames are not authorization. All users share outputs, resources and execution state.
5. No authentication, CSRF controls, quotas, persistence, cancellation, restart recovery or task audit trail. Lock is process-local and only useful with one worker.
6. HTML is embedded repeatedly. v4's dropdown newline repair is already applied, but old branding/version text and misleading mode description remain. Output is safely rendered through textContent in the original page.
7. PDF renderer replaces Unicode characters with question marks. Verification checks only text length; report content is generic. Timetable functionality is specialized rather than a general spreadsheet agent.
8. Agent and diagnostic scripts execute inference at import. Upgrade scripts can overwrite later working source. They must remain archival, not production entry points.
9. Model context is 4096 for research rather than the requested initial 2048. Provider timeout, strict schemas and maximum workflow duration are absent.

## Corrections and implementation priorities

1. Preserve originals, establish Git, repair research and report helpers and test the legacy v4 seam.
2. Reuse the proven Python document stack in modular bounded tools. Add pinned public-IP HTTPS retrieval, PDF parsing, transparent errors and evidence provenance. Never label citation structure as factual verification.
3. Add a single production FastAPI entry point, SQLite owner-scoped tasks and sessions, one worker, strict planning/tool validation, cancellation/checkpoints and artifact verification.
4. Build the React/TypeScript production UI and test actual API interactions; serve compiled static assets from FastAPI.
5. Add bounded uploads, PPTX/CSV/JSON/TXT, restricted code packages, safe optional browser read workflows and permission decisions. Keep host shell execution disabled without strong isolation.
6. Add resource limits, integration tests, operational scripts and honest feature/deployment reports. Public access stays disabled until a separate readiness review.

This is the pre-change audit. Current implementation and observed tests belong in PROJECT_STATE.md and TEST_RESULTS.md; source existence is not a completed test.
