from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_dashboard_service import AdminDashboardService

router = APIRouter()


@router.get("")
def get_dashboard(
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminDashboardService.get_stats(db)
