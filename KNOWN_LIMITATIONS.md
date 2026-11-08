# Feature status and known limitations

This is a functioning local MVP, not completion of the entire takeover vision. Tests and status are kept separate from source implementation.

| Feature | Status | Actual boundary |
|---|---|---|
| Local Ollama connection/inference | Implemented and live tested | qwen3:1.7b, one task/model, 2048 context; small-model reasoning is limited. |
| Function tool calling and schema checks | Implemented and live tested | Model can return structurally valid but inappropriate plans; deterministic common routing and URL authorization take priority. |
| Research with real HTML/PDF sources | Implemented and live tested | HTTPS/2MB/three sources/limited extraction; some sites return403 or block requests; no bypass. |
| Evidence-mapped draft synthesis | Implemented; cybersecurity and general-topic acceptance tracked in TEST_RESULTS.md | Compact schema-constrained workflow summaries and general source perspectives, with Python-owned evidence mappings and source coverage. Numerical performance claims are excluded. Invalid output still has an explicit excerpt fallback. No guaranteed factual accuracy, current deployment status or independent corroboration. |
| Citation numbers and exact quotes | Implemented and tested | Registry membership/quote presence checked; no automated entailment or independent corroboration proof. |
| PDF/DOCX/XLSX/PPTX/CSV/TXT/JSON | Implemented and parser tested | Professional bounded templates; not a general design or spreadsheet modeling service. Unicode depends on system fonts; complex scripts may need DOCX. |
| Tables/formulas/charts/validation | Implemented for controlled workbook patterns | Timetable SUM and input-change recalculation checked in native Excel; arbitrary formulas and imported formulas are not executed server-side. |
| PPTX layouts/notes/source links | Implemented and visual tested | Editable text/theme and cited parallel comparison diagrams; full findings/notes/links retained. Automatic images and arbitrary graphic design are not implemented. |
| Uploaded-file summary | Up to nine selected findings, original evidence and extracted-text line locations; brief requests up to three | Up to three files and100,000accepted extracted characters per new upload; selected passages only, no full-document coverage guarantee or semantic fact proof. Older30,000character uploads may need reattachment. No OCR, encrypted documents, macro execution, arbitrary ZIP extraction or malware scanner. |
| Combined research/four outputs | Live tested with real downloads | File production can complete with a labeled excerpt fallback; that is not proof of a complete factual research comparison. |
| Browser navigation/read/screenshot | Partial and live tested | One to three explicitly approved public HTTPS pages, semantic offline snapshots, real locator readings, PNGs and a verified JSON journey log with previews. No live DOM typing, form filling or clicking; no autonomous destination discovery. |
| Code project source/ZIP/AST checks | Implemented and tested | Model project or explicitly labeled scaffold fallback. No semantic correctness/build claim. |
| Coding sandbox execution | Disabled / blocked | Docker engine unavailable and no hardened sandbox configured. WSL presence alone is not sufficient. No model shell commands execute. |
| Persistent task/conversation history and follow-ups | Implemented and live tested | Explicit parent-linked follow-ups retain up to 3 prior results/2,400 text characters. Answers/documents only; source links are inherited without refreshing pages. No automatic global memory or arbitrary tool continuation. |
| Cancellation/retry/restart | Implemented and regression tested | Model frame/lock checkpoints and tool boundaries; model loading or waiting for the next frame can still take up to the configured timeout. Partial files retained; interrupted tools never auto-replay. |
| Accounts/session/CSRF/owner isolation | Implemented and tested | Local trust boundary; no MFA/OAuth/email recovery, OS-level data encryption or external penetration test. |
| Approval decisions | Implemented and tested | Exact browser destination lists only. Unsupported external actions fail closed; approval cannot activate an unimplemented connector. |
| Recurring schedules | Recent runs show the latest five attempts, including quota skips, and link to saved results | History starts with new attempts; earlier runs are not backfilled. Minimum 15 minutes; the laptop and app must be running. Missed intervals do not trigger catch-up runs. Acceptance testing adjusted due times rather than waiting for real intervals. |
| React responsive workspace | Implemented and real browser tested | Compiled static runtime; desktop/mobile/source/download/form/error paths verified. |
| Local Windows startup | Implemented and runtime tested | One local ASGI process; no Windows service/auto-login boot task installed. |
| Private remote access | Prepared but unverified | Requires Tailscale installation/sign-in, grants, exact host/secure cookies and real HTTPS validation. |
| Public beta | Intentionally disabled | Hardened parser isolation, durable abuse controls, independent security review and hosting authorization pending. |
| External integrations | Interface only / not implemented | Email/calendar/cloud storage/GitHub/OAuth connectors not connected or implemented. |

## Resource and operational limits

The machine has approximately 7.69 GiB physical RAM, shared with Windows and other applications. Model download size does not represent runtime memory. Backend event RSS, available RAM and separate integration observations are in TEST_RESULTS.md. A stress run reached dangerously low free RAM when Chromium started while model weights remained resident. The app now explicitly unloads the model before browser startup and document rendering, refuses browser launch under 384 MiB and unloads under 512 MiB after tasks. The latest comparison completed synthesis in 55.5 seconds but still reached 16.4 MiB available during inference. These are cooperative safeguards, not an OS memory reservation; close unnecessary programs. Task quotas and bounded parsing do not establish hard OS process isolation. The public beta gate remains closed.

Generated artifact retention is indefinite with manual review. There is no automatic user-data cleanup. Metadata/audit database growth is not automatically pruned. Rate counters reset on restart. Backups and recovery procedures require the owner to manage private copies.

Legacy dashboards are retained for compatibility and remain local-only/unauthenticated. Only `main:app` is the supported secured entry point. Optional public/private deployment examples are documentation, not deployed services.

Fuller default reports target up to nine atomic findings, with fewer when evidence is sparse or additional points fail checks. Reports can take longer: the latest six-point run took156.6seconds and reached1.4MiB available RAM. Provenance, actor and sentence checks do not prove factual entailment; acceptance review corrected two unsupported AI elaborations while preserving prior drafts. The same review remains necessary for future generated reports. Brief requests stay smaller. No new UI mode or larger local model was introduced.
