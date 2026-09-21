"""Durable PostgreSQL polling process for hosts without Cloud Tasks."""

from __future__ import annotations

import logging
import signal
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import timedelta
from threading import Event
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from averis.processing import DeliveryOutcome, Processor

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    """Operational bounds for the polling process."""

    concurrency: int = 1
    poll_seconds: float = 1.0
    reconcile_seconds: float = 60.0
    retry_base_seconds: float = 5.0
    retry_max_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not 1 <= self.concurrency <= 2:
            raise ValueError("Runner concurrency must be between one and two")
        if (
            min(
                self.poll_seconds,
                self.reconcile_seconds,
                self.retry_base_seconds,
                self.retry_max_seconds,
            )
            <= 0
        ):
            raise ValueError("Runner timing values must be positive")
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("Maximum retry delay cannot be shorter than its base")


class DurableRunner:
    """Poll durable work and delegate processing through a bounded worker pool.

    The outbox timestamp is both an inter-process claim guard and the durable
    start time used for retry delay. Processor remains the sole owner of run
    leases, attempt limits, checkpoints, budgets, and revision fencing.
    """

    def __init__(
        self,
        processor: Processor,
        options: RunnerOptions | None = None,
    ) -> None:
        if processor.settings.tasks_queue:
            raise ValueError("The polling runner cannot be combined with Cloud Tasks")
        self.processor = processor
        self.db = processor.db
        self.options = options or RunnerOptions()
        self._next_reconcile = 0.0

    def _retry_delay(self, attempts: int) -> float:
        exponent = max(attempts - 1, 0)
        return min(
            self.options.retry_base_seconds * (2**exponent),
            self.options.retry_max_seconds,
        )

    def _reconcile_if_due(self) -> None:
        current = monotonic()
        if current < self._next_reconcile:
            return
        try:
            self.processor.reconcile()
        except Exception as exc:  # noqa: BLE001 - reconciliation retries from durable state
            log.warning(
                "runner_reconcile_failed error_type=%s",
                type(exc).__name__,
            )
        finally:
            self._next_reconcile = current + self.options.reconcile_seconds

    def _claim(self, limit: int) -> list[str]:
        """Claim eligible outbox entries without owning domain run state."""
        from sqlalchemy import and_, or_, select

        from averis.persistence import Outbox, Run, utcnow

        if limit <= 0:
            return []
        claimed: list[str] = []
        now = utcnow()
        first_retry_cutoff = now - timedelta(seconds=self._retry_delay(1))
        second_retry_cutoff = now - timedelta(seconds=self._retry_delay(2))
        with self.db.session() as session, session.begin():
            rows = session.execute(
                select(Run, Outbox)
                .join(Outbox, Outbox.run_id == Run.id)
                .where(
                    Run.status.in_(["queued", "running"]),
                    Run.attempts < 3,
                    or_(
                        Run.status == "queued",
                        Run.lease_until.is_(None),
                        Run.lease_until <= now,
                    ),
                    or_(
                        Outbox.dispatched_at.is_(None),
                        and_(
                            Run.attempts.in_([0, 1]),
                            Outbox.dispatched_at <= first_retry_cutoff,
                        ),
                        and_(
                            Run.attempts == 2,
                            Outbox.dispatched_at <= second_retry_cutoff,
                        ),
                    ),
                )
                .order_by(Run.created_at, Run.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for run, outbox in rows:
                outbox.dispatched_at = now
                claimed.append(run.id)
        return claimed

    def _claim_safely(self, limit: int) -> list[str]:
        try:
            return self._claim(limit)
        except Exception as exc:  # noqa: BLE001 - polling must survive transient DB failures
            log.warning(
                "runner_claim_failed error_type=%s",
                type(exc).__name__,
            )
            return []

    def run_available(self) -> dict[str, str]:
        """Execute one bounded batch; useful for operators and acceptance tests."""
        if not self.processor.processing_enabled():
            return {}
        self._reconcile_if_due()
        run_ids = self._claim_safely(self.options.concurrency)
        if not run_ids:
            return {}
        with ThreadPoolExecutor(
            max_workers=self.options.concurrency,
            thread_name_prefix="averis-runner",
        ) as executor:
            futures = {
                executor.submit(self.processor.execute, run_id): run_id
                for run_id in run_ids
            }
            outcomes: dict[str, str] = {}
            for future, run_id in futures.items():
                try:
                    outcomes[run_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - run state remains durable
                    log.warning(
                        "runner_delivery_failed run_id=%s error_type=%s",
                        run_id,
                        type(exc).__name__,
                    )
                    outcomes[run_id] = "unexpected_failure"
            return outcomes

    def run_forever(self, stop: Event) -> None:
        """Poll until stopped, then let already-started deliveries finish."""
        active: dict[Future[DeliveryOutcome], str] = {}
        with ThreadPoolExecutor(
            max_workers=self.options.concurrency,
            thread_name_prefix="averis-runner",
        ) as executor:
            while not stop.is_set() or active:
                for future in [item for item in active if item.done()]:
                    run_id = active.pop(future)
                    try:
                        outcome = future.result()
                        log.info(
                            "runner_delivery_finished run_id=%s outcome=%s",
                            run_id,
                            outcome,
                        )
                    except Exception as exc:  # noqa: BLE001 - run state remains durable
                        log.warning(
                            "runner_delivery_failed run_id=%s error_type=%s",
                            run_id,
                            type(exc).__name__,
                        )

                if stop.is_set():
                    if active:
                        wait(
                            active,
                            timeout=self.options.poll_seconds,
                            return_when=FIRST_COMPLETED,
                        )
                    continue

                if not self.processor.processing_enabled():
                    stop.wait(self.options.poll_seconds)
                    continue

                self._reconcile_if_due()
                for run_id in self._claim_safely(
                    self.options.concurrency - len(active)
                ):
                    active[executor.submit(self.processor.execute, run_id)] = run_id

                if active:
                    wait(
                        active,
                        timeout=self.options.poll_seconds,
                        return_when=FIRST_COMPLETED,
                    )
                else:
                    stop.wait(self.options.poll_seconds)


def main() -> None:
    """Run the private polling worker as a Railway background process."""
    # Spawned document readers re-import this entry module. They do not need
    # application clients; load those only in the parent worker process.
    from averis.config import Settings
    from averis.persistence import Database
    from averis.processing import Processor
    from averis.storage import Storage

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    settings.validate_deployment()
    db = Database(settings.database_url)
    runner = DurableRunner(Processor(db, settings, Storage(settings)))
    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        log.info("runner_shutdown_requested")
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        runner.run_forever(stop)
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
