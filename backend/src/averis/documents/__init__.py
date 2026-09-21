"""Read source-linked evidence and previews without exposing parser internals."""

from averis.documents.bounded import read_document_bounded as read_document_bounded
from averis.documents.evidence import official_field_aliases as official_field_aliases
from averis.documents.evidence import (
    validate_document_evidence as validate_document_evidence,
)
from averis.documents.previews import DocumentPreviewError as DocumentPreviewError
from averis.documents.previews import render_preview_bounded as render_preview_bounded
from averis.documents.reading import SUPPORTED_FORMATS as SUPPORTED_FORMATS
from averis.documents.reading import read_document as read_document
