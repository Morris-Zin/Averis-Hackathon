import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from averis.timing import count, measure, processing_trace, timed


def records(caplog):
    return [
        json.loads(r.message.removeprefix("processing_timing "))
        for r in caplog.records
        if r.message.startswith("processing_timing ")
    ]


def test_nested_timings_keep_parent_paths_and_do_not_log_payload_or_exception(caplog):
    @timed("outer")
    def operation(secret):
        with measure("inner"):
            count("calls")
            raise ValueError(secret)

    with caplog.at_level(logging.INFO, logger="averis.timing"):
        with (
            pytest.raises(ValueError, match="private source text"),
            processing_trace("run-one"),
        ):
            operation("private source text")
        # A finished trace cannot collect or log later unrelated work.
        with measure("outside"):
            count("outside")
    [result] = records(caplog)
    assert result["calls"] == {"outer/inner": 1, "outer": 1}
    assert result["counts"] == {"calls": 1}
    assert (
        result["total_ms"]
        >= result["stages_ms"]["outer"]
        >= result["stages_ms"]["outer/inner"]
        >= 0
    )
    assert "private source text" not in caplog.text
    assert "outside" not in caplog.text


def test_two_worker_threads_keep_separate_timings(caplog):
    barrier = Barrier(2)

    def execute(ident):
        with processing_trace(ident), measure(ident):
            barrier.wait(timeout=3)
            count(ident)

    with (
        caplog.at_level(logging.INFO, logger="averis.timing"),
        ThreadPoolExecutor(max_workers=2) as workers,
    ):
        list(workers.map(execute, ["one", "two"]))
    results = {r["run_id"]: r for r in records(caplog)}
    assert set(results) == {"one", "two"}
    for ident, result in results.items():
        assert result["counts"] == {ident: 1}
        assert result["calls"] == {ident: 1}
