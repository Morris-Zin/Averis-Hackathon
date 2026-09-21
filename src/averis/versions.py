"""Versioned profiles for checkpoints and evidence compatibility.

Identical profiles reuse completed stages. Provider/prompt changes invalidate
inference but preserve compatible reading; acceptance changes can reinterpret
saved raw proposals; reader changes invalidate dependent extraction. Corrections
bind to an exact evidence-set fingerprint. Unversioned resumable checkpoints
cannot be reused as verified-compatible results.
"""

READER_VERSION = "reader-v6-word-structure"
OCR_PROFILE = "tesseract-language-route-rapid-v6-small-char-v1"
EVIDENCE_PARSER_VERSION = "evidence-v2"
CLASSIFICATION_POLICY_VERSION = "classification-v4-filename-context"
EXTRACTION_POLICY_VERSION = "extraction-v5-numeric-source-spans"
ACCEPTANCE_PROFILE = "jev-acceptance-v1"
NORMALIZATION_PROFILE = "source-bound-layout-v5-loading-label"
COMPARISON_POLICY_VERSION = "comparison-v1"
PAIRING_POLICY_VERSION = "pairing-v1-source-reference"
CHECKPOINT_VERSION = "checkpoint-v1"
CLASSIFICATION_PROMPT_VERSION = "jev-classification-v3-filename-context"
EXTRACTION_PROMPT_VERSION = "jev-extraction-v2-localized-roles"
