# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.1.x   | ✅                 |
| 2.0.x   | ✅                 |
| < 2.0   | ❌                 |

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability in the Maritime
Intelligence Platform, please report it privately so it can be fixed before
public disclosure.

**Do not open a public issue for security vulnerabilities.**

### How to report

- Open a **private advisory** on GitHub:
  https://github.com/FrancKINANI/maritime-edge-ai-intel-platform/security/advisories/new
- Or send an email to **contact@ksf-space.org** with the subject
  `[SECURITY] Maritime Intelligence Platform`.

Please include:

1. A description of the vulnerability and its impact.
2. Steps to reproduce (as detailed as possible).
3. Affected versions and components (service, endpoint, dependency).
4. Any suggested fix, if known.

You should receive an acknowledgement within **72 hours** and a detailed
response (including a fix timeline) within **7 days**.

## Security Notes for Operators

- All services run as a non-privileged `appuser` inside their containers.
- Secrets (`CDSE_PASSWORD`, `GFW_API_TOKEN`, ...) are passed via environment
  variables; never commit `.env` to version control.
- The dashboard (`:8501`) and service APIs are intended for **trusted
  networks**. When exposing them publicly, place them behind a reverse proxy
  with TLS and authentication (see `docs/DEPLOYMENT.md`).
- Rotate API tokens regularly and use the lowest-privilege scopes available.

## Dependency Scanning

- Dependabot keeps Python dependencies up to date
  (`.github/dependabot.yml`).
- CI runs **Trivy** on container images and **Bandit** (SAST) on the Python
  codebase (`.github/workflows/ci.yml`).
