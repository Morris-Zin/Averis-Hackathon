"""Scheduled run recovery. Workspace data is retained until explicit deletion."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from averis.processing import Processor


def maintain(processor: "Processor") -> int:
    """Recover interrupted runs without expiring workspace rows or originals."""
    return processor.reconcile()
