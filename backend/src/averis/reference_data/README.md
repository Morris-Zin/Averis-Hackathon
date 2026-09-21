# Port reference snapshot

Derived from UNECE / UN/CEFACT **UN/LOCODE 2025-1**, under CC BY 4.0.

- Publication: https://unlocode.unece.org/publications/
- Original ZIP: https://opensource.unicc.org/un/unece/uncefact/vocab-locode/-/jobs/artifacts/2025-1/download?job=package-release
- License: https://creativecommons.org/licenses/by/4.0/
- Definition/status/terminal limitations: https://unlocode.unece.org/recommendation16/
- Original ZIP SHA-256: `ad409fc7149b10f98d61190c34d9daf78b78bb8b31464cc66de1a89d09b01b5d`
- Derived snapshot SHA-256: `d6128c5469b2dc59fff48df348a003e672bca70631383b7a236c6dc5369496d6`

Changes: country headings, original names and ASCII names become exact lookup
indexes. All names retain ambiguity, including non-port/unapproved entries.
Only function-1 maritime locations with status AM, AA, AC, AF, AI, AS or RL and
without deletion marker X can establish a match (16,127 locations). No translated,
fuzzy or manually guessed aliases are added. RL confirms a recognized location,
not its relevance to trade. UN/LOCODE is not a terminal directory or a guarantee
of geographical accuracy; never strip terminal qualifiers to force a match.

The private R2 artifact and this bundled cache contain identical bytes. A release
loads this verified local cache once, without a live lookup or mutable download.
Missing/corrupt cache disables alias matching; ordinary comparison continues.
Directory updates require a new reviewed artifact, checksum and benchmark run.

Reproduce from the original ZIP, from the repository root:

```
uv run --project backend python scripts/build_port_directory.py SOURCE.zip backend/src/averis/reference_data/unlocode-2025-1.json.gz
```

This reference data contains no benchmark answers, emails or credentials.
