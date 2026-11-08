# NEXUS AI current project state

Updated 22 October 2026, Asia/Kolkata. The secured local MVP runs through `main:app`. Live browser forms, sandboxed code execution, external OAuth connectors and reviewed public deployment remain outstanding.

## Preserved baseline

All 22 original Python files are backed up in `backups/20261021-212529`, with SHA256 manifests. All 11 original user outputs remain byte-identical. Git baseline is `8d3e0fa`; previous MVP milestone is `27abd6d`. Existing prototypes, earlier demo outputs and the owner's production account/history are retained.

## Current implementation

- FastAPI backend and compiled React/TypeScript/Vite frontend; SQLite history, one worker, cancellation, retry, schedules and restart recovery.
- Owner-scoped accounts, scrypt passwords, expiring sessions, CSRF/origin/host checks, protected uploads/downloads, quotas and approvals.
- Explicit follow-up tasks for answers and documents. The user chooses a completed parent; the server captures up to three linked prior results within 2,400 text characters, checks every ancestor's owner, and retains an immutable context snapshot. Context, parent navigation, removal and shortening notices are visible in the UI. Source links are inherited without new retrieval; previous tools are never replayed.
- Local Ollama `qwen3:1.7b`, 2048 context, streaming progress, a total inference deadline and bounded output. Defaults now use four CPU threads and batch 64. Complete JSON stops without waiting for trailing whitespace. Cancellation is checked between streamed frames and while waiting for the inference lock.
- Cybersecurity-agent research selects concrete defensive workflows and generates short summaries. Python owns application-to-evidence mappings, citations, source coverage and preview/corroboration qualifications. Offensive agents, generic IAM definitions and security-of-agent passages are excluded from defensive application selection. General topics now use fixed Python-owned source groups and compact schema-constrained paraphrases, with exact provenance and explicit excerpt fallback for invalid output.
- PDF/DOCX/XLSX/PPTX/CSV/TXT/JSON and upload parsers. Excel comparison columns are Application/Aspect, Summary, Source comparison and References. PowerPoint can add2–3 cited aspects as native editable shapes/connectors while retaining full findings and notes. Models unload before file rendering and optional Chromium snapshots.
- Code source ZIPs receive AST/compile/static-reference checks. Generated code is not executed. Browser support reads up to three explicit approved public pages with escaped semantic blocks, screenshots, a JSON journey log and authenticated previews; JavaScript and network remain disabled inside Chromium.

## Simple workflow and fuller results

The task-and-download controls are unchanged. General reports now support up to nine distinct source-linked findings, short requests retain a smaller result, and optional-detail failures preserve individually accepted findings. Cybersecurity reports add practical pilot-review questions, explicitly separated from publisher claims. Technical retrieval diagnostics are in activity history; result text is larger. Latest backend255passed/3live-skipped, frontend17passed, production build passed. Real six-finding/four-file acceptance is retained at outputs/features-demo-20261022-190218; two AI sentences needed wording correction during review, with prior drafts retained. This is not an automatic factual-accuracy guarantee. Minimum available RAM reached1.4MiB, so longer reports still depend on available system resources.

The original cybersecurity sample has a fuller four-format edition at outputs/fuller-cybersecurity-report-20261022-190848/NEXUS-Fuller-Report.zip. Its source claims are retained and editorial review questions expand the body from192to332words. Production uses the existing owner account at localhost:8000.

## Latest acceptance

The latest acceptance adds general source comparisons, editable diagrams and approved multi-page readings. General research task `3079f62e244e4c82b3e2933825143140` completed in39.9seconds (21.53seconds model time) with four verified downloads and no excerpt fallback. The selected short summaries were manually checked against exact sentences. Browser task `9fec462edc974aebbea6857499922d23` passed real approval, two page captures, journey-log/download/preview and desktop/mobile checks. Output: `outputs/features-demo-20261022-182807`. Backend **237 passed /3 live skipped**, frontend **17 passed**, production build passed. Native Office/PDF layout review passed. RAM still reached13MiB available during inference; no hardware stability guarantee is claimed. Production uses the existing account and now enables the tested read-only browser. The original prompt status is mapped in REQUIREMENTS_STATUS.md.

