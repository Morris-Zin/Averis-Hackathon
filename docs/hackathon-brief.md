# Hackathon research brief

Investigated 19 September 2026. Source precedence: current written rules and later organizer clarifications; ceremony auto-captions are supporting evidence and can contain transcription errors.

## Sources

- [Participant handbook](https://docs.google.com/document/d/1YrnEANXCxypIKwONAr6QrcLnVW35FtwR66sJn_8M5dc/edit)
- [Problem statement and ZIPs](https://drive.google.com/drive/folders/1ouOrFF6GMKvJDaX_asN8R6v467W7P8Df)
- [Rules and submission requirements](https://docs.google.com/document/d/10PZgxtw4qvDg19NESDZPXt2oc6pSYsj9DKoKOY8PvdI/edit)
- [Preliminary rubric](https://docs.google.com/document/d/1EiI_mqJYeMN0D-dtZ_npCavVGXVcePFmcZ7O4d4ygQI/edit)
- [Final rubric](https://docs.google.com/document/d/1S-bLf45JOabMl1QUDgl4F6NTwuwD7UKbhPKh74sqaRo/edit)
- [Opening recording](https://www.youtube.com/watch?v=ORsJx5W2Q6s): 40:54; auto-generated transcript saved as `opening-transcript.txt`.
- User-supplied Discord clarification: docker ZIP ground truth is intentionally available for evaluating participants' work; README statements to withhold it are outdated. Message supplied at 9:10 AM without an absolute date.

## Dates

| Event | September 2026 |
|---|---|
| Opening/build start | 18, 18:00 |
| Workshop 1 | 20, 12:00–13:00 |
| Workshop 2 | 21, 19:00–20:00 |
| Preliminary submission | **22, 12:00 noon** |
| Shortlisting | 23, 12:00 |
| Finalist announcement | 24 |
| Final pitch | 26 |

Planning assumes Malaysia time (Asia/Kuala_Lumpur); source dates do not explicitly label timezone. Handbook says September 26 for finals; the auto-transcript at 28:07 says September 20, conflicting with its own earlier timeline. Use September 26 and monitor Discord updates.

## Product requirements

Start from email JSON. Classify as BL_COMPARISON, SI_REQUEST, INVOICE_QUERY, GENERAL, or SPAM. Only BL_COMPARISON continues to extraction/comparison. SI is the reference and draft BL is checked against it. Compare shipper, consignee, notify_party, port_of_loading, port_of_discharge, container_count, gross_weight_kg. Match semantically equivalent labels and normalize formatting without hiding real differences.

Show SI/BL values side by side and identify exactly the differing fields. All seven matching means “No mismatch detected.” Missing/unreadable/wrong documents or missing values must go to human review, with evidence and reasons. Advanced work includes PDF/DOCX/scans, misleading subjects, missing attachments, corrections, and retries. The actual kit also contains XLSX.

Evaluation export: one object keyed by every email_id; category, status (OK/MISMATCH/NEEDS_REVIEW), review_reason, has_defect, defect_fields. Review reasons: wrong_doc_type, missing_attachment, unreadable, missing_value. Internal confidence/evidence/retry state should be richer than this export contract.

## Rules and scoring

Teams: 2–5 eligible students; one team per participant. Work must be completed during the hackathon and be original. AI and meaningful cloud infrastructure are required. Any stack is permitted; no-code submissions are not accepted. Written preliminary rules encourage a semi-working prototype, while the ceremony and rubric emphasize a working prototype: aim for a reliable working flow.

Preliminary: architecture 15, working core 25, technology integration 15, feasibility/validation 15; problem understanding 10, innovation 10, practical value 10. Final: functionality 25, architecture/scalability 15, integration 15, engineering/robustness 15; effectiveness/value 10, UX/differentiation 10, impact/potential 10. Final rubric marks technology integration provisional pending sponsor alignment.

The kit's self-score is separate from judging: 50% end-to-end + 30% classification macro-F1 + 20% defect-F1. Human-review reliability is a separate diagnostic. Never present the kit score as the hackathon judging score.

## Ceremony clarifications (auto-caption timestamps)

- 8:03–8:46: speaker describes operations receiving up to 2,000 emails/day; contextual claim, not a measured project benchmark.
- 14:46–17:44: unrestricted AI assistance and workflow design; retain classification, intent understanding, comparison.
- 20:41–21:11: free cloud solutions allowed; no requirement to use AWS specifically. No promise of free credits was established.
- 21:42–22:00: some testing expected in final judging; no explicit hidden-test specification established.
- 28:00–29:14: top 10 finalists; 10-minute pitch/demo + 5-minute Q&A; all team members physically present; finalist mentorship.
- 29:17–29:29: announced prizes RM5,000 / RM3,000 / RM1,000. Handbook still says await prize announcement.
- 34:02–34:10: no slide/document page limit, keep demo video within five minutes.
- 36:35–37:08: embedding sample data for deployed demo is allowed.
- 38:24–39:18: external AI APIs allowed; training a model is not required.
- 39:21–39:46: supplied data is synthetic and can be placed in public GitHub repositories.

## Remaining decisions

Team/project name, AI provider and budget, deployment account/provider, frontend choice, and GitHub repository destination remain open. None prevents local setup. No credentials or paid accounts were created. Re-check Discord for updates before submission.
