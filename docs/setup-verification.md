# Setup verification - 19 September 2026

- Python 3.12.14 virtual environment; dependencies installed and pinned in uv.lock.
- Ruff: all checks passed. Pytest: 8 passed; 2 dependency deprecation warnings from Starlette (httpx/AnyIO aliases).
- Dataset inspection: 520 emails, 250 attachments (192 TXT, 28 PDF, 8 DOCX, 22 XLSX).
- Official sample submission validates against the output contract and complete email-ID coverage.
- Official scorer executed locally: 520 records; placeholder score 0.0124137931. This all-GENERAL placeholder is only a setup smoke test, not an AI result. Full output: outputs/setup-score.json.
- API health tested in-process. It reports liveness and the two processing configuration flags; it does not claim database, storage, provider or worker readiness.
- Docker executable exists but daemon was unavailable. Docker service not started or tested; local scoring works without it.
- Git initialized on main; no remote, commit, publication or deployment.

SHA-256 archive integrity:
- sdoc-hackathon-bundle.zip: 2C7EF1EB3219CA1FCED4DF40A94020E374CC4981BDDFA2A2E65DBA6EFCA588D1
- sdoc-hackathon-docker.zip: 62C89020C78AB1313D49325B9B9CF3624EFB46F3DE72176555ECDE3C2D7C6FA7
