# User actions required

## To use the local application

1. Reuse the local server at http://127.0.0.1:8000 and sign in with your existing account. For a fresh installation, run `D:\nexus-ai\start.ps1` and create a first account with a unique password of at least 12 characters. No production password was invented or reset. QA uses an isolated synthetic account/database and is not a supplied login.
2. Keep Ollama running with `qwen3:1.7b`. Keep this laptop awake for running/scheduled work. Free local operation does not run while the laptop sleeps or is off.
3. Review generated research against its sources. A small model can produce invalid evidence mappings; the app then returns labeled retrieved excerpts. This can be less useful than a proper synthesis and is not independent fact verification.
4. To continue a completed result, choose **Follow up** and ask a question or request a document. Review the visible context target before submitting. **Remove prior context** starts independently; **View previous task** opens the original. Follow-ups use bounded saved answers, so old sources are not refreshed and long context can be shortened.

## Only if you want optional capabilities

- Browser readings/screenshots: install optional dependencies with `setup.ps1 -Browser`, set `NEXUS_BROWSER=1` and restart; include up to three public HTTPS URLs in a Browser task and approve its exact destination list. Matching Chromium is already present, and read-only browser capture is enabled in this local deployment. Offline previews, per-page PNGs and a JSON journey log are provided; live forms/typing are not implemented.
- More accounts: run `python -m nexus.manage add-user` locally and choose separate credentials. Do not share your owner password.
- Password recovery: use `python -m nexus.manage reset-password --username YOUR_USERNAME` locally. All sessions for that account will be invalidated.
- Private remote access: install/sign into Tailscale, choose restrictive grants, set exact allowed HTTPS hostname/secure cookies and follow DEPLOYMENT.md. This account authorization cannot be completed without you.
- Code execution/build verification: Docker's Linux engine was unavailable. A disposable sandbox with denied host mounts, no network, non-root user and strict resource limits must be configured/reviewed before implementing an executor. Starting Docker alone does not enable execution. Current safe alternative is source ZIP plus static validation.
- External email/calendar/GitHub/storage: no accounts are connected. Choose an integration, authorize official OAuth/scopes and add a reviewed connector. No account password should be pasted into task prompts.
- Public beta: choose a provider/domain, complete the documented security/isolation/testing gate, then explicitly authorize exposure. No public tunnel or firewall change is currently necessary or enabled.

## Data protection

Choose a private backup location for `data/`, `outputs/` and `backups/` and copy with the service stopped. Review retention/storage manually; automatic user-file deletion is disabled. No administrator request, OS reboot, purchase or unrelated-file change was needed for the local development performed here.

The Docker probe on22October returned a working client but no Linux-engine server (`dockerDesktopLinuxEngine` named pipe missing). This is an execution blocker, not evidence of a passed sandbox test. No administrator installation, OS reboot or credential entry was attempted.
