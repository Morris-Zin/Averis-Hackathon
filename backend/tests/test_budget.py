import pytest
from sqlalchemy import select

from averis.budget import BudgetAuthority, BudgetUnavailable
from averis.config import Settings
from averis.persistence import Budget, Database, Reservation


def authority(
    *, input_rate: str = "1", output_rate: str = "0"
) -> tuple[Database, BudgetAuthority]:
    db = Database("sqlite:///:memory:")
    db.create_local_schema()
    settings = Settings(
        _env_file=None,
        live_enabled=True,
        budget_verified=True,
        prior_spend_usd="0",
        input_usd_per_million=input_rate,
        output_usd_per_million=output_rate,
    )
    with db.session() as session, session.begin():
        session.add(Budget(id=1, prior_spend=0, development=0, demo=0))
    return db, BudgetAuthority(db, settings)


def reservation(db: Database, reservation_id: str) -> Reservation:
    with db.session() as session:
        row = session.get(Reservation, reservation_id)
        assert row is not None
        session.expunge(row)
        return row


def test_success_replaces_reservation_with_rounded_reported_usage() -> None:
    db, budget = authority(input_rate="0.042", output_rate="0")
    reservation_id = budget.reserve("run-1", "development", 12_000, 1)

    assert budget.settle_success(reservation_id, 59_061, 14_795, "request-1")

    row = reservation(db, reservation_id)
    with db.session() as session:
        ledger = session.get(Budget, 1)
        assert ledger is not None
        assert ledger.development == 2_481
    assert row.input_usd_per_million == "0.042"
    assert row.output_usd_per_million == "0"
    assert row.actual_amount == 2_481
    assert row.input_tokens == 59_061
    assert row.output_tokens == 14_795
    assert row.provider_request_id == "request-1"
    assert row.settled_at is not None
    assert row.reconciliation_issue is None


def test_successful_settlement_is_idempotent() -> None:
    db, budget = authority()
    reservation_id = budget.reserve("run-1", "demo", 1, 1)

    assert budget.settle_success(reservation_id, 10, 2, "request-1")
    first = reservation(db, reservation_id)
    assert budget.settle_success(reservation_id, 10, 2, "request-1")
    second = reservation(db, reservation_id)

    with db.session() as session:
        ledger = session.get(Budget, 1)
        assert ledger is not None
        assert ledger.demo == 10
    assert second.settled_at == first.settled_at
    assert second.actual_amount == 10


def test_supplemental_provider_uses_its_reserved_prices_not_jev_rates() -> None:
    db, budget = authority(input_rate="0.042", output_rate="0")
    identifier = budget.reserve_estimate(
        "run", "development", 1000, 100, pricing=("0.30", "1.20")
    )
    assert reservation(db, identifier).amount == 420
    assert budget.settle_success(identifier, 100, 20, "deepseek-request")
    row = reservation(db, identifier)
    assert row.actual_amount == 54
    assert row.output_usd_per_million == "1.20"
    with db.session() as session:
        assert session.get(Budget, 1).development == 54


def test_missing_usage_retains_full_reservation_for_reconciliation() -> None:
    db, budget = authority()
    reservation_id = budget.reserve("run-1", "development", 1, 1)
    original = reservation(db, reservation_id).amount

    assert not budget.settle_success(reservation_id, None, 2, "request-1")

    row = reservation(db, reservation_id)
    with db.session() as session:
        ledger = session.get(Budget, 1)
        assert ledger is not None
        assert ledger.development == original
    assert row.settled_at is None
    assert row.actual_amount is None
    assert row.provider_request_id == "request-1"
    assert row.reconciliation_issue == (
        "Provider success did not include valid nonnegative token usage"
    )


def test_usage_above_reservation_retains_amount_and_blocks_new_calls() -> None:
    db, budget = authority()
    reservation_id = budget.reserve("run-1", "development", 1, 1)
    original = reservation(db, reservation_id).amount

    assert not budget.settle_success(reservation_id, original + 1, 0, "request-2")

    row = reservation(db, reservation_id)
    with db.session() as session:
        ledger = session.get(Budget, 1)
        assert ledger is not None
        assert ledger.development == original
    assert row.actual_amount == original + 1
    assert row.input_tokens == original + 1
    assert row.settled_at is None
    assert row.reconciliation_issue == (
        "Reported usage exceeded the conservative reservation"
    )
    with pytest.raises(BudgetUnavailable, match="usage above a reservation"):
        budget.reserve("run-2", "development", 1, 1)


def test_uncertain_outcome_keeps_reservation_and_first_reconciliation_reason() -> None:
    db, budget = authority()
    reservation_id = budget.reserve("run-1", "development", 1, 1)
    original = reservation(db, reservation_id).amount

    budget.retain_for_reconciliation(reservation_id, "Provider outcome uncertain")
    budget.retain_for_reconciliation(reservation_id, "A later duplicate marker")

    row = reservation(db, reservation_id)
    with db.session() as session:
        ledger = session.scalar(select(Budget).where(Budget.id == 1))
        assert ledger is not None
        assert ledger.development == original
    assert row.settled_at is None
    assert row.reconciliation_issue == "Provider outcome uncertain"


def test_settlement_uses_rates_captured_when_request_was_reserved() -> None:
    db, budget = authority(input_rate="1", output_rate="0")
    reservation_id = budget.reserve("run-1", "development", 1, 1)
    budget.settings.input_usd_per_million = "0.001"

    assert budget.settle_success(reservation_id, 10, 0, "request-1")

    row = reservation(db, reservation_id)
    with db.session() as session:
        ledger = session.get(Budget, 1)
        assert ledger is not None
        assert ledger.development == 10
    assert row.input_usd_per_million == "1"
    assert row.actual_amount == 10
