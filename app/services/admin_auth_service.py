from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.admin_user_model import AdminUser
from app.core.security import verify_password, hash_password, create_access_token


class AdminAuthService:

    @staticmethod
    def login(db: Session, email: str, password: str):
        admin = db.query(AdminUser).filter(AdminUser.email == email).first()

        if not admin:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not admin.is_active:
            raise HTTPException(status_code=403, detail="Admin account is deactivated")
        if not verify_password(password, admin.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        admin.last_login_at = datetime.now(timezone.utc)
        db.commit()

        token = create_access_token({
            "admin_id": str(admin.admin_user_id),
            "email": admin.email,
            "role": admin.role or "admin",
        })

        return {
            "success": True,
            "message": "Login successful",
            "admin_id": admin.admin_user_id,
            "role": admin.role,
            "access_token": token,
            "token_type": "bearer"
        }

    @staticmethod
    def get_profile(db: Session, admin_id: str):
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        return {
            "success": True,
            "admin": {
                "admin_user_id": str(admin.admin_user_id),
                "full_name": admin.full_name,
                "email": admin.email,
                "role": admin.role,
                "is_active": admin.is_active,
                "last_login_at": admin.last_login_at,
                "created_at": admin.created_at,
            },
        }

    @staticmethod
    def change_password(db: Session, admin_id: str, payload):
        admin = db.query(AdminUser).filter(AdminUser.admin_user_id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")
        if not verify_password(payload.current_password, admin.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        admin.password_hash = hash_password(payload.new_password)
        db.commit()

        return {"success": True, "message": "Password changed successfully"}

    @staticmethod
    async def logout_admin():

        return {
            "success": True,
            "message": "Logged out successfully"
        }
