from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_dashboard_service import AdminDashboardService

router = APIRouter()


@router.get(
    "",
    summary="Admin Dashboard Overview",
    description=(
        "**Fetch high-level platform statistics for the admin dashboard.**\n\n"
        "Returns key metrics including:\n"
        "- Total users, providers, delivery boys\n"
        "- Active subscriptions count\n"
        "- Orders delivered today\n"
        "- Revenue / wallet totals\n\n"
        "**When to call:** On every admin panel load or dashboard screen. "
        "Refresh periodically to keep metrics current."
    )
)
def get_dashboard(
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDashboardService.get_stats(db)
