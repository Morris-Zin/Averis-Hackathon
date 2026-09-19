"""Explicit operator utilities. Paid processing still goes through the shared ledger."""
import argparse
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select

from averis.config import Settings
from averis.persistence import Budget, Database, Run
from averis.processing import Processor
from averis.storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init-budget", "budget", "run-pending", "reconcile", "metrics"])
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--confirm-starting-usage", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    db = Database(settings.database_url)
    if args.command == "init-budget":
        if not args.confirm_starting_usage or not settings.budget_verified:
            parser.error("Verify billing first, set AVERIS_BUDGET_VERIFIED=true and confirm starting usage.")
        previous = Decimal(settings.prior_spend_usd)
        if not previous.is_finite() or not 0 <= previous <= 7:
            parser.error("Verified previous spend must be between $0 and $7.")
        with db.session() as session, session.begin():
            if session.get(Budget, 1) is not None:
                parser.error("Budget already initialized. This command never resets spending.")
            session.add(Budget(id=1, prior_spend=int((previous * 1_000_000).to_integral_value(rounding=ROUND_CEILING)),
                               development=0, demo=0))
        print("Verified starting usage recorded. No provider request was made.")
    elif args.command == "budget":
        with db.session() as session:
            ledger = session.get(Budget, 1)
            if ledger is None:
                print("Not initialized; paid calls fail closed.")
            else:
                print({"prior_usd": ledger.prior_spend / 1_000_000,
                       "development_reserved_usd": ledger.development / 1_000_000,
                       "demo_reserved_usd": ledger.demo / 1_000_000,
                       "ceiling_usd": 7})
    else:
        processor = Processor(db, settings, Storage(settings))
        if args.command == "metrics":
            print(processor.metrics())
        elif args.command == "reconcile":
            print({"dispatched": processor.reconcile()})
        else:
            if not 1 <= args.limit <= 50:
                parser.error("Choose a batch limit between 1 and 50.")
            if not settings.live_enabled or not settings.budget_verified:
                parser.error("Live processing is disabled. Configure and verify the shared allowance first.")
            with db.session() as session:
                run_ids = session.scalars(select(Run.id).where(Run.status == "queued")
                                          .order_by(Run.created_at).limit(args.limit)).all()
            for run_id in run_ids:
                print({"run_id": run_id, "status": processor.execute(run_id)}, flush=True)


if __name__ == "__main__":
    main()
