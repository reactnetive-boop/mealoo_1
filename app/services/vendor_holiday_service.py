"""
Kitchen holidays: the approved schedule and the changes applied to it.

A kitchen never changes its holidays directly: it sends a request that an
admin approves or rejects (app/services/holiday_request_service.py). The
functions here APPLY an approved change (or an admin's own change):

Regular (casual) holidays are rules; adding or editing one re-plans the
kitchen's running subscriptions in the same transaction
(app/domain/holiday_policy.py). Emergency holidays close one date (today or
later); the day's meals are refunded and every active subscription gets an
extra free skip (app/domain/emergency_holiday.py). Past holidays are
history: they cannot be edited or removed. Every change is audited.

commit=False lets the approval of a request apply the change and record the
decision in one transaction.
"""

import uuid
from collections import Counter
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.audit import business_event, record_audit
from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.domain import emergency_holiday, holiday_notices, holiday_policy, holidays
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.user_model import User
from app.models.vendor_holiday_model import (
    HolidayNotice, VendorHoliday, VendorHolidayMeal, VendorHolidayRequest, VendorHolidaySubscription,
)

CALENDAR_PAST_DAYS = 30
CALENDAR_DAYS = 120


def _rule_view(h: VendorHoliday) -> dict:
    today = today_local()
    finished = h.end_date is not None and h.end_date <= today
    return {
        "holiday_id": h.vendor_holiday_id,
        "holiday_type": h.holiday_type,
        "rule_type": h.rule_type,
        "weekdays": sorted(h.weekdays or []),
        "month_days": sorted(h.month_days or []),
        "dates": sorted(h.dates or []),
        "start_date": h.start_date,
        "end_date": h.end_date,
        "reason": h.reason,
        "label": holidays.describe(h),
        "status": h.status,
        "removed_at": h.removed_at,
        "processing_status": h.processing_status,
        "affected_subscriptions": h.affected_subscriptions,
        "affected_meals": h.affected_meals,
        "replaced_meals": h.replaced_meals,
        "compensated_meals": h.compensated_meals,
        "failed_meals": h.failed_meals,
        "created_by_type": h.created_by_type,
        "created_at": h.created_at,
        # past holidays are history
        "editable": h.holiday_type == holidays.CASUAL and h.status == "active" and not finished
                    and h.removed_at is None,
    }


def _owned(db: Session, provider_id, holiday_id) -> VendorHoliday:
    h = db.query(VendorHoliday).filter(
        VendorHoliday.vendor_holiday_id == holiday_id, VendorHoliday.provider_reference_id == provider_id,
    ).with_for_update().first()
    if h is None:
        raise DomainError("Holiday not found", 404)
    return h


def _lock_kitchen(db: Session, provider_id) -> Provider:
    kitchen = db.query(Provider).filter(Provider.provider_id == provider_id).with_for_update().first()
    if kitchen is None:
        raise DomainError("Kitchen not found", 404)
    return kitchen


def _calendar(db: Session, provider_id) -> list[dict]:
    today = today_local()
    start, end = today - timedelta(days=CALENDAR_PAST_DAYS), today + timedelta(days=CALENDAR_DAYS)
    days = holidays.closures(db, [provider_id], start, end).get(holidays._uuid(provider_id), {})
    return [
        {
            "date": d,
            "unavailable_date": d,  # older app versions
            "holiday_id": h.vendor_holiday_id,
            "holiday_type": h.holiday_type,
            "label": holidays.CASUAL_LABEL if h.holiday_type == holidays.CASUAL else holidays.EMERGENCY_LABEL,
            "rule_label": holidays.describe(h),
            "reason": h.reason,
            "is_past": d < today,
            "editable": h.holiday_type == holidays.CASUAL and d > today,
        }
        for d, h in sorted(days.items())
    ]


def _payload(payload) -> dict:
    data = payload if isinstance(payload, dict) else payload.model_dump(exclude_unset=True)
    return {k: v for k, v in data.items() if v is not None}


def _transient(provider_id, rule: dict) -> VendorHoliday:
    return VendorHoliday(provider_reference_id=provider_id, holiday_type=holidays.CASUAL, **rule)


