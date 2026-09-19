# Office source-reader validation — 20 September 2026

This is an offline document-reader acceptance check. It does not use ground truth,
AI inference, or the official scorer, and it does not claim that paired documents
have semantically matching shipment fields.

Every DOCX and XLSX attachment in `resources/official/bundle/attachments` was read
with `read_document_bounded` using a 30-second per-file deadline. The matrix checked
that every returned block had nonblank text and at least one location, that DOCX
locations retained paragraph identity without invented page numbers, and that XLSX
locations retained sheet identity with at least one cell-level location per file.

Results:

- 30 files read: 8 DOCX and 22 XLSX.
- All 30 returned evidence; none returned reader issues or a silent empty result.
- All 30 had valid format-specific and precise source locations.
- All eight DOCX/XLSX pairs had evidence and valid locations in both formats.
- Elapsed wall time was 11.187 seconds on the local Windows development machine.

The detailed local artifacts are
`outputs/office-reader-matrix/reader-matrix.json` and
`outputs/office-reader-matrix/summary.json`. They contain file names, sizes,
SHA-256 digests, counts, issues and location validation results, but no extracted
document text. Their SHA-256 digests are respectively
`55FAC6C25A9E6349758B45C90D44AF7E409334FB885CD7D030FD9D7DAE3B7C36` and
`26AC86DFEA5A7BC877926F3EEB6124666EA73937F8A33CCFD65E9EDC76DE4EB5`.

This run does not establish field extraction accuracy or cross-format value parity.
It also does not replace Linux container resource profiling: RSS and CPU were not
measured in this Windows run.
