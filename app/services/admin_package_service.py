"""Admin: Orleeno catalogue packages and review of kitchen packages (incl. revisions)."""

from fastapi import UploadFile
from sqlalchemy.orm import Session, selectinload

from app.core.audit import record_audit
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.domain import item_quantity, notify, ratings
from app.domain import package_revision as revision
from app.domain.pricing import validate_package_prices
from app.domain.status import EXTRA_OPEN_STATUSES
from app.models.extra_order_model import ExtraOrder
from app.models.menu_category_model import MenuCategory
from app.models.menu_package_image_model import MenuPackageImage
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.repositories.menu_repository import MenuRepository
from app.services.admin_views import package_admin_view
from app.services.menu_service import active_subscription_count, package_dict
from app.services.package_image_service import MAX_IMAGES
from app.utils.file_helper import delete_upload, save_package_image


def _image_view(i: MenuPackageImage) -> dict:
    return {
        "image_id": i.image_id,
        "image_url": i.image_url,
        "is_primary": bool(i.is_primary),
        "display_order": i.display_order or 0,
        "created_at": i.created_at,
    }


def _images(db: Session, package_id) -> list[dict]:
    rows = (
        db.query(MenuPackageImage)
        .filter(MenuPackageImage.package_reference_id == package_id)
        .order_by(MenuPackageImage.is_primary.desc(), MenuPackageImage.display_order.asc())
        .all()
    )
    return [_image_view(i) for i in rows]


def _package_image(db: Session, package_id, image_id) -> MenuPackageImage:
    image = (
        db.query(MenuPackageImage)
        .filter(MenuPackageImage.image_id == image_id, MenuPackageImage.package_reference_id == package_id)
        .with_for_update()
        .first()
    )
    if image is None:
        raise DomainError("Image not found", 404)
    return image


def _tell_kitchen_about_photos(db: Session, pkg: MenuPackage, what: str) -> None:
    if not pkg.is_predefined and pkg.provider_id:
        notify.kitchen(
            db, pkg.provider_id, "package_update", "Package photos updated",
            f"Orleeno {what} on '{pkg.package_name}'.", {"package_id": str(pkg.package_id)},
        )
def _package(db: Session, package_id, lock: bool = False) -> MenuPackage:
    q = db.query(MenuPackage).filter(MenuPackage.package_id == package_id)
    if lock:
        q = q.with_for_update()
    pkg = q.first()
    if not pkg:
        raise DomainError("Package not found", 404)
    return pkg


def _open_extra_orders(db: Session, package_id) -> int:
    return db.query(ExtraOrder).filter(
        ExtraOrder.package_reference_id == package_id,
        ExtraOrder.status.in_(EXTRA_OPEN_STATUSES),
    ).count()


def _audit_package(db, pkg, before, admin_id, ip, operation="U"):
    record_audit(
        db, table="provider.menu_packages", record_id=pkg.package_id, operation=operation,
        old=before, new=package_admin_view(pkg), actor_id=admin_id, actor_type="admin", ip=ip,
    )


# ── Package Management ────────────────────────────────────

