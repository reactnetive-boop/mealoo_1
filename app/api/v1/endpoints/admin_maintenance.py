from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import require_super_admin
from app.domain import maintenance

router = APIRouter()


@router.get(
    "/reconciliation",
    summary="Money and Pipeline Reconciliation",
    description=(
        "Read-only health report: every wallet balance against its ledger, negative balances, "
        "delivered orders not settled (or settled twice), meals stuck with a partner from earlier days, "
        "withdrawals waiting too long, and platform ledger totals. The same check runs every night. "
        "**super_admin**."
    ),
)
def reconciliation(db: Session = Depends(get_db), current=Depends(require_super_admin)):
    return {"success": True, **maintenance.reconcile(db)}


@router.post(
    "/purge",
    summary="Run Data Retention Now",
    description=(
        "Deletes expired OTP rows and long-read notifications and prepares audit-log partitions "
        "(the nightly job does the same). Ledgers, orders and payments are never deleted. **super_admin**."
    ),
)
def purge(request: Request, db: Session = Depends(get_db), current=Depends(require_super_admin)):
    result = maintenance.purge(db)
    record_audit(
        db, table="maintenance.purge", operation="D", new=result,
        actor_id=current["admin_id"], actor_type="admin", ip=client_ip(request),
    )
    db.commit()
    return {"success": True, **result}
