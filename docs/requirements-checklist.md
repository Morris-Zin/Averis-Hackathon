# Expected results and extensions — acceptance check

Checked against the organizer requirements on 20 September 2026. These boxes
mean implemented support with the evidence below, not perfect accuracy on every
document or enterprise readiness.

- [x] **Seven-field comparison.** Shipper, consignee, notify party, loading port,
  discharge port, container count and gross weight in kilograms. SI is the
  reference; numeric parsing and unit conversion are deterministic.
- [x] **Clear email-specific report.** Case identity, subject, sender and original
  email are visible. Findings show SI and BL values side by side and link to
  evidence. Known mismatches remain visible alongside unresolved fields.
- [x] **Honest all-clear result.** “No mismatch detected” requires an accepted
  comparison category, valid pair, current report and seven matching fields with
  no blocking issues. Missing values and processing failures cannot qualify.
- [x] **Organizer container example.** A regression checks SI count 3 against BL
  count 4 with equal 22,000 kg weights: only container count differs. It also
  checks 22 MT conversion and the all-seven-match variant.
- [x] **PDF and Word attachments.** Native PDF layout extraction, page previews
  and coordinates; DOCX paragraphs and tables with structured evidence previews.
  Word previews do not claim original pagination. XLSX is also supported.
- [x] **Scanned documents.** Tesseract English OCR for image-only PDF pages and
  PNG/JPEG, retaining image-region locations and OCR confidence separately from
  AI confidence. Mixed PDFs choose native reading or OCR per page.
- [x] **Messier input.** Field-label aliases, conservative whitespace/case
  normalization, unit conversion, email-thread preparation, misleading subjects
  and missing attachments have regression coverage. Ambiguous values abstain;
  formatting differences are not automatically treated as real discrepancies.
- [x] **Human review and corrections.** Missing, unreadable and uncertain inputs
  produce review reasons. Reviewers select source evidence or explicitly verify
  an OCR transcription. Corrections recompute the report and preserve history;
  they do not alter the source or conceal a genuine mismatch.
- [x] **Visible failures and retries.** Failed processing is distinct from a
  document result. Retry, durable checkpoints, exhausted-attempt handling and
  stale-result protection have acceptance coverage.

## Fresh evidence

Current readers processed **58 official advanced attachments** offline in Linux
with actual Tesseract, networking disabled, one CPU and 1 GiB: 28 PDF, 8 DOCX,
22 XLSX. All six scanned PDFs produced OCR evidence with locations. Fifty-six
documents returned evidence without reader issues; two malformed PDFs returned
explicit unreadable errors. The pass took 27.373 seconds. This measures reader
support, not Jev field-selection or end-to-end accuracy. Ground truth was not
mounted, and no AI calls were made.

Regression coverage is in `tests/test_verification.py`, `test_documents.py`,
`test_document_limits.py`, `test_case_status.py`, `test_domain_review.py`,
`test_workflow_actions.py`, `test_processing.py`, and `test_email_preparation.py`.

The deployed browser acceptance for release `ee08de6` imported three synthetic
emails. The invoice was categorized correctly, the missing-document comparison
required review, and the complete pair returned five matches and the two
deliberate mismatches. Classification appeared while processing without a manual
refresh. Duplicate import reused all three cases. Earlier browser acceptance
also exercised source-bound correction, revisions, history and conflicting
reviewer edits; see [validation](validation.md).

## Limits to disclose

- English first; 10 MB per attachment, 20 PDF pages and at most three OCR pages
  per document. Exceeded limits require review rather than silent truncation.
- Ordinary DOCX tables/paragraphs and bounded XLSX cells are supported. Complex
  Office structures, unreadable scans and uncertain formulas can require review.
- Supporting a format does not guarantee correct extraction from every layout.
  See [evaluation results](evaluation-results.md) and the
  [classification checkpoint](classification-checkpoint.md) for measured accuracy
  and dataset limitations, separately from feature coverage.
- Unreadable documents may have no extractable evidence; their original file and
  failure reason remain available. Arbitrary revised-file uploads are currently
  operator-only; saved demo cases offer controlled replacement drafts.
