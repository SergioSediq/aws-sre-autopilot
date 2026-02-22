# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Handler tests: fallback_remediation, lambda_handler (non-ALARM, no-targets)
- Dashboard API tests: POST /api/approve, /api/reject, /api/chaos
- vm-image tests for health app
- pytest-cov and coverage report in CI
- docker-compose.yml for local dashboard
- docs/RUNBOOK.md for deployment and operations
- Makefile (test, lint, format, run-dashboard, docker-up)
- Release badge in README
- Trivy and Gitleaks security scanning in CI
- Type hints in handler.py
- SECURITY.md for vulnerability reporting
- docs/API.md — Dashboard API reference
- Dependabot for pip and GitHub Actions
- Handler test for TargetGroup dimension (get_unhealthy_targets)
- vm-image/requirements.txt, scripts/build-lambda.py, make build-lambda
- ask_genai tests (no API key, HTTP error fallback)
- GET /api/health aggregate test
- Bandit Python SAST in CI
- Terraform fmt -check in CI
- Python 3.10/3.11/3.12 matrix in CI
- Codecov coverage upload, coverage badge
- .editorconfig
- docs/architecture-decisions/ADR-001-approval-mode.md
- docs/SLO.md
- API docs link (/docs) in README
- GitHub templates (bug report, feature request, PR template)
- Dashboard tests: /api/logs, /api/archives, /api/incidents/stats
- Terraform tfsec security scan in CI
- Bandit in pre-commit
- vm-image Dockerfile
- .github/CODEOWNERS
- Optional mypy in CI
- Dashboard rate limiting (60/min per IP, disable with RATE_LIMIT_DISABLED=1)
- Route order fix: /api/incidents/stats before /api/incidents/{id}
- LICENSE file (MIT)
- .env.example and infra/terraform.tfvars.example for setup
- docs/TROUBLESHOOTING.md
- GitHub Actions CI (Python lint, test, Terraform validate)
- Unit tests for chaos_master, dashboard utilities
- requirements-dev.txt for development dependencies
- README aligned with self-healing project style (emojis, structure)
- Author section in README

### Changed

- CI: Ruff format includes vm-image, Trivy exit-code 1 (fail on CRITICAL/HIGH)
- Ruff format applied to dashboard, sre-brain, chaos-scripts
- README: add links to docs/API.md and CONTRIBUTING.md
- Expanded .gitignore (logs, IDE, terraform plan, etc.)
- Pinned dependency versions in requirements.txt
- Project structure documentation updated

## [1.0.0] - 2024

- Initial release
- AI-powered incident detection, diagnosis, remediation
- CloudWatch alarms → SNS → Lambda → Gemini AI
- SRE Command Center dashboard
- Chaos engineering scripts (disk-fill, OOM, nginx-crash)
