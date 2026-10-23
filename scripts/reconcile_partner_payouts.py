"""
Review every delivery partner payout ever credited (read-only).

    python scripts/reconcile_partner_payouts.py              # summary + all findings as JSON
    python scripts/reconcile_partner_payouts.py --csv out.csv  # also write the findings as CSV

It connects with the backend's configuration (DATABASE_URL or the DB_* settings
in .env) inside a READ ONLY transaction, so it cannot change anything. It lists
duplicate credits, completed deliveries that were never paid, credits for
deliveries that did not complete (failed hand-overs were paid before
2026-10-24) and how many credits differ from today's configured payout.

What to do with the findings is a business decision: an admin posts a wallet
adjustment with a note for each delivery that needs correcting (Admin ->
Delivery partner -> Wallet), so the original credit and the correction both
stay in the ledger. This script never edits balances.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.domain import payout_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", help="write every finding to this CSV file")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        report = payout_audit.review(db, sample=None)
    finally:
        db.rollback()
        db.close()

    print(json.dumps(report, indent=2, default=str))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(["finding", "reference", "delivery_boy_id", "amount", "detail"])
            for d in report["duplicate_payouts"]["sample"]:
                writer.writerow(["duplicate_payout", d["delivery"], d["delivery_boy_id"], d["total"],
                                 f"{d['credits']} credits: {' '.join(d['transaction_ids'])}"])
            for ref in report["delivered_without_payout"]["sample"]:
                writer.writerow(["delivered_without_payout", ref, "", "", ""])
            for p in report["paid_but_not_delivered"]["sample"]:
                writer.writerow(["paid_but_not_delivered", f"{p['reference_type']}:{p['reference_id']}",
                                 p["delivery_boy_id"], p["amount"], f"status {p['order_status']}"])
        print(f"\nFindings written to {args.csv}", file=sys.stderr)

    problems = report["duplicate_payouts"]["count"] + report["delivered_without_payout"]["count"]
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
