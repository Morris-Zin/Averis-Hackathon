"""Per-delivery wall timings without logging documents, arguments or secrets.

Paths are inclusive: a parent includes its children. Subtract immediate children
to estimate its own work; never add parent and child durations as separate work.
Context variables isolate concurrent worker threads. Outside a delivery these
helpers are no-ops, including inside isolated document-reader subprocesses.
"""

import json
import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter


@dataclass
class _Trace:
    stages: dict[str, float] = field(default_factory=lambda: dict[str, float]())
    calls: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    counts: dict[str, int] = field(default_factory=lambda: dict[str, int]())


_trace: ContextVar[_Trace | None] = ContextVar("processing_trace", default=None)
_path: ContextVar[tuple[str, ...]] = ContextVar("processing_path", default=())
log = logging.getLogger(__name__)


@contextmanager
def processing_trace(run_id: str) -> Generator[None]:
    trace = _Trace()
    token = _trace.set(trace)
    path_token = _path.set(())
    started = perf_counter()
    try:
        yield
    finally:
        _path.reset(path_token)
        _trace.reset(token)
        log.info(
            "processing_timing %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "total_ms": round((perf_counter() - started) * 1000, 3),
                    "stages_ms": {
                        key: round(value * 1000, 3)
                        for key, value in trace.stages.items()
                    },
                    "calls": trace.calls,
                    "counts": trace.counts,
                },
                separators=(",", ":"),
            ),
        )


@contextmanager
def measure(stage: str) -> Generator[None]:
    trace = _trace.get()
    if trace is None:
        yield
        return
    path = (*_path.get(), stage)
    token = _path.set(path)
    key = "/".join(path)
    started = perf_counter()
    try:
        yield
    finally:
        _path.reset(token)
        trace.stages[key] = trace.stages.get(key, 0) + perf_counter() - started
        trace.calls[key] = trace.calls.get(key, 0) + 1


def timed[**P, R](stage: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with measure(stage):
                return function(*args, **kwargs)

        return wrapped

    return decorate


def count(name: str, amount: int = 1) -> None:
    trace = _trace.get()
    if trace is not None:
        trace.counts[name] = trace.counts.get(name, 0) + amount
