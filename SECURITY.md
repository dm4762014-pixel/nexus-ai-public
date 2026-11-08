# Security model and remaining boundaries

This version is intended for localhost/private trusted use. It is not certified for hostile public uploads or unrestricted multi-tenant agent execution.

## Implemented controls

- First account setup requires local request address and local deployment hostname. Setup is closed after one account. Additional accounts use local interactive management, with unique salted scrypt password hashes.
- Session tokens use 256-bit randomness, are hashed at rest, expire after 12 hours, and use HttpOnly/SameSite Strict cookies. Enable Secure for remote HTTPS. Sign-out deletes the session; password reset revokes all sessions.
- Same-origin mutation checks plus per-session CSRF headers. No permissive CORS middleware. Explicit trusted hosts. Browser responses use CSP, no framing, nosniff and no-store for API data. React escapes source/model text; download URLs and source protocols are checked.
- All task/upload/artifact/approval/schedule queries include owner identity from the authenticated session. No public registration, shared credentials or arbitrary legacy output downloads in the production app.
- Follow-ups require a completed parent owned by the signed-in user. Every ancestor lookup is owner-scoped; unknown/other-owner references return the same 404. Snapshots are built by the server, not accepted from the client, and contain bounded text/source metadata. Prior instructions and URL strings are data, never tool authorization. No unrelated history, raw source bodies or artifact paths are imported into context. UI context is cleared on sign-out and fresh-task navigation.
- Rate limits, global queue bound, daily task quotas, owner/file limits, signed-in downloads with path/hash checks, safe UUID workspaces, validation of Office/PDF signatures and decompression bounds. A shared file write lock limits concurrent upload/generation quota races.
- Research validates every DNS answer and pins actual numeric socket connections with hostname TLS verification; it rejects private/mapped/multicast/link-local destinations, credentials, non-HTTPS schemes and unsafe redirects. Compressed/raw body sizes are bounded. No anti-bot, paywall or login bypass.
- Retrieved sources and uploaded documents are untrusted data. Evidence summarization has no execution tools attached. Only original user input reaches the planner. Model tool names/arguments use strict schema validation. Citation and exact quote checks are not truth verification.
- Browser agent reads at most three explicitly supplied and approved public HTTPS pages, sequentially through the pinned fetcher, and renders escaped semantic blocks offline with JavaScript, external network, downloads and service workers disabled. Its temporary context closes in finally. It cannot access saved passwords/personal browser profiles. Source attributes/scripts/forms are discarded; reconstructed blocks are capped at6,500 text characters/48 visual units, individual downloads2MB and combined downloads4MB. A JSON journey log records requested/final URLs and content/screenshot hashes. Redirects retain repeated public-address checks and are logged. No live click/type/submit action is enabled.
- Coding source is never executed by the server. AST parsing does not establish that code is harmless. Builds/tests require a separate hardened disposable sandbox, currently unavailable.
- Approvals are owner-scoped, single-decision and bound to the saved ordered browser destination list/plan. Rejection/cancellation/restart resolves pending requests. Unsupported messaging/publishing/purchase/account/deletion integrations cannot be unlocked merely by approval.
- SQLite audit records capture account/task/schedule/approval activity without plaintext passwords or session tokens.

## Limitations

The Windows account, filesystem and SQLite files are trusted. App login does not encrypt stored documents or protect them from someone with OS file access. Use Windows account security, disk encryption and backups. No malware scanning, process-level parser sandbox, hard process memory quota, distributed rate limiter, independent penetration test or security certification has been completed.

Model cancellation is cooperative at call boundaries; it can wait for a blocking request timeout. OS DNS resolver time is not bounded by Python's HTTP timer. A bounded file size and safe parsing settings do not guarantee zero CPU/memory vulnerabilities in third-party libraries. Keep public beta disabled.

Request rate counters are in memory and reset on restart. Basic account brute-force throttling supplements strong unique passwords; it is not a public identity service. Account recovery is local CLI access. There is no OAuth integration, MFA, email recovery or external secret vault.

Legacy dashboards remain archival local-only examples and are unauthenticated. Never expose them, Ollama port 11434, Uvicorn dev reload, the data directory or a filesystem root through a tunnel. No default firewall rule or public tunnel was enabled by this work.

## Public readiness gate

Before exposing to unknown users: external review; HTTPS and strict proxy/host handling; invitation identity/MFA as appropriate; reverse-proxy request limits; durable abuse counters; OS/container parser and browser resource/network isolation; backup/retention/privacy handling; dependency/security scans; load testing within actual hardware; and a disposable sandbox before enabling code execution. Until then, public deployment remains an intentionally disabled deployment option.