class AdminPackageService:

    @staticmethod
    def create_package(db: Session, payload, admin_id: str, ip: str | None = None):
        category = db.query(MenuCategory).filter(
            MenuCategory.category_id == payload.category_id, MenuCategory.is_active == True  # noqa: E712
        ).first()
        if not category:
            raise DomainError("Invalid category")
        validate_package_prices(payload.price, payload.discounted_price, payload.subscription_price)

        package = MenuRepository.create_package(db, {
            # Catalogue packages belong to Orleeno: no owning kitchen
            "provider_id": None,
            "created_by_admin_id": admin_id,
            "category_reference_id": payload.category_id,
            "package_name": payload.package_name,
            "short_description": payload.short_description,
            "description": payload.description,
            "meal_type": payload.meal_type,
            "food_type": payload.food_type,
            "price": payload.price,
            "discounted_price": payload.discounted_price,
            "is_subscription_available": payload.is_subscription_available,
            "subscription_price": payload.subscription_price,
            "is_predefined": True,
            "is_active": True,
            "is_available": True,
            "approval_status": "approved",
            "approved_at": now_utc(),
            "approved_by": admin_id,
        })
        for order, item in enumerate(payload.items, start=1):
            MenuRepository.create_package_item(db, {
                "package_reference_id": package.package_id,
                "item_name": item.item_name,
                "item_order": order,
                **item_quantity.from_request(item),
            })
        _audit_package(db, package, None, admin_id, ip, operation="I")
        db.commit()
        db.refresh(package)
        return {
            "success": True,
            "message": "Orleeno catalogue package created. Kitchens can now offer it.",
            "package": package_admin_view(package),
        }

    @staticmethod
    def list_packages(db: Session, is_predefined: bool = None, is_active: bool = None,
                      is_subscription_available: bool = None, approval_status: str = None,
                      provider_id: str = None, search: str = None, include_deleted: bool = False,
                      has_pending_changes: bool = None, page: int = 1, limit: int = 20):
        query = db.query(MenuPackage, Provider.business_name).options(selectinload(MenuPackage.images)).outerjoin(
            Provider, Provider.provider_id == MenuPackage.provider_id
        )
        if not include_deleted:
            query = query.filter(MenuPackage.deleted_at.is_(None))
        if is_predefined is not None:
            query = query.filter(MenuPackage.is_predefined == is_predefined)
        if is_active is not None:
            query = query.filter(MenuPackage.is_active == is_active)
        if is_subscription_available is not None:
            query = query.filter(MenuPackage.is_subscription_available == is_subscription_available)
        if approval_status:
            query = query.filter(MenuPackage.approval_status == approval_status)
        if provider_id:
            query = query.filter(MenuPackage.provider_id == provider_id)
        if search:
            query = query.filter(MenuPackage.package_name.ilike(f"%{search}%"))
        if has_pending_changes is not None:
            query = query.filter(
                MenuPackage.pending_changes.isnot(None) if has_pending_changes else MenuPackage.pending_changes.is_(None)
            )

        total = query.count()
        rows = query.order_by(MenuPackage.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        stats = ratings.for_packages(db, (pkg.package_id for pkg, _ in rows))
        return {
            "success": True,
            "total": total,
            "page": page,
            "packages": [
                {**package_admin_view(pkg, None if pkg.is_predefined else name), **stats.get(pkg.package_id, ratings.empty())}
                for pkg, name in rows
            ],
        }

    @staticmethod
    def get_package(db: Session, package_id: str):
        pkg = _package(db, package_id)
        data = package_dict(pkg)
        data.update(package_admin_view(pkg))
        data["images"] = _images(db, pkg.package_id)
        data["active_subscriptions"] = active_subscription_count(db, pkg.package_id)
        data.update(ratings.for_packages(db, [pkg.package_id]).get(pkg.package_id) or ratings.empty())  # UUID key
        data["reviews"] = ratings.recent_reviews(db, pkg.package_id, limit=10)
        return data

    # ── Package photos ─────────────────────────────────────
    # The same photos the kitchen uploads from its app (master.menu_package_images):
    # whatever an admin adds, replaces or reorders here is what the kitchen and
    # customers see, and the other way round.

    @staticmethod
    def upload_image(db: Session, package_id: str, file: UploadFile, admin_id: str, ip: str | None = None,
                     make_primary: bool = False):
        pkg = _package(db, package_id, lock=True)
        if pkg.deleted_at is not None:
            raise DomainError("This package was deleted")
        count = db.query(MenuPackageImage).filter(MenuPackageImage.package_reference_id == pkg.package_id).count()
        if count >= MAX_IMAGES:
            raise DomainError(f"A package can have at most {MAX_IMAGES} photos")
        path = save_package_image(file)
        primary = make_primary or count == 0
        try:
            if primary:
                db.query(MenuPackageImage).filter(MenuPackageImage.package_reference_id == pkg.package_id).update(
                    {"is_primary": False}, synchronize_session=False
                )
            image = MenuPackageImage(
                package_reference_id=pkg.package_id, image_url=path, is_primary=primary, display_order=count + 1,
            )
            db.add(image)
            db.flush()
            record_audit(
                db, table="master.menu_package_images", record_id=image.image_id, operation="I",
                new=_image_view(image), actor_id=admin_id, actor_type="admin", ip=ip,
            )
            _tell_kitchen_about_photos(db, pkg, "added a photo")
            db.commit()
        except Exception:
            db.rollback()
            delete_upload(path)  # never leave an orphan file behind a failed save
            raise
        return {
            "success": True, "message": "Photo uploaded", "image": _image_view(image),
            "images": _images(db, pkg.package_id),
        }

    @staticmethod
    def replace_image(db: Session, package_id: str, image_id, file: UploadFile, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        image = _package_image(db, pkg.package_id, image_id)
        before = _image_view(image)
        old_path = image.image_url
        path = save_package_image(file)
        try:
            image.image_url = path
            record_audit(
                db, table="master.menu_package_images", record_id=image.image_id,
                old=before, new=_image_view(image), actor_id=admin_id, actor_type="admin", ip=ip,
            )
            _tell_kitchen_about_photos(db, pkg, "replaced a photo")
            db.commit()
        except Exception:
            db.rollback()
            delete_upload(path)
            raise
        delete_upload(old_path)
        return {
            "success": True, "message": "Photo replaced", "image": _image_view(image),
            "images": _images(db, pkg.package_id),
        }

    @staticmethod
    def set_primary_image(db: Session, package_id: str, image_id, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        image = _package_image(db, pkg.package_id, image_id)
        db.query(MenuPackageImage).filter(MenuPackageImage.package_reference_id == pkg.package_id).update(
            {"is_primary": False}, synchronize_session=False
        )
        image.is_primary = True
        record_audit(
            db, table="master.menu_package_images", record_id=image.image_id,
            new={"event": "set_primary"}, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "message": "Cover photo updated", "images": _images(db, pkg.package_id)}

    @staticmethod
    def delete_image(db: Session, package_id: str, image_id, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        image = _package_image(db, pkg.package_id, image_id)
        before = _image_view(image)
        was_primary, path = image.is_primary, image.image_url
        db.delete(image)
        db.flush()
        if was_primary:
            nxt = (
                db.query(MenuPackageImage)
                .filter(MenuPackageImage.package_reference_id == pkg.package_id)
                .order_by(MenuPackageImage.display_order.asc())
                .first()
            )
            if nxt:
                nxt.is_primary = True
        record_audit(
            db, table="master.menu_package_images", record_id=before["image_id"], operation="D",
            old=before, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        _tell_kitchen_about_photos(db, pkg, "removed a photo")
        db.commit()
        delete_upload(path)
        return {"success": True, "message": "Photo removed", "images": _images(db, pkg.package_id)}

    @staticmethod
    def set_approval(db: Session, package_id: str, *, approve: bool, note: str | None, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        if pkg.deleted_at is not None:
            raise DomainError("This package was deleted")
        if pkg.approval_status == "approved" and pkg.pending_changes:
            return AdminPackageService._review_revision(db, pkg, approve=approve, note=note, admin_id=admin_id, ip=ip)
        before = package_admin_view(pkg)

        if approve:
            if not pkg.items:
                raise DomainError("A package needs at least one item before it can be approved")
            validate_package_prices(pkg.price, pkg.discounted_price, pkg.subscription_price)
            pkg.approval_status = "approved"
            pkg.approval_note = note
            pkg.approved_at = now_utc()
            pkg.approved_by = admin_id
            pkg.is_active = True
        else:
            if not note:
                raise DomainError("Give the kitchen a reason for the rejection")
            pkg.approval_status = "rejected"
            pkg.approval_note = note
            pkg.approved_at = None
            pkg.approved_by = None
            pkg.is_active = False

        _audit_package(db, pkg, before, admin_id, ip)
        if not pkg.is_predefined:
            notify.kitchen(
                db, pkg.provider_id, "package_update",
                "Package approved" if approve else "Package needs changes",
                f"'{pkg.package_name}' is approved and live." if approve
                else f"'{pkg.package_name}' was not approved: {note}",
                {"package_id": str(pkg.package_id)},
            )
        db.commit()
        running = active_subscription_count(db, pkg.package_id)
        message = "Package approved and live" if approve else "Package rejected"
        if not approve and running:
            message += f"; {running} running subscription(s) continue at their booked price"
        return {"success": True, "message": message, "package": package_admin_view(pkg)}

    @staticmethod
    def _review_revision(db: Session, pkg, *, approve: bool, note: str | None, admin_id: str, ip: str | None):
        """A kitchen's edit of a live package: swap it in, or discard it. The package stays on sale either way."""
        before = package_admin_view(pkg)
        if approve:
            validate_package_prices(
                revision.proposed(pkg, "price"),
                revision.proposed(pkg, "discounted_price"),
                revision.proposed(pkg, "subscription_price"),
            )
            revision.apply(db, pkg)
            pkg.approval_note = note
            pkg.approved_at = now_utc()
            pkg.approved_by = admin_id
            title, body = "Package changes approved", f"Your changes to '{pkg.package_name}' are now live."
        else:
            if not note:
                raise DomainError("Give the kitchen a reason for the rejection")
            revision.discard(pkg)
            title = "Package changes not approved"
            body = f"Your changes to '{pkg.package_name}' were not approved: {note} The current version stays on sale."
        _audit_package(db, pkg, before, admin_id, ip)
        notify.kitchen(db, pkg.provider_id, "package_update", title, body, {"package_id": str(pkg.package_id)})
        db.commit()
        return {
            "success": True,
            "message": "Package changes approved and live" if approve else "Package changes rejected; the live version is unchanged",
            "package": package_admin_view(pkg),
        }

    @staticmethod
    def update_package(db: Session, package_id: str, payload, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        if pkg.deleted_at is not None:
            raise DomainError("This package was deleted")
        before = package_admin_view(pkg)
        data = payload.model_dump(exclude_unset=True)

        for key in ("discounted_price", "subscription_price"):
            if key in data and data[key] is not None and data[key] <= 0:
                data[key] = None
        for key in ("package_name", "meal_type", "food_type", "price"):
            if key in data and data[key] is None:
                raise DomainError(f"{key} cannot be empty")

        price = data.get("price", pkg.price)
        discounted = data["discounted_price"] if "discounted_price" in data else pkg.discounted_price
        sub_price = data["subscription_price"] if "subscription_price" in data else pkg.subscription_price
        validate_package_prices(price, discounted, sub_price)
        if data.get("is_active") and pkg.approval_status != "approved":
            raise DomainError("Approve the package to make it live")

        for key, value in data.items():
            setattr(pkg, key, value)

        _audit_package(db, pkg, before, admin_id, ip)
        db.commit()
        db.refresh(pkg)
        running = active_subscription_count(db, pkg.package_id)
        return {
            "success": True,
            "message": "Package updated. Running subscriptions keep the price they were booked at."
            if running else "Package updated",
            "active_subscriptions_unaffected": running,
            "package": package_admin_view(pkg),
        }

    @staticmethod
    def set_subscription_availability(db: Session, package_id: str, payload, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        before = package_admin_view(pkg)
        enable = payload.is_subscription_available

        if payload.subscription_price is not None:
            validate_package_prices(pkg.price, pkg.discounted_price, payload.subscription_price)
            pkg.subscription_price = payload.subscription_price
        # without a subscription price, subscriptions are charged the selling price

        pkg.is_subscription_available = enable
        _audit_package(db, pkg, before, admin_id, ip)
        db.commit()
        db.refresh(pkg)
        return {
            "success": True,
            "message": (
                "Package is now available for subscription" if enable
                else "Package subscription disabled; new subscriptions and switches to it are blocked"
            ),
            "active_subscriptions_unaffected": 0 if enable else active_subscription_count(db, pkg.package_id),
            "package": package_admin_view(pkg),
        }

    @staticmethod
    def delete_package(db: Session, package_id: str, admin_id: str, ip: str | None = None):
        pkg = _package(db, package_id, lock=True)
        if pkg.deleted_at is not None:
            return {"success": True, "message": "Package already deleted"}

        running = active_subscription_count(db, pkg.package_id)
        if running:
            raise DomainError(
                f"Cannot delete: package is in {running} running subscription(s). Deactivate it instead."
            )
        open_orders = _open_extra_orders(db, pkg.package_id)
        if open_orders:
            raise DomainError(f"Cannot delete: {open_orders} one-time order(s) for this package are still open.")

        before = package_admin_view(pkg)
        # Soft delete: past orders, reviews and price snapshots keep their reference
        pkg.deleted_at = now_utc()
        pkg.is_active = False
        pkg.is_available = False
        _audit_package(db, pkg, before, admin_id, ip, operation="D")
        db.commit()
        return {"success": True, "message": "Package deleted"}


# ── Subscription Plan Management ──────────────────────────

