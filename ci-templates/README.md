# CI/CD templates (not active yet)

These are ready-to-use GitHub Actions configs, kept here **inert** so nothing runs
automatically. CI/CD setup is deferred — activate when ready.

## What's here
- `ci.yml` — lint (ruff) + tests (pytest) + frontend build + security scans
  (gitleaks/pip-audit/npm-audit/bandit/Trivy) + build/push images to GHCR + deploy hooks.
- `codeql.yml` — CodeQL scanning (Python + JS/TS).
- `dependabot.yml` — weekly dependency/action/image bumps.

## To activate later
```bash
mkdir -p .github/workflows
mv ci-templates/ci.yml ci-templates/codeql.yml .github/workflows/
mv ci-templates/dependabot.yml .github/
```
Then in GitHub repo settings:
1. **Secrets → Actions**: add `RENDER_DEPLOY_HOOK`, `VERCEL_DEPLOY_HOOK`, `VITE_API_URL`,
   `VITE_GOOGLE_CLIENT_ID`, `VITE_MAPS_API_KEY`. Allow Actions "Read and write" permissions
   (for GHCR image push).
2. **Branches**: protect `main`, require the CI status checks before merge.
3. **Code security**: enable Dependabot alerts, CodeQL/code scanning, secret scanning.
