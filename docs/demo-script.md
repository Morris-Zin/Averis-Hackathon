# Five-minute demonstration script

Target duration: 4 minutes 45 seconds. Record only after the public deployment and live processing checks pass. This script is a recording aid, not a claim that a submission video exists.

## 0:00–0:25 — Problem

Introduce the team and project name. Explain: “Shipping staff receive many kinds of messages in one inbox. For document checks, the Shipping Instruction is the reference, and the draft Bill of Lading must agree with it before release. Averis brings classification, comparison and source evidence into one work queue.”

## 0:25–0:55 — Architecture

Show the diagram in build-plan.md. Explain that Next.js presents the workspace, FastAPI owns the workflow, PostgreSQL persists work, private R2 stores originals, and authenticated Cloud Tasks invokes the worker. Parsing and OCR run with explicit resource limits. Jev chooses categories and source evidence; application code performs the numerical and text comparison. Show actual deployed service names only after deployment is verified.

## 0:55–1:30 — Inbox and uncertainty

Enter a fresh demo workspace. Show the five categories and the Needs review queue. Call out the illustrative classification label on saved scenarios. Demonstrate accepting or changing an uncertain category. Confidence is a routing signal, not a measured accuracy percentage.

If the verified live deployment is ready, run one controlled example and wait for its persisted result. Clearly distinguish that live result from preloaded illustrative scenarios. Do not suggest that a saved fixture was just processed by Jev.

## 1:30–2:20 — Comparison and evidence

Open Mismatches. The Port Klang scenario automatically contains a destination-port and container-count mismatch. Select the count finding and show SI count three and BL count four in their original evidence. Explain that missing information is unresolved rather than zero, and that a case can contain both known mismatches and unresolved checks.

## 2:20–3:10 — Review actions and revisions

Correct a reading by selecting its source evidence. Show that correctly reading four does not change the original BL to three or remove the genuine discrepancy. Move the case to Waiting for revised draft, then attach the labelled controlled replacement. Show the new result and retained original document/history. Completing a review records an employee action; it does not erase discrepancies.

## 3:10–3:50 — Formats and boundaries

Show one already verified native PDF and one OCR preview with highlighted evidence. Show structured DOCX or XLSX evidence if it fits the recording. Explain the supported limits and demonstrate an explicit unreadable or unresolved outcome. Do not claim unsupported spreadsheet formulas, arbitrary layouts or multilingual accuracy.

## 3:50–4:25 — Evidence and operational controls

Show the current validation record and actual measured evaluation results, if available. Label automatic coverage, abstentions and reviewer-assisted results separately. Mention durable checkpoints, stale-result rejection, isolated demo sessions and the shared AI spending allowance. Do not present the small earlier Jev experiments as full-pipeline accuracy.

## 4:25–4:45 — Practical value and next steps

Conclude with the practical benefit: employees can find discrepancies and inspect why, while uncertain cases stay visible. Future work is production identity, email connectors and measured multilingual support. Framework choices and workers alone do not establish enterprise readiness.

## Before publishing

- Replace the opening team details with the actual team information.
- Verify the deployed URL in a fresh signed-out browser and retain access through judging.
- Record actual UI actions with readable text; keep the final video below five minutes.
- Check that credentials, billing pages, ground truth and personal browser tabs are absent.
- Upload to the chosen public/unlisted destination and verify link access before submission.
