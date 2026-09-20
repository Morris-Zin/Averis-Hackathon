# Bulk email import

The queue offers **Bulk import** next to **Add email**. One request imports many
emails; every email reuses the single-email intake path, so deduplication,
durable worker runs and the monetary AI guard behave exactly as for manual
imports. Identical submissions in the same workspace reuse the existing case,
so retrying a bulk request never creates duplicate cases.

## Supported layouts

**Mode 1 — organizer-style ZIP.** A `.zip` archive containing email JSON files
(any folder, for example `inbox/email_001.json`) plus the attachment files
they reference (for example `attachments/email_001_SI.txt`).

Each email JSON has the organizer shape:

```json
{
  "email_id": "email_001",
  "from": "sender@example.test",
  "subject": "Draft BL for SYNTH-001",
  "body": "Please check the attached documents.",
  "attachments": ["attachments/email_001_SI.txt", "attachments/email_001_BL.txt"]
}
```

**Mode 2 — loose email JSON files.** Select several `.json` files in the same
shape, optionally with loose attachment files. References resolve against the
loose attachment pool by exact filename.

A small synthetic example of the ZIP layout (never organizer data) lives in
`docs/examples/bulk-import/`.

## Attachment resolution

- An attachment reference resolves by exact relative archive path first, then
  by unique basename (`email_001_SI.txt` matches
  `attachments/email_001_SI.txt`).
- References never cross email boundaries: an email without references imports
  with zero attachments even when other emails bring files.
- A reference with no match is kept as an honest missing attachment: the email
  still imports, the result names the missing file, and processing routes the
  case to human review instead of inventing a match.
- A basename matching several files, an unsafe reference, an unsupported file
  type or more than eight attachments fails only that email with an actionable
  reason; valid emails still import.

## Safety bounds

| Bound | Value |
|---|---|
| Archive entries | at most 2000 files |
| Decompressed archive total | at most 32 MB |
| Single file / attachment | 1 byte to 10 MB |
| Attachments combined per email | at most 20 MB |
| Attachments per email | at most 8 files |
| Email JSON file | at most 2 MB |
| Emails per request | at most 600 |
| Loose attachments per request | at most 1200 |
| Transport request | at most 21 MB |

These are parser resource bounds, not usage quotas: the full 520-email
organizer set fits in one request whenever it stays within the byte bounds.
Attachments within one email are sorted by filename, so re-uploading the same
files in a different order reuses the existing case. Only email transport
fields are read from email JSON; unknown keys (including any evaluation
labels) are ignored and can never become inference input.

Archives reject absolute paths, `..` segments and duplicate member names, and
are read from memory — members are never extracted to disk. There are no
per-session or daily run quotas; live processing stays under the shared
monetary budget guard.

## Results and retry

Preview (before importing) lists every email with its resolved and missing
attachments. Importing reports per-email `accepted`, `duplicate` or `failed`
rows with case links, accurate totals and actionable errors. Failed rows can be
fixed and the same selection re-imported: already-imported emails return as
`duplicate` rows pointing at their existing cases.
