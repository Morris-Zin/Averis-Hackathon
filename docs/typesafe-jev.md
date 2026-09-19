# TypeSafe / Jev investigation

Investigated 19 September 2026 from official live documentation. User already has access; credentials and live API connectivity have not been verified.

## Installed skill

Installed once with the user-requested method:

```powershell
npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent codex --yes
```

Project-local path: `.agents/skills/typesafe-ai/SKILL.md`; installation provenance: `skills-lock.json`. Codex can discover it next turn; its instructions were read and applied during this investigation. No Claude plugin installation was used.

## What Jev does

TypeSafe describes Jev as its first System One model. It understands natural-language state but returns constrained typed judgments rather than generated prose or reasoning explanations.

- Choice: select one supplied option; returns option probabilities and confidence.
- Noul: probability that a yes/no condition holds; no separate confidence field.
- Score: probability-weighted position across described ordered levels, plus probabilities/confidence.

Current input is text, including JSON/arrays of text. No direct image, audio, or video input. This means Jev cannot replace OCR for scanned PDFs. Confidence describes the answer distribution, not guaranteed correctness. Vendor speed/calibration claims have not been benchmarked here.

## Proposed role in Averis (not yet implemented)

1. Use Choice to classify subject + body into the five official categories. Internally preserve uncertainty/review state separately from the evaluator's constrained result format.
2. Parse TXT/PDF/DOCX/XLSX into text and candidate spans. OCR image-only PDFs using a separate component.
3. Ask Choice questions to select spans for the seven SI/BL fields, including a none-of-the-candidates option. Copy values verbatim from the selected source, retaining page/line/cell provenance. The correct value must be present in the candidates; selection cannot recover an omitted span.
4. Normalize numeric formats and compare values in code. Use focused semantic judgments only where normalization cannot settle equivalence safely.
5. Route missing evidence, ambiguous selections and service failures to review. Derive explanations from actual source evidence and deterministic templates, since Jev does not generate explanations.
6. Batch independent questions over the same state; use later requests only where new evidence/options depend on earlier answers. Record actual latency, token usage and cost. Tune thresholds against held-out data instead of copying cookbook thresholds.

Start with email classification and a small TXT subset before broad extraction/OCR integration. Ground truth remains evaluation-only. This is an architectural proposal, not an accuracy claim or completed AI integration.

## Python integration setup for the next implementation phase

Official SDK package: `typesafe-sdk`; imports include `TypeSafeClient`, `AsyncTypeSafeClient`, `Choice`, `Noul`, `Score`. Credentials use `TYPESAFE_API_KEY`; console: https://console.typesafe.ai/. The SDK supports `system_one(state=..., questions=...)`. Documentation currently uses `jev-latest` as the default alias; pin an available model version when recording reproducible benchmarks.

No SDK dependency or live API request was added in this investigation. Do not put credentials in chat or source. Configure the key in the server process environment when implementing the first live experiment.

## Primary sources

- https://docs.typesafe.ai/llms.txt
- https://docs.typesafe.ai/concepts/system-one.md
- https://docs.typesafe.ai/sdk/python.md
- https://docs.typesafe.ai/primitives/choice.md
- https://docs.typesafe.ai/confidence.md
- https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook.md
- https://github.com/typesafe-ai/skills

Local documentation snapshots are under docs/sources/typesafe-*; refresh current API/model information before integration.
