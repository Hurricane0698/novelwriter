# E2E Pressure Matrix

Use E2E first to discover real failure modes, then sink each discovered issue into the lowest stable deterministic test layer.

Current pressure priorities for Studio world-entry:

- upload handoff:
  uploaded novels should stay behind the preparation gate until ingest/bootstrap handoff is terminal
- first-entry contract:
  imported novels that already reached a ready writing state must not reopen empty-world onboarding on first Studio launch
- bootstrap click pressure:
  repeated clicks while extraction is pending must not issue duplicate triggers
- bootstrap failed recovery:
  failed extraction should expose a retry/re-extract action with stable copy
- pending marker stability:
  route reload/back/forward should not strand Studio in a fake running state

Test layering:

- `web/e2e/mock/**`: exploratory and deterministic browser probes with controlled API timing
- `web/e2e/integration/**`: thin end-to-end chain validation against the real backend stack
- `web/e2e/production/**`: built SPA entry and lazy-module failure recovery (`npm run test:e2e:production`)
- `web/e2e/desktop-installed/**`: attach to the installed Tauri WebView through `NOVWR_DESKTOP_CDP_URL`; no separate Chromium window
- `web/src/__tests__/**`: sink stable semantics here after pressure tests reveal the real failure mode

Rule:

Do not add broad new deterministic tests before a pressure probe reveals the concrete drift risk.

## Runtime evidence

The installed-product PowerShell harness enables a loopback WebView2 debugging
port only for its child application and supplies `NOVWR_DESKTOP_CDP_URL` to
Playwright. Run it only in a disposable Windows profile: it resets the current
user's NovWr data and installer registry state. The normal application needs no
debugging port. CDP tests use absolute URLs because the existing WebView context
does not inherit Playwright's `baseURL` setting.

The real-backend `llm-probe.spec.ts` supplies only the external provider response
locally. It covers bounded reasoning-budget retries and UI classification, not
live-provider availability. `E2E_PROBE_PROVIDER_PORT` optionally fixes the provider
port for a reverse SSH tunnel when browser and backend run on different hosts.

## Hosted Credential Profiles

Integration E2E must not hardcode personal hosted accounts.

Supported resolution order:

1. explicit `LoginOptions`
2. optional env-selected profile via `E2E_HOSTED_PROFILE`
3. default hosted env vars

Example local profile for a machine-only account:

```bash
E2E_HOSTED_PROFILE=OMEGA_LOCAL_VERIFY
E2E_HOSTED_OMEGA_LOCAL_VERIFY_NICKNAME=...
E2E_HOSTED_OMEGA_LOCAL_VERIFY_PASSWORD=...
E2E_HOSTED_OMEGA_LOCAL_VERIFY_USERNAME=...
E2E_HOSTED_OMEGA_LOCAL_VERIFY_INVITE_CODE=...
```

Use profile env only in local/private config such as untracked `.env`, never in repo-tracked tests.
