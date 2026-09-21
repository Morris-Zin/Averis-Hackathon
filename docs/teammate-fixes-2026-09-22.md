# Teammate testing fixes — 22 September 2026

The equivalent-label PDF test (T04) exposed a reader boundary bug. Separate party and port fields were grouped together because some labels were absent from the shared vocabulary. Jev selected those blocks, but source validation correctly rejected ambiguous readings. The change recognizes compound shipper/consignee labels, Party to Notify and Destination Port. Addresses remain multiline, source locations remain intact, and explicit discharge evidence takes priority over a separate destination label, including localized discharge labels. Reader and normalization versions invalidate incompatible saved readings on a new run.

When the app cannot establish one SI and one BL, review messages now distinguish absent documents, unreadable documents, multiple candidates and an unidentified role. Unknown roles are not claimed to be conclusively wrong document types. Export policy is unchanged; these messages help users understand the next action.

The case-list API now returns a compact queue projection. Detail still includes source evidence, reports and history. Both views use the same backend assessment. On 25 saved teammate cases, uncompressed item JSON shrank from 334,309 to 13,823 bytes (95.87%). This does not remove full state loading from the database and is not a guaranteed latency improvement. Older browser queue code uses the retained fields; detail requests remain unchanged.

## Acceptance evidence

- Original T04 PDF pair: browser import through the built frontend and live Jev completed with seven matches, a valid pair and both rendered previews. Before the fix, five fields were unresolved on two SHA-matched live cases.
- Original T10 wrong-document pair: browser import remained Needs review with “No draft BL identified”, rather than the generic selection message.
- Re-reading 18 native PDF/DOCX attachments changed only T04's SI evidence (six blocks to nine); the other17 retained identical blocks and issues. Two PNGs remained unavailable to the local OCR environment, so this is not a fresh OCR success claim. Existing Linux/live OCR results were not altered.
- The720-case replay retained581 exact outcomes and1,524 exact synthetic field values, with zero protected regressions. This is a recorded-provider, saved-reader-evidence check of normalization/report behavior, not a fresh720-call accuracy test. No saved document contained the newly introduced label strings. Original teammate documents and independent layout/address/discharge safeguards cover reader changes separately.
- Full application verification passed493 backend tests,21 frontend tests, strict typing, lint, contracts and production build; two optional tests were skipped. Subsequent localized discharge and HTTP projection checks also passed. Final CI validates the complete committed change.

No change was made to weight-unit requirements, confidence thresholds, document-pair acceptance thresholds or automatic comparison outcomes. A bare weight still requires review rather than an assumed kilogram value. Pei En's exact reported unit failures remain unverified without their source cases.
