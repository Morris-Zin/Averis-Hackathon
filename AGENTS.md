# Project guidance

Read README.md and docs/hackathon-brief.md before implementation. This repository is a hackathon foundation; do not describe unbuilt capabilities as working.

- SI is authoritative; compare only the seven official fields.
- Classify all five categories; only BL_COMPARISON enters document checking.
- Preserve source evidence and uncertainty. Missing/unreadable input goes to review.
- Keep ground truth and official evaluation code out of application inference.
- Keep organizer kits unchanged; they are local dependencies under resources/official.
- No hard-coded per-email answers. No keys in source, prompts, logs, or commits.
- Verify with `.venv/Scripts/python.exe -m pytest` and `.venv/Scripts/ruff.exe check .`.
- Follow current written rules and later organizer clarifications over stale ZIP README wording.

## TypeSafe / Jev

Use `.agents/skills/typesafe-ai/SKILL.md` when designing or implementing AI features for this project, as requested by the user. Read live TypeSafe docs and the relevant SDK/primitive/cookbook before integration. See docs/typesafe-jev.md for the initial investigation.

Keep deterministic comparisons in code. Jev currently accepts text, not document images; parse/OCR attachments first. Preserve source spans and model distributions; calibrate review thresholds on our data. Keep TYPESAFE_API_KEY server-side and never print it.
