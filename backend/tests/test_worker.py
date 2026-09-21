"""Private worker delivery acknowledgement semantics."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from averis import worker


@pytest.mark.parametrize("outcome", ["busy", "held", "retry"])
def test_nonterminal_delivery_requests_queue_retry(monkeypatch, outcome):
    monkeypatch.setattr(
        worker,
        "processor",
        SimpleNamespace(execute=lambda _run_id: outcome),
    )

    with pytest.raises(HTTPException) as raised:
        worker.execute("run-1")

    assert raised.value.status_code == 503


@pytest.mark.parametrize("outcome", ["missing", "completed"])
def test_terminal_delivery_is_acknowledged(monkeypatch, outcome):
    monkeypatch.setattr(
        worker,
        "processor",
        SimpleNamespace(execute=lambda _run_id: outcome),
    )

    assert worker.execute("run-1") == {"status": outcome}