The preceding feature acceptance is a real project-brief → follow-up question → PDF handoff chain. Task `adc49286f06f4c0b951e5e581a3c3703` retained the project code, owner and review day without repeating them in either follow-up prompt. Its two prior turns, parent links, history and authenticated PDF download survived an actual QA server restart. Follow-up answer and PDF tasks completed in 14.09 and 16.76 seconds respectively. Final sample and desktop/mobile screenshots: `outputs/followup-demo-20261022-143524`. Backend **172 passed / 3 opt-in live skipped** (20.58 seconds); frontend **15 passed** (14.73 seconds); TypeScript/Vite production build passed (JS 81.37 KB gzip). Earlier comparison acceptance is retained below.

Real UI task `6ae5e82f96db40aa8dd1e0ceaaa5224d` completed in **76.2 seconds**, including **55.5 seconds for model synthesis**, versus the earlier 120-second model timeout. It produced three workflow summaries and four verified HTTP200 downloads without excerpt fallback. Freshly fetched sources include Microsoft, Google Cloud and Cybersecurity Tribe; previously retrieved candidate URLs were used and disclosed when search providers returned no results.

The comparison distinguishes incident response, alert triage and malware analysis. Google passages describe historical previews; current availability was not verified. Incident-response evidence is secondary and single-publisher; Microsoft supplied general background rather than detailed evidence for the selected workflows. This is an attributed draft, not independent fact checking or deployment validation.

Bundle: `outputs/demonstration-6ae5e82f-final-002451/NEXUS-Demonstration.zip`. Older timeout/fallback demonstrations remain preserved. The saved model draft was re-rendered after layout repairs, with the previous answer and artifacts retained and a revision event recorded. PDF 2 pages, Word 2 pages, PowerPoint 11 slides and all 3 Excel sheets were visually inspected. Desktop/mobile checks passed with four HTTP200 attachment downloads and no browser errors.

Earlier comparison milestone: **161 backend tests passed, 3 opt-in live tests skipped** (18.37 seconds), real streaming Ollama greeting/function-call regression **1 passed** (22.51 seconds), and the original frontend 11-test/build result. The latest follow-up suite supersedes those counts above.

## Hardware and operation

The laptop has approximately 7.69 GiB RAM shared with Windows and other programs. The latest demo observed only 16.4 MiB available at its lowest sample during inference; tuning improved latency but did not eliminate memory pressure. Backend peak across both servers was 129.1 MiB, model-process peak 1.17 GiB, at most one model. Releasing the model before file rendering restored approximately 1.67 GiB available by task completion. Close unnecessary applications; no hard OS memory reservation or multi-user capacity guarantee is claimed.

Production runs on localhost:8000 through the standard start.ps1 launcher, using the existing owner account. Health/frontend/favicon.svg and compiled assets return 200; unauthenticated task access returns 401. Owner identity and existing session/task/artifact counts were preserved; an online SQLite backup was created before launch. Follow-up QA uses the separate ignored `tmp/followup-qa-data` database and a synthetic account, never production credentials. The owned QA server is stopped at handoff; its database, earlier `tmp/qa-data`, all previous artifacts and baseline outputs are retained. No public deployment, firewall change, account reset or user-data cleanup was performed.

## Remaining product work

Disposable code execution/builds require an available hardened Docker engine. Live browser actions, external connectors, arbitrary graphic design, broader memory beyond explicit bounded follow-ups, parser isolation, durable public abuse controls and independent security/load review remain incomplete. Tailscale HTTPS examples are prepared but unverified. See KNOWN_LIMITATIONS.md and USER_ACTIONS_REQUIRED.md.
