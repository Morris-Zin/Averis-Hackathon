"""Private document bounded implementation."""

from __future__ import annotations

import math
import multiprocessing
from multiprocessing.connection import Connection

from averis.documents.limits import DEFAULT_TIMEOUT_SECONDS, MAX_DOCUMENT_BYTES
from averis.documents.process_limits import (
    acquire_child_process_tree,
    apply_child_resource_limits,
    stop_process_tree,
)
from averis.documents.reading import read_document
from averis.domain import DocumentEvidence


def read_document_bounded(
    document_id: str,
    filename: str,
    content: bytes,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> DocumentEvidence:
    """Read a document in an isolated child process with a hard wall timeout."""

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        return DocumentEvidence(
            document_id=document_id,
            issues=["invalid_timeout:must_be_positive_and_finite"],
        )
    # Avoid copying an already-rejected large document into a child process.
    if len(content) > MAX_DOCUMENT_BYTES:
        return read_document(document_id, filename, content)

    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_bounded_worker,
        args=(send, document_id, filename, content),
        daemon=True,
    )
    process.start()
    send.close()
    try:
        if receive.poll(timeout_seconds):
            try:
                payload = receive.recv_bytes()
            except (EOFError, OSError):
                return DocumentEvidence(
                    document_id=document_id,
                    issues=["document_reader_failed:no_result"],
                )
            return DocumentEvidence.model_validate_json(payload)

        return DocumentEvidence(
            document_id=document_id,
            issues=[f"document_read_timeout:{timeout_seconds:g}s"],
        )
    finally:
        receive.close()
        stop_process_tree(process)


def _bounded_worker(
    connection: Connection,
    document_id: str,
    filename: str,
    content: bytes,
) -> None:
    try:
        acquire_child_process_tree()
    except OSError:
        result = DocumentEvidence(
            document_id=document_id,
            issues=["document_reader_failed:process_tree_isolation_unavailable"],
        )
        connection.send_bytes(result.model_dump_json().encode("utf-8"))
        connection.close()
        return
    apply_child_resource_limits(120)
    try:
        result = read_document(document_id, filename, content)
        connection.send_bytes(result.model_dump_json().encode("utf-8"))
    finally:
        connection.close()
