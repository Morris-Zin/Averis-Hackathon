"""Global budget authority. Uncertain calls retain the full reservation."""

from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import TypeGuard

from sqlalchemy import select

from averis.config import Settings
from averis.persistence import Budget, Database, Reservation, utcnow

_MAX_REPORTED_TOKENS = 2_147_483_647
_USAGE_EXCEEDED_ISSUE = "Reported usage exceeded the conservative reservation"


class BudgetUnavailable(RuntimeError):
    pass


class BudgetAuthority:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def reserve(
        self, run_id: str, purpose: str, payload_bytes: int, questions: int
    ) -> str:
        settings = self.settings
        if not settings.live_enabled or not settings.budget_verified:
            raise BudgetUnavailable(
                "Live AI disabled until starting usage and billing are verified"
            )
        input_rate, output_rate = self._verified_rates()
        if not 0 <= payload_bytes <= 100_000 or not 1 <= questions <= 10:
            raise BudgetUnavailable("Request exceeds the bounded inference envelope")
        # UTF-8 bytes upper-bound token count, with repeated-question/context overhead.
        input_bound = payload_bytes * (questions + 1) * 2 + 32768
        output_bound = 32768
        amount = int(
            (input_bound * input_rate + output_bound * output_rate).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        with self.db.session() as session, session.begin():
            row = session.scalar(select(Budget).where(Budget.id == 1).with_for_update())
            if row is None:
                raise BudgetUnavailable(
                    "Initialize the verified budget ledger before inference"
                )
            unresolved_overage = session.scalar(
                select(Reservation.id)
                .where(
                    Reservation.settled_at.is_(None),
                    Reservation.reconciliation_issue == _USAGE_EXCEEDED_ISSUE,
                )
                .limit(1)
            )
            if unresolved_overage is not None:
                raise BudgetUnavailable(
                    "Inference disabled until usage above a reservation is reconciled"
                )
            previous = Decimal(settings.prior_spend_usd)
            if not previous.is_finite() or not 0 <= previous <= 7:
                raise BudgetUnavailable("Starting usage is invalid")
            prior = int(
                (previous * 1_000_000).to_integral_value(rounding=ROUND_CEILING)
            )
            if row.prior_spend != prior:
                raise BudgetUnavailable(
                    "Starting usage does not match the verified ledger"
                )
            if purpose not in {"demo", "development"}:
                raise BudgetUnavailable("Unknown budget purpose")
            used = row.demo if purpose == "demo" else row.development
            limit = 2_000_000 if purpose == "demo" else 5_000_000 - prior
            if (
                used + amount > limit
                or row.demo + row.development + prior + amount > 7_000_000
            ):
                raise BudgetUnavailable(
                    "Jev allowance exhausted; saved results remain available"
                )
            if purpose == "demo":
                row.demo += amount
            else:
                row.development += amount
            reservation = Reservation(
                run_id=run_id,
                purpose=purpose,
                amount=amount,
                input_usd_per_million=str(input_rate),
                output_usd_per_million=str(output_rate),
            )
            session.add(reservation)
            session.flush()
            return reservation.id

    def settle_success(
        self,
        reservation_id: str,
        input_tokens: int | None,
        output_tokens: int | None,
        request_id: str | None = None,
    ) -> bool:
        """Replace a successful call's reservation with verified reported usage.

        False means the conservative reservation remains charged and the row records
        why an operator should reconcile it.
        """

        with self.db.session() as session, session.begin():
            # Reserve and settle lock the singleton ledger first. This serializes the
            # fail-closed overage check with new provider reservations.
            budget = session.scalar(
                select(Budget).where(Budget.id == 1).with_for_update()
            )
            reservation = session.scalar(
                select(Reservation)
                .where(Reservation.id == reservation_id)
                .with_for_update()
            )
            if reservation is None:
                raise BudgetUnavailable("Unknown inference reservation")
            if reservation.settled_at is not None:
                return True

            reservation.provider_request_id = self._safe_request_id(request_id)
            if not self._valid_token_count(input_tokens) or not self._valid_token_count(
                output_tokens
            ):
                reservation.reconciliation_issue = (
                    "Provider success did not include valid nonnegative token usage"
                )
                return False
            reservation.input_tokens = input_tokens
            reservation.output_tokens = output_tokens

            try:
                input_rate, output_rate = self._parse_rates(
                    reservation.input_usd_per_million,
                    reservation.output_usd_per_million,
                )
            except BudgetUnavailable:
                reservation.reconciliation_issue = (
                    "Reserved provider pricing was unavailable during settlement"
                )
                return False
            actual = int(
                (
                    input_tokens * input_rate + output_tokens * output_rate
                ).to_integral_value(rounding=ROUND_CEILING)
            )
            reservation.actual_amount = actual
            if actual > reservation.amount:
                reservation.reconciliation_issue = _USAGE_EXCEEDED_ISSUE
                return False

            if budget is None:
                reservation.reconciliation_issue = (
                    "Budget ledger was unavailable during settlement"
                )
                return False
            if reservation.purpose == "demo":
                current = budget.demo
            elif reservation.purpose == "development":
                current = budget.development
            else:
                reservation.reconciliation_issue = (
                    "Reservation has an unknown budget purpose"
                )
                return False
            if current < reservation.amount:
                reservation.reconciliation_issue = (
                    "Budget ledger is lower than the recorded reservation"
                )
                return False

            released = reservation.amount - actual
            if reservation.purpose == "demo":
                budget.demo -= released
            else:
                budget.development -= released
            reservation.reconciliation_issue = None
            reservation.settled_at = utcnow()
            return True

    def retain_for_reconciliation(self, reservation_id: str, issue: str) -> None:
        """Record an uncertain provider outcome without releasing its reservation."""

        with self.db.session() as session, session.begin():
            reservation = session.scalar(
                select(Reservation)
                .where(Reservation.id == reservation_id)
                .with_for_update()
            )
            if reservation is None:
                raise BudgetUnavailable("Unknown inference reservation")
            if (
                reservation.settled_at is None
                and reservation.reconciliation_issue is None
            ):
                reservation.reconciliation_issue = issue

    def _verified_rates(self) -> tuple[Decimal, Decimal]:
        return self._parse_rates(
            self.settings.input_usd_per_million,
            self.settings.output_usd_per_million,
        )

    @staticmethod
    def _parse_rates(
        input_value: str | None, output_value: str | None
    ) -> tuple[Decimal, Decimal]:
        if input_value is None or output_value is None:
            raise BudgetUnavailable("Verified provider pricing required")
        try:
            input_rate = Decimal(input_value)
            output_rate = Decimal(output_value)
        except (InvalidOperation, ValueError) as error:
            raise BudgetUnavailable("Verified provider pricing required") from error
        if (
            not input_rate.is_finite()
            or not output_rate.is_finite()
            or input_rate <= 0
            or output_rate < 0
        ):
            raise BudgetUnavailable("Verified provider pricing required")
        return input_rate, output_rate

    @staticmethod
    def _valid_token_count(value: int | None) -> TypeGuard[int]:
        return type(value) is int and 0 <= value <= _MAX_REPORTED_TOKENS

    @staticmethod
    def _safe_request_id(value: str | None) -> str | None:
        return value if value is not None and 0 < len(value) <= 255 else None
