"""Versioned profiles for checkpoints and evidence compatibility.

Identical profiles reuse completed stages. Provider/prompt changes invalidate
inference but preserve compatible reading; acceptance changes can reinterpret
saved raw proposals; reader changes invalidate dependent extraction. Corrections
bind to an exact evidence-set fingerprint. Unversioned resumable checkpoints
cannot be reused as verified-compatible results.
"""

READER_VERSION = "reader-v5-multilingual-ocr"
OCR_PROFILE = "tesseract-language-route-rapid-v6-small-char-v1"
EVIDENCE_PARSER_VERSION = "evidence-v2"
CLASSIFICATION_POLICY_VERSION = "classification-v3-thread-reference"
EXTRACTION_POLICY_VERSION = "extraction-v4-complete-regions"
ACCEPTANCE_PROFILE = "jev-acceptance-v1"
NORMALIZATION_PROFILE = "source-bound-layout-v4-complete-regions"
COMPARISON_POLICY_VERSION = "comparison-v1"
CHECKPOINT_VERSION = "checkpoint-v1"
CLASSIFICATION_PROMPT_VERSION = "jev-classification-v2-thread-reference"
EXTRACTION_PROMPT_VERSION = "jev-extraction-v2-localized-roles"