class VendorHolidayService:

    # ── Kitchen: read ─────────────────────────────────────

    @staticmethod
    def overview(db: Session, provider_id) -> dict:
        today = today_local()
        rules = (
            db.query(VendorHoliday)
            .filter(VendorHoliday.provider_reference_id == provider_id)
            .order_by(VendorHoliday.start_date.desc(), VendorHoliday.created_at.desc())
            .limit(200)
            .all()
        )
        calendar = _calendar(db, provider_id)
        casual = [r for r in rules if r.holiday_type == holidays.CASUAL and r.status == "active"]
        current = [r for r in casual if (r.end_date is None or r.end_date > today) and r.removed_at is None]
        from app.services.holiday_request_service import request_view

        requests = (
            db.query(VendorHolidayRequest)
            .filter(VendorHolidayRequest.provider_reference_id == provider_id)
            .order_by(VendorHolidayRequest.created_at.desc())
            .limit(50)
            .all()
        )
        pending = [r for r in requests if r.status == "pending"]
        changing = {r.target_holiday_id: r for r in pending if r.target_holiday_id is not None}
        targets = {h.vendor_holiday_id: h for h in rules}

        def rule_with_request(r: VendorHoliday) -> dict:
            req = changing.get(r.vendor_holiday_id)
            return {**_rule_view(r), "pending_request": request_view(req, targets) if req else None}

        return {
            "success": True,
            "timezone": "Asia/Kolkata",
            "today": today,
            "is_holiday_today": any(c["date"] == today for c in calendar),
            # for the "set your regular weekly holidays?" question
            "weekly_holiday_set": any(r.rule_type == "weekly" for r in current),
            "regular_holidays": [holidays.describe(r) for r in current if r.rule_type in ("weekly", "monthly")],
            # approved weekly days off now in force, e.g. [7] = every Sunday
            "weekly_off_days": sorted({d for r in current if r.rule_type == "weekly" for d in (r.weekdays or [])}),
            "rules": [rule_with_request(r) for r in current],
            "past_rules": [_rule_view(r) for r in casual if r not in current][:50],
            "emergencies": [_rule_view(r) for r in rules if r.holiday_type == holidays.EMERGENCY][:50],
            # holiday changes waiting for Orleeno, and the decisions taken
            "pending_requests": [request_view(r, targets) for r in pending],
            "requests": [request_view(r, targets) for r in requests],
            "requires_approval": True,
            "calendar": calendar,
            "upcoming": [c for c in calendar if c["date"] >= today],
            # older app versions read `holidays` (one row per date)
            "holidays": calendar,
            "total": len(calendar),
        }

    @staticmethod
    def affected_orders(db: Session, provider_id, holiday_id) -> dict:
        h = db.query(VendorHoliday).filter(
            VendorHoliday.vendor_holiday_id == holiday_id, VendorHoliday.provider_reference_id == provider_id,
        ).first()
        if h is None:
            raise DomainError("Holiday not found", 404)
        if h.holiday_type == holidays.EMERGENCY:
            meals = _meal_rows(db, h.vendor_holiday_id)
        else:
            orders = db.query(Order).filter(Order.vendor_holiday_reference_id == h.vendor_holiday_id).all()
            meals = [
                {"order_id": o.order_id, "subscription_id": o.subscription_reference_id, "meal_date": o.order_date,
                 "meal_slot": o.meal_slot, "outcome": "moved_to_plan_end", "status": o.status}
                for o in sorted(orders, key=lambda o: (o.order_date, o.meal_slot))
            ]
        return {"success": True, "holiday": _rule_view(h), "total": len(meals), "meals": meals}

    # ── Kitchen: casual holidays ──────────────────────────

    @staticmethod
    def preview_casual(db: Session, provider_id, payload) -> dict:
        rule = holidays.normalize_rule(_payload(payload))
        draft = _transient(provider_id, rule)
        return {"success": True, "label": holidays.describe(draft), **holiday_policy.preview(db, draft)}

    @staticmethod
    def add_casual(db: Session, provider_id, payload, *, actor_type: str = "provider", actor_id=None,
                   commit: bool = True, request_id=None) -> dict:
        data = _payload(payload)
        reason = data.pop("reason", None)
        rule = holidays.normalize_rule(data)
        _lock_kitchen(db, provider_id)
        active = db.query(VendorHoliday).filter(
            VendorHoliday.provider_reference_id == provider_id,
            VendorHoliday.holiday_type == holidays.CASUAL,
            VendorHoliday.status == "active",
            VendorHoliday.removed_at.is_(None),
        ).all()
        if any(holidays.same_rule(h, rule) for h in active):
            raise DomainError("This holiday is already set", 409, code="HOLIDAY_EXISTS")
        if rule["rule_type"] == "dates":
            closed = holidays.closed_dates(db, provider_id, rule["start_date"], rule["end_date"])
            if all(d in closed for d in rule["dates"]):
                shown = ", ".join(str(d) for d in rule["dates"])
                raise DomainError(f"{shown} is already marked as a holiday", 409, code="HOLIDAY_EXISTS")

        h = VendorHoliday(
            vendor_holiday_id=uuid.uuid4(), provider_reference_id=provider_id, holiday_type=holidays.CASUAL,
            reason=(reason or "").strip() or None, status="active", processing_status="pending",
            created_by_type=actor_type, created_by=actor_id, **rule,
        )
        db.add(h)
        db.flush()
        result = holiday_policy.apply(db, h, request_id=request_id)
        record_audit(
            db, table="provider.vendor_holidays", record_id=h.vendor_holiday_id, operation="I",
            new={"label": holidays.describe(h), "reason": h.reason, **result},
            actor_id=actor_id or provider_id, actor_type=actor_type,
        )
        if commit:
            db.commit()
            holiday_notices.deliver(db, holiday_id=h.vendor_holiday_id)
        business_event("holiday.casual_added", provider_id=provider_id, holiday_id=h.vendor_holiday_id, **result)
        msg = f"{holidays.describe(h)}. "
        if result["affected_subscriptions"]:
            msg += (f"{result['affected_subscriptions']} subscription(s) were re-planned: customers are told in "
                    "advance and get every paid meal (their plans move past the holiday).")
        else:
            msg += "No running subscription is affected."
        return {"success": True, "message": msg, "holiday": _rule_view(h), **result}

    @staticmethod
    def update_casual(db: Session, provider_id, holiday_id, payload, *, actor_type: str = "provider",
                      actor_id=None, commit: bool = True, request_id=None) -> dict:
        _lock_kitchen(db, provider_id)
        h = _owned(db, provider_id, holiday_id)
        today = today_local()
        if h.holiday_type != holidays.CASUAL:
            raise DomainError("Emergency holidays cannot be edited", 409)
        if h.status != "active" or h.removed_at is not None:
            raise DomainError("This holiday was removed", 409)
        if h.end_date is not None and h.end_date <= today:
            raise DomainError("Past holidays cannot be edited", code="HOLIDAY_IN_PAST")
        data = _payload(payload)
        reason = data.pop("reason", h.reason)
        rule = holidays.normalize_rule(data)
        old = _rule_view(h)
        if h.start_date > today:
            # not started yet: changed in place
            for k, v in rule.items():
                setattr(h, k, v)
            h.reason = reason
            h.updated_by = actor_id
            target = h
        else:
            # the past part stays as it was; the new version applies from tomorrow
            h.end_date = today
            h.updated_by = actor_id
            target = VendorHoliday(
                vendor_holiday_id=uuid.uuid4(), provider_reference_id=provider_id, holiday_type=holidays.CASUAL,
                reason=reason, status="active", processing_status="pending", created_by_type=actor_type,
                created_by=actor_id, replaces_holiday_id=h.vendor_holiday_id, **rule,
            )
            db.add(target)
        db.flush()
        result = holiday_policy.apply(db, target, request_id=request_id)
        record_audit(
            db, table="provider.vendor_holidays", record_id=target.vendor_holiday_id, operation="U",
            old=old, new={"label": holidays.describe(target), **result},
            actor_id=actor_id or provider_id, actor_type=actor_type,
        )
        if commit:
            db.commit()
            holiday_notices.deliver(db, holiday_id=target.vendor_holiday_id)
        return {"success": True, "message": f"Holiday updated: {holidays.describe(target)}",
                "holiday": _rule_view(target), **result}

    @staticmethod
    def remove(db: Session, provider_id, holiday_id, *, actor_type: str = "provider", actor_id=None,
               reason: str | None = None, commit: bool = True) -> dict:
        _lock_kitchen(db, provider_id)
        h = _owned(db, provider_id, holiday_id)
        today = today_local()
        if h.holiday_type != holidays.CASUAL:
            raise DomainError("Emergency holidays cannot be removed. Contact Orleeno support.", 409)
        if h.status != "active" or h.removed_at is not None:
            raise DomainError("This holiday was already removed", 409)
        if h.end_date is not None and h.end_date <= today:
            raise DomainError("Past holidays cannot be removed", code="HOLIDAY_IN_PAST")
        h.removed_at = now_utc()
        h.removed_by = actor_id
        h.removed_reason = reason
        if h.start_date > today:
            h.status = "removed"
        else:
            h.end_date = today  # the days already passed stay on record
        record_audit(
            db, table="provider.vendor_holidays", record_id=h.vendor_holiday_id, operation="D",
            old=_rule_view(h), actor_id=actor_id or provider_id, actor_type=actor_type,
        )
        if commit:
            db.commit()
        return {
            "success": True,
            "message": "Holiday removed. Running subscriptions keep their plan; new orders can use these days.",
            "holiday": _rule_view(h),
        }

    @staticmethod
    def remove_date(db: Session, provider_id, on: date, *, actor_type: str = "provider", actor_id=None,
                    commit: bool = True) -> dict:
        """Older apps remove one date at a time."""
        if on <= today_local():
            raise DomainError("Past holidays cannot be removed", code="HOLIDAY_IN_PAST")
        h = holidays.holiday_on(db, provider_id, on)
        if h is None:
            raise DomainError("Holiday not found", 404)
        if h.holiday_type != holidays.CASUAL:
            raise DomainError("Emergency holidays cannot be removed. Contact Orleeno support.", 409)
        if h.rule_type != "dates":
            raise DomainError(f"{on} is part of '{holidays.describe(h)}'. Edit or remove that holiday.", 409)
        remaining = [d for d in (h.dates or []) if d != on]
        if not remaining:
            return VendorHolidayService.remove(db, provider_id, h.vendor_holiday_id, actor_type=actor_type,
                                               actor_id=actor_id, commit=commit)
        _lock_kitchen(db, provider_id)
        h = _owned(db, provider_id, h.vendor_holiday_id)
        h.dates = remaining
        h.start_date, h.end_date = min(remaining), max(remaining)
        h.updated_by = actor_id
        record_audit(db, table="provider.vendor_holidays", record_id=h.vendor_holiday_id, operation="U",
                     old={"removed_date": on}, actor_id=actor_id or provider_id, actor_type=actor_type)
        if commit:
            db.commit()
        return {"success": True, "message": f"Holiday on {on} removed", "holiday": _rule_view(h)}

    # ── Kitchen: emergency holidays ───────────────────────

    @staticmethod
    def preview_emergency(db: Session, provider_id, on: date | None) -> dict:
        on = on or today_local()
        if on < today_local():
            raise DomainError("An emergency holiday cannot be declared for a past date", code="HOLIDAY_IN_PAST")
        return {"success": True, **emergency_holiday.preview(db, provider_id, on)}

    @staticmethod
    def declare_emergency(db: Session, provider_id, on: date | None, reason: str | None, *,
                          actor_type: str = "provider", actor_id=None) -> dict:
        on = on or today_local()
        holiday = emergency_holiday.declare(db, provider_id, on, reason, actor_type=actor_type,
                                            actor_id=actor_id or provider_id)
        result = emergency_holiday.process(db, holiday.vendor_holiday_id)
        db.expire_all()
        holiday = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday.vendor_holiday_id).one()
        return {
            "success": True,
            "message": (
                f"Emergency holiday declared for {on}. {holiday.affected_meals} meal(s) affected and "
                f"{holiday.compensated_meals} refunded; every active subscription got 1 extra free skip."
            ),
            "holiday": _rule_view(holiday),
            **result,
        }

    # ── Admin ──────────────────────────────────────────────

    @staticmethod
    def admin_list(db: Session, *, provider_id=None, holiday_type=None, from_date=None, to_date=None,
                   processing_status=None, page: int = 1, limit: int = 50) -> dict:
        q = db.query(VendorHoliday, Provider.business_name).join(
            Provider, Provider.provider_id == VendorHoliday.provider_reference_id
        )
        if provider_id:
            q = q.filter(VendorHoliday.provider_reference_id == provider_id)
        if holiday_type:
            q = q.filter(VendorHoliday.holiday_type == holiday_type)
        if from_date:
            q = q.filter((VendorHoliday.end_date.is_(None)) | (VendorHoliday.end_date >= from_date))
        if to_date:
            q = q.filter(VendorHoliday.start_date <= to_date)
        if processing_status:
            q = q.filter(VendorHoliday.processing_status == processing_status)
        total = q.count()
        rows = (
            q.order_by(VendorHoliday.created_at.desc())
            .offset((page - 1) * limit).limit(limit).all()
        )
        return {
            "success": True,
            "total": total,
            "page": page,
            "holidays": [{**_rule_view(h), "provider_id": h.provider_reference_id, "vendor_name": name}
                         for h, name in rows],
        }

    @staticmethod
    def admin_detail(db: Session, holiday_id) -> dict:
        h = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday_id).first()
        if h is None:
            raise DomainError("Holiday not found", 404)
        kitchen = db.query(Provider).filter(Provider.provider_id == h.provider_reference_id).first()
        meals = _meal_rows(db, h.vendor_holiday_id) if h.holiday_type == holidays.EMERGENCY else [
            {"order_id": o.order_id, "subscription_id": o.subscription_reference_id, "meal_date": o.order_date,
             "meal_slot": o.meal_slot, "outcome": "moved_to_plan_end", "status": o.status}
            for o in db.query(Order).filter(Order.vendor_holiday_reference_id == h.vendor_holiday_id).all()
        ]
        subs = db.query(VendorHolidaySubscription).filter(
            VendorHolidaySubscription.vendor_holiday_reference_id == h.vendor_holiday_id
        ).all()
        names = dict(db.query(User.user_id, User.full_name).filter(
            User.user_id.in_([s.user_reference_id for s in subs])).all()) if subs else {}
        notices = db.query(HolidayNotice).filter(
            HolidayNotice.vendor_holiday_reference_id == h.vendor_holiday_id
        ).order_by(HolidayNotice.created_at).all()
        from app.services.holiday_request_service import request_view

        req = db.query(VendorHolidayRequest).filter(
            VendorHolidayRequest.resulting_holiday_id == h.vendor_holiday_id
        ).order_by(VendorHolidayRequest.created_at.desc()).first()
        return {
            "success": True,
            "holiday": {**_rule_view(h), "provider_id": h.provider_reference_id,
                        "vendor_name": kitchen.business_name if kitchen else None},
            "request": request_view(req) if req else None,
            "summary": dict(Counter(m["outcome"] for m in meals)),
            "meals": meals,
            # emergency: one extra free skip per active subscription
            "skip_credits": [
                {
                    "subscription_id": s.subscription_reference_id,
                    "customer_name": names.get(s.user_reference_id),
                    "skip_status": s.skip_status,
                    "skip_credit_id": s.skip_credit_reference_id,
                    "refunded_meals": s.refunded_meals,
                    "refund_amount": s.refund_amount,
                    "notified": s.notice_queued_at is not None,
                    "attempts": s.attempts,
                    "last_error": s.last_error,
                }
                for s in subs
            ],
            "notices": [holiday_notices.view(n) for n in notices],
        }

    @staticmethod
    def admin_compensations(db: Session, *, outcome=None, status=None, page: int = 1, limit: int = 50) -> dict:
        q = db.query(VendorHolidayMeal)
        if outcome:
            q = q.filter(VendorHolidayMeal.outcome == outcome)
        if status == "failed":
            q = q.filter(
                (VendorHolidayMeal.processing_status == "failed")
                | (VendorHolidayMeal.compensation_status == "failed")
                | (VendorHolidayMeal.notification_status == "failed")
            )
        elif status == "pending":
            q = q.filter(
                (VendorHolidayMeal.processing_status == "pending")
                | (VendorHolidayMeal.notification_status == "pending")
            )
        total = q.count()
        rows = q.order_by(VendorHolidayMeal.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "meals": _meal_views(db, rows)}

    @staticmethod
    def admin_retry(db: Session, holiday_id, admin_id, ip: str | None = None) -> dict:
        h = db.query(VendorHoliday).filter(VendorHoliday.vendor_holiday_id == holiday_id).first()
        if h is None:
            raise DomainError("Holiday not found", 404)
        if h.holiday_type != holidays.EMERGENCY:
            # a regular holiday has nothing to process again: only its notices are re-sent
            db.query(HolidayNotice).filter(
                HolidayNotice.vendor_holiday_reference_id == holiday_id, HolidayNotice.status == "failed",
            ).update({"attempts": 0}, synchronize_session=False)
            record_audit(db, table="provider.vendor_holidays", record_id=holiday_id, operation="U",
                         new={"event": "retry_notices"}, actor_id=admin_id, actor_type="admin", ip=ip)
            db.commit()
            return {"success": True, "message": "Retry finished",
                    "notifications": holiday_notices.deliver(db, holiday_id=holiday_id, retry_failed=True)}
        # failed meals get a fresh set of attempts; finished ones are never processed again
        db.query(VendorHolidayMeal).filter(
            VendorHolidayMeal.vendor_holiday_reference_id == holiday_id,
            VendorHolidayMeal.processing_status == "failed",
        ).update({"attempts": 0}, synchronize_session=False)
        db.query(VendorHolidayMeal).filter(
            VendorHolidayMeal.vendor_holiday_reference_id == holiday_id,
            VendorHolidayMeal.notification_status == "failed",
        ).update({"notification_attempts": 0}, synchronize_session=False)
        db.query(VendorHolidaySubscription).filter(
            VendorHolidaySubscription.vendor_holiday_reference_id == holiday_id,
            (VendorHolidaySubscription.skip_status == "failed") | VendorHolidaySubscription.notice_queued_at.is_(None),
        ).update({"attempts": 0}, synchronize_session=False)
        db.query(HolidayNotice).filter(
            HolidayNotice.vendor_holiday_reference_id == holiday_id, HolidayNotice.status == "failed",
        ).update({"attempts": 0}, synchronize_session=False)
        record_audit(db, table="provider.vendor_holidays", record_id=holiday_id, operation="U",
                     new={"event": "retry"}, actor_id=admin_id, actor_type="admin", ip=ip)
        db.commit()
        result = emergency_holiday.process(db, holiday_id, retry_failed=True)
        return {"success": True, "message": "Retry finished", **result}


