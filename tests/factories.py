"""Small builders for test data. Each returns ORM rows plus a ready auth header."""

import itertools
import uuid
from decimal import Decimal

from app.core.clock import now_utc
from app.core.security import create_access_token, hash_password
from app.domain import ledger
from app.models.admin_user_model import AdminUser
from app.models.delivery_boy_document_model import DeliveryBoyDocument
from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_boy_payout_model import DeliveryBoyPayoutDetails
from app.models.menu_category_model import MenuCategory
from app.models.menu_package_item_model import MenuPackageItem
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.serviceable_pincode_model import ServiceablePincode
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.user_address_model import UserAddress
from app.models.user_model import User

PIN = 560001
PASSWORD = "Secret@123"
_seq = itertools.count(1)


def _mobile() -> str:
    return f"9{next(_seq):09d}"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def pincode(db, pin=PIN, active=True):
    row = ServiceablePincode(pincode=pin, city="Bengaluru", state="Karnataka", is_active=active)
    db.add(row)
    db.commit()
    return row


def category(db):
    row = MenuCategory(category_name=f"Meals {next(_seq)}", category_slug=f"meals-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(row)
    db.commit()
    return row


def admin(db, role="super_admin"):
    row = AdminUser(
        full_name="Test Admin", email=f"admin{next(_seq)}@orleeno.test",
        password_hash=hash_password(PASSWORD), role=role, is_active=True,
    )
    db.add(row)
    db.commit()
    token = create_access_token({"admin_id": str(row.admin_user_id)}, role="admin", token_version=0)
    return row, auth(token)


def provider(db, *, approved=True, pin=PIN, quota=None, accepting=True, active=True, complete=True):
    row = Provider(
        mobile_number=_mobile(), hashed_password=hash_password(PASSWORD), is_mobile_verified=True,
        is_active=active, is_accepting_orders=accepting,
    )
    if complete:
        row.full_name = "Asha Cook"
        row.business_name = f"Asha Kitchen {next(_seq)}"
        row.kitchen_type = "home"
        row.meal_service_type = "Full Day"
        row.daily_meal_quota = quota or 100
        row.house_no = "12"
        row.address = "MG Road"
        row.area = "Central"
        row.city = "Bengaluru"
        row.state = "Karnataka"
        row.pincode = pin
        row.is_profile_completed = True
    row.approval_status = "approved" if approved else "pending"
    if quota is not None:
        row.daily_meal_quota = quota
    db.add(row)
    db.commit()
    token = create_access_token({"provider_id": str(row.provider_id)}, role="provider", token_version=0)
    return row, auth(token)


def package(db, kitchen, cat, *, price="180", discounted=None, sub_price=None, meal_type="lunch",
            approved=True, capacity=None, predefined=False, sub_available=True, food_type="veg"):
    pkg = MenuPackage(
        provider_id=kitchen.provider_id if kitchen is not None else uuid.uuid4(),
        category_reference_id=cat.category_id,
        package_name=f"Thali {next(_seq)}",
        meal_type=meal_type,
        food_type=food_type,
        price=Decimal(price),
        discounted_price=Decimal(discounted) if discounted else None,
        subscription_price=Decimal(sub_price) if sub_price else (Decimal(price) if sub_available else None),
        is_subscription_available=sub_available,
        is_available=True,
        is_active=approved,
        is_predefined=predefined,
        approval_status="approved" if approved else "pending",
    )
    db.add(pkg)
    db.flush()
    db.add(MenuPackageItem(package_reference_id=pkg.package_id, item_name="Rice", quantity="1 bowl", item_order=1))
    if kitchen is not None:
        db.add(ProviderSelectedPackage(provider_id=kitchen.provider_id, package_id=pkg.package_id, daily_capacity=capacity))
    db.commit()
    return pkg


def offer(db, kitchen, pkg, capacity=None):
    db.add(ProviderSelectedPackage(provider_id=kitchen.provider_id, package_id=pkg.package_id, daily_capacity=capacity))
    db.commit()


def plan(db, *, sub_type="weekly", slot="lunch", days=7, discount="0", skips=2):
    row = SubscriptionPlan(
        subscription_type=sub_type, meal_slot=slot, duration_days=days,
        discount_percent=Decimal(discount), free_skips=skips, is_active=True,
    )
    db.add(row)
    db.commit()
    return row


def customer(db, *, balance="0", pin=PIN, status="active"):
    user = User(
        phone=_mobile(), password_hash=hash_password(PASSWORD), phone_verified=True,
        full_name="Ravi Kumar", status=status, is_profile_completed=True,
    )
    db.add(user)
    db.flush()
    address = UserAddress(
        user_reference_id=user.user_id, label="Home", address_line1="1 Residency Road",
        city="Bengaluru", state="Karnataka", pin_code=str(pin), is_default=True, is_active=True,
    )
    db.add(address)
    if Decimal(balance) > 0:
        ledger.post_customer(
            db, user.user_id, type="credit", amount=Decimal(balance), reason="adjustment",
            idempotency_key=f"test_seed:{user.user_id}",
        )
    db.commit()
    token = create_access_token({"user_id": str(user.user_id)}, role="customer", token_version=0)
    return user, address, auth(token)


def delivery_boy(db, *, approved=True, kitchen=None, online=True, documents=True):
    boy = DeliveryBoy(
        mobile_number=_mobile(), hashed_password=hash_password(PASSWORD), is_mobile_verified=True,
        full_name="Kiran Rider", email="kiran@example.com", gender="male", is_active=True,
        is_online=online, vehicle_type="bike", vehicle_number="KA01AB1234",
        assigned_provider_reference_id=kitchen.provider_id if kitchen is not None else None,
        approval_status="approved" if approved else "pending",
    )
    boy.date_of_birth = now_utc().date().replace(year=1995)
    db.add(boy)
    db.flush()
    if documents:
        for t in ("aadhaar", "pan", "driving_license", "vehicle_rc"):
            db.add(DeliveryBoyDocument(
                delivery_boy_reference_id=boy.delivery_boy_id, document_type=t,
                file_url=f"uploads/delivery_boys/documents/{uuid.uuid4()}.jpg",
                status="verified" if approved else "pending",
            ))
        db.add(DeliveryBoyPayoutDetails(delivery_boy_reference_id=boy.delivery_boy_id, upi_id="kiran@upi"))
    db.commit()
    token = create_access_token({"delivery_boy_id": str(boy.delivery_boy_id)}, role="delivery_boy", token_version=0)
    return boy, auth(token)


def world(db, *, price="180", discounted=None, sub_price=None, meal_type="lunch", balance="5000",
          plan_slot="lunch", plan_days=7, discount="0", skips=2, quota=None, capacity=None):
    """A sellable kitchen + package + plan + customer with money, all in one pincode."""
    pincode(db)
    cat = category(db)
    kitchen, kitchen_auth = provider(db, quota=quota)
    pkg = package(db, kitchen, cat, price=price, discounted=discounted, sub_price=sub_price,
                  meal_type=meal_type, capacity=capacity)
    pl = plan(db, slot=plan_slot, days=plan_days, discount=discount, skips=skips)
    user, address, user_auth = customer(db, balance=balance)
    return {
        "category": cat, "kitchen": kitchen, "kitchen_auth": kitchen_auth, "package": pkg, "plan": pl,
        "user": user, "address": address, "user_auth": user_auth,
    }
