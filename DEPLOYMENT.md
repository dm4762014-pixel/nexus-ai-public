# Deployment options

No public tunnel, firewall exception, paid service, new external account or public deployment was enabled. Core runtime uses the existing Windows laptop and local Ollama, with no mandatory monthly API/software subscription.

## A Local Windows

Run `setup.ps1` once, then `start.ps1`. It binds **127.0.0.1:8000**, checks port availability, uses a single worker and serves prebuilt frontend files. Keep Ollama on loopback port11434. Create the owner account through localhost before remote configuration. Local startup, API requests and the compiled browser UI are tested; a Windows service/autostart-at-login installation has not been configured.

The laptop must be awake, powered and connected for web research/schedules. No concurrent-user capacity beyond the bounded single task queue is promised. Settings and execution events expose measured backend RSS and available system memory; Ollama is a separate process. Do not run development reload or multiple Uvicorn workers.

## B Private remote access

Tailscale Serve can privately proxy a loopback service to your tailnet over HTTPS. This requires your installation, sign-in and access-policy decisions; no account is assumed. Follow [official Serve documentation](https://tailscale.com/docs/reference/tailscale-cli/serve). Plan eligibility and organizational licensing depend on current [Tailscale plans](https://tailscale.com/pricing); verify your intended use rather than assuming personal free terms apply to a business.

1. First create your NEXUS owner at localhost. Stop the app.
2. Install/sign in to Tailscale using its official installer. Authorize only intended users/devices and restrictive tailnet grants. Do not use Funnel (public exposure).
3. Configure `.env` from `deployment/private.env.example`, replacing the exact machine hostname. Set secure cookies. Create separate local NEXUS accounts for other authorized people with `python -m nexus.manage add-user`.
4. Start `.\start.ps1 -TrustedLocalProxy`. This trusts forwarded scheme headers **only from 127.0.0.1**, keeping CSRF origin comparison consistent with proxy HTTPS.
5. After reviewing access policy, run `tailscale serve --bg http://127.0.0.1:8000`. Open the HTTPS address printed by Tailscale and sign in. Do not proxy Ollama.
6. Verify login, CSRF mutation, session cookies, two-account isolation, downloads and tailnet access denial for unintended identities. Stop private serving with `tailscale serve reset` when no longer needed.

This configuration is documented but **not deployed or tested against a signed-in Tailscale account** here. The user must perform that authorization. An actual HTTPS reverse-proxy test is required before relying on private access; no claim is made from a config template alone.

## C Controlled public beta

**Not enabled and not approved for exposure to unknown users.** The app has core authentication/owner isolation, but hard parser/browser resource isolation, external penetration testing and durable abuse prevention remain incomplete. Arbitrary generated code execution stays disabled even if Docker later becomes available.

Prepared examples: `deployment/public-beta.env.example` and `deployment/Caddyfile.example`. They do not create a tunnel. After the SECURITY.md readiness gate passes, a reviewed reverse proxy or named Cloudflare Tunnel can proxy the API/UI only, with HTTPS, strict hosts, upload limits and invitation-only access. Cloudflare account/domain authorization is a user action. Consult [official tunnel publishing documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/) and current terms/limits before choosing a plan. Quick public tunnels are not a safe beta substitute.

Before enabling: complete the security gate, choose/authorize a hosting account/domain, review privacy/retention, verify limits, test real HTTPS/proxy behavior and external denial cases, and obtain explicit public-exposure approval. Code execution/browser forms remain disabled. Rate limiting and single-worker quotas are not an unlimited hosting entitlement. This laptop is suitable only for a small measured workload, not unlimited public users.

## Migration

Move to a dedicated VPS/cloud VM when observed CPU/RAM, task latency, queue pressure or availability needs exceed the laptop. Keep the same ASGI API and compiled frontend; back up/migrate SQLite with the service stopped; maintain owner artifact paths/metadata. Initially retain one worker. Later add database job leases, stronger SQL/object storage and isolated tool workers before scaling horizontally. Keep inference private and use one suitably sized local model; optional paid infrastructure/AI requires a separate user choice.

Official implementation references: [FastAPI deployment processes and memory](https://fastapi.tiangolo.com/deployment/concepts/), [Ollama chat/tool API](https://github.com/ollama/ollama/blob/main/docs/api.md), [Playwright network interception](https://playwright.dev/python/docs/network). A configuration or documentation link does not prove a deployment succeeded.
