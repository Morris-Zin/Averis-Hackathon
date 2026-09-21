# Replaceable application components

Averis uses explicit, trusted adapters in one backend package. It does not load
arbitrary third-party code, discover plugins dynamically, or need a plugin service.

`runtime.application_components` selects the shipped implementation set.
`components.Components` carries the reader, a per-run intelligence factory,
checkpoint identities and execution reserve. The factory returns both intelligence
and an optional pairing judge. `Processor` manages delivery and publication;
`ShipmentPipeline` validates source evidence and computes shipment findings.

## Replacing an implementation

- AI: implement `Intelligence`, construct it in a `RunIntelligence`, and supply a
  versioned `Components` to `Processor`. Pairing is selected explicitly alongside
  extraction, rather than silently disabled for replacement providers.
- Jev prompts: replace fields of `JevPrompts`, then pass the bundle to
  `application_components`. Defaults are collected in `jev_prompts.py`. Existing
  question text is unchanged. Prompt contents, selected models and relevant
  thresholds contribute to inference checkpoint identities.
- Whole reader: supply the `DocumentReader` callable plus its reader/OCR version
  pair. It returns original, located `DocumentEvidence`, never parser objects.
- Individual formats: add a trusted `FormatReader` in `documents.FORMAT_READERS`.
  The entry owns its handler and preview/OCR/archive metadata. Common document
  byte limits, Office archive checks, process deadlines and evidence handling stay
  outside the adapter. Upload allowlists must explicitly permit new extensions.
  Static registration is reconstructed when a parser subprocess starts; runtime
  dictionary mutation is not a deployment mechanism.

Keep parser implementation functions private to document reading. Splitting those
functions into separate files is optional; file count does not establish isolation.

## Checkpoint safety

Classification, extraction, reading and pairing have separate identities.
Changing extraction assistance does not invalidate compatible document reading.
Changing the pairing prompt does not invalidate classification or extraction.
Human category decisions retain priority. Incompatible saved document/extraction
stages fail visibly; a manual retry creates a new run. Do not reinterpret an old
stage as if a new implementation produced it.

The old `factory=` injection remains a compatibility seam for existing offline
fixtures and research scripts. It preserves their legacy checkpoint behavior and
does not provide plugin version guarantees and is rejected in production mode.
New integrations must use explicit
`Components`; production entry points use the versioned application composition.

Adapters propose readings. The core still owns source validation, conservative
normalization, comparison, uncertainty and publication. Provider SDK response
decoding stays in the provider adapter. Domain import-boundary checks reject
TypeSafe SDK and concrete adapter dependencies.

No default prompts, thresholds, model choices, parser algorithms, storage scheme
or HTTP contracts change in this refactor. Existing completed reports remain
unchanged. In-flight legacy extraction checkpoints lack the new implementation
identity and may require an explicit retry after upgrading.