def _meal_views(db: Session, rows: list[VendorHolidayMeal]) -> list[dict]:
    kitchen_ids = {r.original_vendor_reference_id for r in rows} | {r.replacement_vendor_reference_id for r in rows}
    names = dict(
        db.query(Provider.provider_id, Provider.business_name).filter(Provider.provider_id.in_(
            [k for k in kitchen_ids if k is not None])).all()
    ) if kitchen_ids else {}
    users = dict(
        db.query(User.user_id, User.full_name).filter(User.user_id.in_([r.user_reference_id for r in rows])).all()
    ) if rows else {}
    pkg_ids = [r.replacement_package_reference_id for r in rows if r.replacement_package_reference_id]
    pkgs = dict(db.query(MenuPackage.package_id, MenuPackage.package_name).filter(
        MenuPackage.package_id.in_(pkg_ids)).all()) if pkg_ids else {}
    return [
        {
            "holiday_meal_id": r.vendor_holiday_meal_id,
            "holiday_id": r.vendor_holiday_reference_id,
            "order_id": r.order_reference_id,
            "subscription_id": r.subscription_reference_id,
            "customer_name": users.get(r.user_reference_id),
            "meal_date": r.meal_date,
            "meal_slot": r.meal_slot,
            "outcome": r.outcome,
            "original_vendor_id": r.original_vendor_reference_id,
            "original_vendor_name": names.get(r.original_vendor_reference_id),
            "replacement_vendor_id": r.replacement_vendor_reference_id,
            "replacement_vendor_name": names.get(r.replacement_vendor_reference_id),
            "replacement_package_name": pkgs.get(r.replacement_package_reference_id),
            "original_meal_price": r.original_meal_price,
            "replacement_meal_price": r.replacement_meal_price,
            "meal_amount": r.meal_amount,
            "wallet_transaction_id": r.wallet_transaction_reference_id,
            "skip_credit_id": r.skip_credit_reference_id,
            "processing_status": r.processing_status,
            "compensation_status": r.compensation_status,
            "notification_status": r.notification_status,
            "attempts": r.attempts,
            "last_error": r.last_error,
            "processed_at": r.processed_at,
            "notified_at": r.notified_at,
        }
        for r in rows
    ]


def _meal_rows(db: Session, holiday_id) -> list[dict]:
    rows = db.query(VendorHolidayMeal).filter(
        VendorHolidayMeal.vendor_holiday_reference_id == holiday_id
    ).order_by(VendorHolidayMeal.meal_date, VendorHolidayMeal.meal_slot).all()
    return _meal_views(db, rows)
