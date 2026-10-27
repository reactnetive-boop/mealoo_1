"""
Kitchen holiday requests and their approval by an admin.

A kitchen (Profile -> Manage Holidays) asks for:

  emergency  one date after today (up to 30 days ahead), the whole day or
             some of the meals the kitchen serves, optional reason
  regular    weekly days off: add, change (an approved weekly rule) or remove
             (any approved rule, including older date / vacation / monthly
             ones, which can no longer be added)

Every request goes to the admins (notified at once with the date or days and
what would change) and waits. Nothing changes until an admin approves it:
the approved schedule is provider.vendor_holidays alone, so a pending,
rejected, withdrawn or expired request never closes or opens a day.

Approving applies the change through VendorHolidayService in the same
transaction as the decision (the request is locked, so two admins approving
at once apply it once; a second approval of an approved request changes
nothing). Emergency work - refunds, the one-time orders of the day, one free
skip per active subscription - then runs meal by meal with its own
idempotency keys (app/domain/emergency_holiday.py). The kitchen hears the
decision; customers and delivery partners hear about approved changes only.

Duplicates: one pending request per kitchen and dedupe key (unique index);
sending the same request again gives back the one already waiting. An
emergency request overlapping a different one still waiting (same date, a
meal in common) is refused (409) until that one is withdrawn or decided.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import business_event, record_audit
from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.domain import emergency_holiday, holiday_notices, holiday_policy, holidays, vendor_partner
from app.domain.slots import SLOTS, slots_label
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.vendor_holiday_model import HolidayNotice, VendorHoliday, VendorHolidayRequest
from app.services.vendor_holiday_service import VendorHolidayService, _rule_view

EMERGENCY = "emergency"
REGULAR = "regular"
RUNNING = ("active", "paused")
WEEKLY_ONLY = (
    "Regular holidays are weekly days off (for example every Sunday). For a single day, "
    "request an emergency holiday."
)


# ── Views ─────────────────────────────────────────────────────

def _fmt(d: date | None) -> str:
    return f"{d.day} {d.strftime('%b %Y')}" if d else ""


def _weekly_label(weekdays) -> str:
    days = [holidays.WEEKDAY_NAMES[d] for d in sorted(weekdays or [])]
    return f"Closed every {holidays._join(days)}" if days else "No weekly days off"


def describe(r: VendorHolidayRequest, target: VendorHoliday | None = None) -> str:
    """'Emergency holiday on 6 Oct 2026 (Lunch only)', 'Add: Closed every Sunday', 'Remove: Closed every Sunday', ..."""
    if r.request_type == EMERGENCY:
        return f"Emergency holiday on {_fmt(r.holiday_date)}{holidays.meals_note(r.meal_slots)}"
    current = holidays.describe(target) if target is not None else "a holiday"
    if r.action == "remove":
        if r.holiday_date is not None:
            return f"Remove the holiday on {_fmt(r.holiday_date)}"
        return f"Remove: {current}"
    new = _weekly_label(r.weekdays)
    if r.start_date and r.start_date > today_local() + timedelta(days=1):
        new += f" from {_fmt(r.start_date)}"
    return f"Change: {current} → {new}" if r.action == "update" else f"Add: {new}"


def request_view(r: VendorHolidayRequest, targets: dict | None = None, *, db: Session | None = None,
                 vendor_name: str | None = None) -> dict:
    target = None
    if r.target_holiday_id is not None:
        target = (targets or {}).get(r.target_holiday_id)
        if target is None and db is not None:
            target = db.get(VendorHoliday, r.target_holiday_id)
    return {
        "request_id": r.request_id,
        "provider_id": r.provider_reference_id,
        "vendor_name": vendor_name,
        "request_type": r.request_type,
        "action": r.action,
        "status": r.status,
        "label": describe(r, target),
        "holiday_date": r.holiday_date,
        # emergency: the meals asked for; None = the whole day
        "meal_slots": r.meal_slots or None,
        "full_day": not r.meal_slots,
        "weekdays": sorted(r.weekdays or []),
        "start_date": r.start_date,
        "reason": r.reason,
        "target_holiday_id": r.target_holiday_id,
        "target_label": holidays.describe(target) if target is not None else None,
        "impact": r.impact or {},
        "decision_note": r.decision_note,
        "decided_by": r.decided_by,
        "decided_at": r.decided_at,
        "resulting_holiday_id": r.resulting_holiday_id,
        "result": r.result or {},
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _kitchen(db: Session, provider_id, lock: bool = False) -> Provider:
    q = db.query(Provider).filter(Provider.provider_id == provider_id)
    kitchen = (q.with_for_update() if lock else q).first()
    if kitchen is None:
        raise DomainError("Kitchen not found", 404)
    return kitchen


def _pending(db: Session, provider_id, key: str) -> VendorHolidayRequest | None:
    return db.query(VendorHolidayRequest).filter(
        VendorHolidayRequest.provider_reference_id == provider_id,
        VendorHolidayRequest.dedupe_key == key,
        VendorHolidayRequest.status == "pending",
    ).first()


def _refuse_overlap(db: Session, provider_id, on: date, slots, key: str) -> None:
    """Another emergency request for a meal of that date still waiting: it must be withdrawn first (409)."""
    wanted = set(slots or SLOTS)
    waiting = db.query(VendorHolidayRequest).filter(
        VendorHolidayRequest.provider_reference_id == provider_id,
        VendorHolidayRequest.request_type == EMERGENCY,
        VendorHolidayRequest.status == "pending",
        VendorHolidayRequest.holiday_date == on,
    ).all()
    for w in waiting:
        if w.dedupe_key == key:
            continue  # the very same request: given back as a duplicate
        overlap = wanted & set(w.meal_slots or SLOTS)
        if overlap:
            raise DomainError(
                f"An emergency holiday request for {slots_label(overlap)} on {_fmt(on)} is already waiting for "
                "approval. Withdraw it first.", 409, code="HOLIDAY_REQUEST_PENDING",
            )


def _payload(payload) -> dict:
    data = payload if isinstance(payload, dict) else payload.model_dump(exclude_unset=True)
    return {k: v for k, v in data.items() if v is not None}


def _weekly_rule(data: dict) -> dict:
    """Validated weekly rule of a regular-holiday request (weekly days only)."""
    rule = holidays.normalize_rule(data)
    if rule["rule_type"] != "weekly":
        raise DomainError(WEEKLY_ONLY, code="HOLIDAY_WEEKLY_ONLY")
    return rule


def _target(db: Session, provider_id, holiday_id) -> VendorHoliday:
    h = db.query(VendorHoliday).filter(
        VendorHoliday.vendor_holiday_id == holiday_id, VendorHoliday.provider_reference_id == provider_id,
    ).first()
    if h is None:
        raise DomainError("Holiday not found", 404)
    if h.holiday_type != holidays.CASUAL:
        raise DomainError("Emergency holidays cannot be changed. Contact Orleeno support.", 409)
    if h.status != "active" or h.removed_at is not None:
        raise DomainError("This holiday was already removed", 409)
    if h.end_date is not None and h.end_date <= today_local():
        raise DomainError("Past holidays cannot be changed", code="HOLIDAY_IN_PAST")
    return h


def _notify_admins(db: Session, r: VendorHolidayRequest, kitchen: Provider, target: VendorHoliday | None) -> None:
    name = kitchen.business_name or "A kitchen"
    impact = r.impact or {}
    if r.request_type == EMERGENCY:
        meals = f" for {slots_label(r.meal_slots)} only" if r.meal_slots else " (full day)"
        skip = impact.get("free_skip") or {}
        if skip.get("eligible", True):
            skips = f"{impact.get('skip_credits', 0)} active subscription(s) get 1 extra free skip."
        else:
            skips = f"no free skip is given ({skip.get('reason', 'the kitchen serves fewer than 2 meals a day')})."
        body = (
            f"{name} asked for an emergency holiday on {r.holiday_date.strftime('%a %d %b %Y')}{meals}"
            + (f" ({r.reason})" if r.reason else "") + ". "
            f"If approved: {impact.get('affected_orders', 0)} meal(s) and {impact.get('one_time_orders', 0)} "
            f"one-time order(s) refunded (about ₹{impact.get('estimated_refund', '0.00')}), and {skips}"
        )
    else:
        body = f"{name} asked: {describe(r, target)}."
        if r.action != "remove":
            body += (f" If approved, {impact.get('affected_subscriptions', 0)} running subscription(s) are "
                     "re-planned so customers keep every paid meal.")
        if r.reason:
            body += f" Reason: {r.reason}."
    holiday_notices.queue(
        db, "admin", None, "holiday_request", f"Holiday request: {name}", body,
        {"request_id": r.request_id, "provider_id": r.provider_reference_id, "request_type": r.request_type,
         "action": r.action, "holiday_date": r.holiday_date.isoformat() if r.holiday_date else None,
         "weekdays": sorted(r.weekdays or [])},
        dedupe_key=f"holiday_request:{r.request_id}:admin", request_id=r.request_id,
    )


def _create(db: Session, kitchen: Provider, *, key: str, **fields) -> tuple[VendorHolidayRequest, bool]:
    """(request, created). A request already waiting with the same key is given back."""
    existing = _pending(db, kitchen.provider_id, key)
    if existing is not None:
        return existing, False
    r = VendorHolidayRequest(request_id=uuid.uuid4(), provider_reference_id=kitchen.provider_id, status="pending",
                             dedupe_key=key, **fields)
    db.add(r)
    try:
        db.flush()
    except IntegrityError:  # sent twice at the same moment: the other one won
        db.rollback()
        existing = _pending(db, kitchen.provider_id, key)
        if existing is None:
            raise
        return existing, False
    return r, True


def _submitted(db: Session, r: VendorHolidayRequest, kitchen: Provider, created: bool,
               target: VendorHoliday | None = None) -> dict:
    if created:
        _notify_admins(db, r, kitchen, target)
        record_audit(db, table="provider.vendor_holiday_requests", record_id=r.request_id, operation="I",
                     new={"label": describe(r, target), "reason": r.reason}, actor_id=kitchen.provider_id,
                     actor_type="provider")
    db.commit()
    if created:
        holiday_notices.deliver(db, request_id=r.request_id)
        business_event("holiday.request_sent", provider_id=kitchen.provider_id, request_id=r.request_id,
                       request_type=r.request_type, action=r.action)
    view = request_view(r, {target.vendor_holiday_id: target} if target is not None else None, db=db)
    return {
        "success": True,
        "duplicate": not created,
        "message": (
            "Request sent to Orleeno for approval. Your holidays change only once it is approved."
            if created else "This request is already waiting for approval."
        ),
        "request": view,
        # older app versions read `holiday`
        "holiday": view,
    }


class HolidayRequestService:

    # ── Kitchen ────────────────────────────────────────────

    @staticmethod
    def submit_emergency(db: Session, provider_id, on: date | None, reason: str | None, meal_slots=None) -> dict:
        """
        A kitchen's emergency holiday request: only for a date after today
        (business-local; no date = today, refused), the whole day or
        `meal_slots` (meals the kitchen serves). The whole request is refused
        when the date or a meal is not allowed.
        """
        on = on or today_local()
        emergency_holiday.validate_future(on)
        kitchen = _kitchen(db, provider_id, lock=True)  # one request at a time per kitchen
        slots = emergency_holiday.normalize_slots(db, provider_id, on, meal_slots)
        emergency_holiday.validate_request(db, provider_id, on, slots, future_only=True)
        key = f"emergency:{on.isoformat()}" + (f":{','.join(slots)}" if slots else "")
        _refuse_overlap(db, provider_id, on, slots, key)
        r, created = _create(
            db, kitchen, key=key, request_type=EMERGENCY, action="add",
            holiday_date=on, meal_slots=slots, reason=(reason or "").strip() or None,
            impact=_json(emergency_holiday.preview(db, provider_id, on, slots)),
        )
        return _submitted(db, r, kitchen, created)

    @staticmethod
    def submit_regular(db: Session, provider_id, payload, *, action: str = "add", target_id=None) -> dict:
        kitchen = _kitchen(db, provider_id, lock=True)
        data = _payload(payload or {})
        reason = (data.pop("reason", None) or "").strip() or None
        target = None
        if action == "add":
            rule = _weekly_rule(data)
            current = db.query(VendorHoliday).filter(
                VendorHoliday.provider_reference_id == provider_id,
                VendorHoliday.holiday_type == holidays.CASUAL,
                VendorHoliday.rule_type == "weekly",
                VendorHoliday.status == "active",
                VendorHoliday.removed_at.is_(None),
                or_(VendorHoliday.end_date.is_(None), VendorHoliday.end_date > today_local()),
            ).all()
            if any(sorted(h.weekdays or []) == rule["weekdays"] for h in current):
                raise DomainError("These weekly days off are already approved", 409, code="HOLIDAY_EXISTS")
            key = "regular:add:" + ",".join(str(d) for d in rule["weekdays"])
        elif action == "update":
            target = _target(db, provider_id, target_id)
            rule = _weekly_rule(data)
            if target.rule_type == "weekly" and sorted(target.weekdays or []) == rule["weekdays"]:
                raise DomainError("These weekly days off are already approved", 409, code="HOLIDAY_EXISTS")
            key = f"regular:target:{target.vendor_holiday_id}"
        elif action == "remove":
            target = _target(db, provider_id, target_id)
            rule = None
            key = f"regular:target:{target.vendor_holiday_id}"
        else:
            raise DomainError("Unknown holiday change", 400)

        waiting = _pending(db, provider_id, key)
        if waiting is not None and (
            waiting.action != action or (rule and sorted(waiting.weekdays or []) != rule["weekdays"])
        ):
            raise DomainError("A change to this holiday is already waiting for approval. Withdraw it first.", 409,
                              code="HOLIDAY_REQUEST_PENDING")
        impact: dict = {}
        if rule is not None:
            draft = VendorHoliday(provider_reference_id=provider_id, holiday_type=holidays.CASUAL, **rule)
            impact = {"label": holidays.describe(draft), **holiday_policy.preview(db, draft)}
        else:
            impact = {"label": holidays.describe(target)}
        r, created = _create(
            db, kitchen, key=key, request_type=REGULAR, action=action,
            target_holiday_id=target.vendor_holiday_id if target is not None else None,
            weekdays=rule["weekdays"] if rule else None, start_date=rule["start_date"] if rule else None,
            reason=reason, impact=_json(impact),
        )
        return _submitted(db, r, kitchen, created, target)

    @staticmethod
    def submit_remove_date(db: Session, provider_id, on: date) -> dict:
        """Older apps remove one date of a dates rule at a time: also a request."""
        if on <= today_local():
            raise DomainError("Past holidays cannot be removed", code="HOLIDAY_IN_PAST")
        h = holidays.holiday_on(db, provider_id, on)
        if h is None:
            raise DomainError("Holiday not found", 404)
        if h.holiday_type != holidays.CASUAL:
            raise DomainError("Emergency holidays cannot be removed. Contact Orleeno support.", 409)
        if h.rule_type != "dates":
            raise DomainError(f"{on} is part of '{holidays.describe(h)}'. Remove that holiday instead.", 409)
        kitchen = _kitchen(db, provider_id, lock=True)
        r, created = _create(
            db, kitchen, key=f"regular:date:{on.isoformat()}", request_type=REGULAR, action="remove",
            target_holiday_id=h.vendor_holiday_id, holiday_date=on, impact={"label": holidays.describe(h)},
        )
        return _submitted(db, r, kitchen, created, h)

    @staticmethod
    def withdraw(db: Session, provider_id, request_id) -> dict:
        r = db.query(VendorHolidayRequest).filter(
            VendorHolidayRequest.request_id == request_id, VendorHolidayRequest.provider_reference_id == provider_id,
        ).with_for_update().first()
        if r is None:
            raise DomainError("Request not found", 404)
        if r.status == "withdrawn":
            return {"success": True, "message": "Request withdrawn", "request": request_view(r, db=db)}
        if r.status != "pending":
            raise DomainError(f"This request was already {r.status}", 409, code="HOLIDAY_REQUEST_DECIDED")
        r.status = "withdrawn"
        r.decided_at = now_utc()
        record_audit(db, table="provider.vendor_holiday_requests", record_id=r.request_id, operation="U",
                     new={"status": "withdrawn"}, actor_id=provider_id, actor_type="provider")
        db.commit()
        return {"success": True, "message": "Request withdrawn", "request": request_view(r, db=db)}

    @staticmethod
    def list_for_provider(db: Session, provider_id, status: str | None = None, limit: int = 100) -> dict:
        q = db.query(VendorHolidayRequest).filter(VendorHolidayRequest.provider_reference_id == provider_id)
        if status:
            q = q.filter(VendorHolidayRequest.status == status)
        rows = q.order_by(VendorHolidayRequest.created_at.desc()).limit(limit).all()
        return {"success": True, "total": len(rows), "requests": [request_view(r, db=db) for r in rows]}

    # ── Admin ──────────────────────────────────────────────

    @staticmethod
    def admin_list(db: Session, *, status=None, request_type=None, provider_id=None, page: int = 1,
                   limit: int = 50) -> dict:
        q = db.query(VendorHolidayRequest, Provider.business_name).join(
            Provider, Provider.provider_id == VendorHolidayRequest.provider_reference_id
        )
        if status:
            q = q.filter(VendorHolidayRequest.status == status)
        if request_type:
            q = q.filter(VendorHolidayRequest.request_type == request_type)
        if provider_id:
            q = q.filter(VendorHolidayRequest.provider_reference_id == provider_id)
        total = q.count()
        rows = (
            q.order_by((VendorHolidayRequest.status == "pending").desc(), VendorHolidayRequest.created_at.desc())
            .offset((page - 1) * limit).limit(limit).all()
        )
        pending = db.query(VendorHolidayRequest).filter(VendorHolidayRequest.status == "pending").count()
        return {
            "success": True, "total": total, "page": page, "pending": pending,
            "requests": [request_view(r, db=db, vendor_name=name) for r, name in rows],
        }

    @staticmethod
    def admin_detail(db: Session, request_id) -> dict:
        r = db.query(VendorHolidayRequest).filter(VendorHolidayRequest.request_id == request_id).first()
        if r is None:
            raise DomainError("Request not found", 404)
        kitchen = db.query(Provider).filter(Provider.provider_id == r.provider_reference_id).first()
        view = request_view(r, db=db, vendor_name=kitchen.business_name if kitchen else None)
        # what approving it would do now (it may differ from when it was sent)
        if r.status == "pending":
            try:
                if r.request_type == EMERGENCY:
                    view["impact_now"] = _json(emergency_holiday.preview(db, r.provider_reference_id, r.holiday_date,
                                                                         r.meal_slots))
                elif r.action != "remove":
                    draft = VendorHoliday(provider_reference_id=r.provider_reference_id, holiday_type=holidays.CASUAL,
                                          **_weekly_rule({"rule_type": "weekly", "weekdays": r.weekdays,
                                                          "start_date": _start(r)}))
                    view["impact_now"] = _json({"label": holidays.describe(draft),
                                                **holiday_policy.preview(db, draft)})
            except DomainError as exc:
                view["impact_now"] = {"error": exc.message}
        history = db.query(VendorHolidayRequest).filter(
            VendorHolidayRequest.provider_reference_id == r.provider_reference_id,
            VendorHolidayRequest.request_id != r.request_id,
        ).order_by(VendorHolidayRequest.created_at.desc()).limit(20).all()
        notices = db.query(HolidayNotice).filter(
            or_(HolidayNotice.request_reference_id == r.request_id,
                HolidayNotice.vendor_holiday_reference_id == r.resulting_holiday_id)
            if r.resulting_holiday_id else HolidayNotice.request_reference_id == r.request_id
        ).order_by(HolidayNotice.created_at).all()
        current = VendorHolidayService.overview(db, r.provider_reference_id)
        return {
            "success": True,
            "request": view,
            "current_schedule": {
                "regular_holidays": current["regular_holidays"],
                "rules": [{k: v for k, v in rule.items() if k != "pending_request"} for rule in current["rules"]],
                "upcoming": current["upcoming"],
            },
            "history": [request_view(h, db=db) for h in history],
            "notices": [holiday_notices.view(n) for n in notices],
        }

    @staticmethod
    def approve(db: Session, request_id, admin_id, note: str | None = None, ip: str | None = None) -> dict:
        r = db.query(VendorHolidayRequest).filter(
            VendorHolidayRequest.request_id == request_id
        ).with_for_update().populate_existing().first()
        if r is None:
            raise DomainError("Request not found", 404)
        if r.status == "approved":  # approved by someone else just now: nothing more to do
            return {"success": True, "message": "This request is already approved", "already_decided": True,
                    "request": request_view(r, db=db)}
        if r.status != "pending":
            raise DomainError(f"This request was already {r.status}", 409, code="HOLIDAY_REQUEST_DECIDED")
        kitchen = _kitchen(db, r.provider_reference_id)
        today = today_local()
        if r.request_type == EMERGENCY and r.holiday_date < today:
            _expire(db, r, kitchen)
            db.commit()
            holiday_notices.deliver(db, request_id=r.request_id)
            raise DomainError("This emergency date has passed, so the request expired.", 409,
                              code="HOLIDAY_REQUEST_EXPIRED")

        holiday_id = None
        result: dict = {}
        if r.request_type == EMERGENCY:
            holiday = emergency_holiday.declare(
                db, r.provider_reference_id, r.holiday_date, r.reason, actor_type="admin", actor_id=admin_id,
                commit=False, request_id=r.request_id, meal_slots=r.meal_slots,
            )
            holiday_id = holiday.vendor_holiday_id
        else:
            rule = {"rule_type": "weekly", "weekdays": r.weekdays, "start_date": _start(r), "reason": r.reason}
            if r.action == "add":
                out = VendorHolidayService.add_casual(db, r.provider_reference_id, rule, actor_type="admin",
                                                      actor_id=admin_id, commit=False, request_id=r.request_id)
            elif r.action == "update":
                out = VendorHolidayService.update_casual(db, r.provider_reference_id, r.target_holiday_id, rule,
                                                         actor_type="admin", actor_id=admin_id, commit=False,
                                                         request_id=r.request_id)
            elif r.holiday_date is not None:
                out = VendorHolidayService.remove_date(db, r.provider_reference_id, r.holiday_date,
                                                       actor_type="admin", actor_id=admin_id, commit=False)
            else:
                out = VendorHolidayService.remove(db, r.provider_reference_id, r.target_holiday_id,
                                                  actor_type="admin", actor_id=admin_id, reason=r.reason,
                                                  commit=False)
            holiday_id = out["holiday"]["holiday_id"]
            result = {k: v for k, v in out.items() if k in (
                "affected_subscriptions", "cancelled_meals", "cancelled_one_time_orders")}
            _announce_regular(db, r, kitchen, out, set(out.get("notified_subscriptions") or []))

        r.status = "approved"
        r.decided_by = admin_id
        r.decided_at = now_utc()
        r.decision_note = (note or "").strip() or None
        r.resulting_holiday_id = holiday_id
        r.result = _json(result) or None
        _notify_kitchen(db, r, kitchen, approved=True)
        record_audit(db, table="provider.vendor_holiday_requests", record_id=r.request_id, operation="U",
                     new={"status": "approved", "note": r.decision_note, "holiday_id": str(holiday_id)},
                     actor_id=admin_id, actor_type="admin", ip=ip)
        db.commit()
        business_event("holiday.request_approved", request_id=r.request_id, provider_id=r.provider_reference_id,
                       request_type=r.request_type, action=r.action)

        if r.request_type == EMERGENCY:
            work = emergency_holiday.process(db, holiday_id)
            r = db.query(VendorHolidayRequest).filter(VendorHolidayRequest.request_id == request_id).one()
            h = db.get(VendorHoliday, holiday_id)
            r.result = _json({
                "affected_meals": h.affected_meals, "refunded_meals": h.compensated_meals,
                "one_time_orders": work.get("one_time_orders", {}), "skip_credits": work.get("skip_credits", {}),
                "processing_status": work.get("processing_status"),
            })
            db.commit()
        holiday_notices.deliver(db, request_id=request_id)
        if holiday_id is not None:
            holiday_notices.deliver(db, holiday_id=holiday_id)
        db.expire_all()
        r = db.query(VendorHolidayRequest).filter(VendorHolidayRequest.request_id == request_id).one()
        view = request_view(r, db=db)
        h = db.get(VendorHoliday, holiday_id) if holiday_id else None
        return {"success": True, "message": f"Approved: {view['label']}", "request": view,
                "holiday": _rule_view(h) if h is not None else None}

    @staticmethod
    def reject(db: Session, request_id, admin_id, note: str | None = None, ip: str | None = None) -> dict:
        r = db.query(VendorHolidayRequest).filter(
            VendorHolidayRequest.request_id == request_id
        ).with_for_update().populate_existing().first()
        if r is None:
            raise DomainError("Request not found", 404)
        if r.status == "rejected":
            return {"success": True, "message": "This request is already rejected", "already_decided": True,
                    "request": request_view(r, db=db)}
        if r.status != "pending":
            raise DomainError(f"This request was already {r.status}", 409, code="HOLIDAY_REQUEST_DECIDED")
        kitchen = _kitchen(db, r.provider_reference_id)
        r.status = "rejected"
        r.decided_by = admin_id
        r.decided_at = now_utc()
        r.decision_note = (note or "").strip() or None
        _notify_kitchen(db, r, kitchen, approved=False)
        record_audit(db, table="provider.vendor_holiday_requests", record_id=r.request_id, operation="U",
                     new={"status": "rejected", "note": r.decision_note}, actor_id=admin_id, actor_type="admin", ip=ip)
        db.commit()
        holiday_notices.deliver(db, request_id=r.request_id)
        business_event("holiday.request_rejected", request_id=r.request_id, provider_id=r.provider_reference_id)
        return {"success": True, "message": "Request rejected. The kitchen's holidays stay as they were.",
                "request": request_view(r, db=db)}

    @staticmethod
    def expire_stale(db: Session) -> dict:
        """Emergency requests whose date passed without a decision expire (the kitchen is told)."""
        rows = db.query(VendorHolidayRequest).filter(
            VendorHolidayRequest.status == "pending",
            VendorHolidayRequest.request_type == EMERGENCY,
            VendorHolidayRequest.holiday_date < today_local(),
        ).with_for_update(skip_locked=True).all()
        for r in rows:
            _expire(db, r, _kitchen(db, r.provider_reference_id))
        db.commit()
        for r in rows:
            holiday_notices.deliver(db, request_id=r.request_id)
        return {"expired": len(rows)}


# ── Helpers ───────────────────────────────────────────────────

def _json(data: dict) -> dict:
    def conv(v):
        if isinstance(v, (date, uuid.UUID)):
            return str(v) if isinstance(v, uuid.UUID) else v.isoformat()
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        return v if isinstance(v, (str, int, float, bool)) or v is None else str(v)

    return {k: conv(v) for k, v in (data or {}).items()}


def _start(r: VendorHolidayRequest) -> date:
    """A weekly rule starts on the requested day, or tomorrow if that has passed while it waited."""
    tomorrow = today_local() + timedelta(days=1)
    return max(r.start_date or tomorrow, tomorrow)


def _expire(db: Session, r: VendorHolidayRequest, kitchen: Provider) -> None:
    r.status = "expired"
    r.decided_at = now_utc()
    r.decision_note = "The date passed before the request was decided."
    holiday_notices.queue(
        db, "provider", kitchen.provider_id, "holiday_request", "Holiday request expired",
        f"Your request ({describe(r)}) was not decided before the date passed, so nothing changed.",
        {"request_id": r.request_id, "status": "expired"},
        dedupe_key=f"holiday_request:{r.request_id}:expired", request_id=r.request_id,
    )


def _notify_kitchen(db: Session, r: VendorHolidayRequest, kitchen: Provider, *, approved: bool) -> None:
    target = db.get(VendorHoliday, r.target_holiday_id) if r.target_holiday_id else None
    what = describe(r, target)
    if approved:
        title = "Holiday request approved"
        if r.request_type == EMERGENCY:
            skip = emergency_holiday.skip_decision(db, kitchen.provider_id, r.holiday_date, r.meal_slots)
            closed = (f"No {slots_label(r.meal_slots).lower()} that day: no orders, preparation or pickups for it; "
                      "your other meals run as usual." if r.meal_slots
                      else "You are closed that day: no orders, preparation or pickups.")
            body = (f"Approved: {what}. {closed} Customers are told and refunded"
                    + (", and get an extra free skip." if skip.eligible else "."))
        else:
            body = f"Approved: {what}. Your holiday calendar is updated and customers are told."
    else:
        title = "Holiday request rejected"
        body = f"Not approved: {what}. Your holidays stay as they were."
    if r.decision_note:
        body += f" Note from Orleeno: {r.decision_note}"
    holiday_notices.queue(
        db, "provider", kitchen.provider_id, "holiday_request", title, body,
        {"request_id": r.request_id, "status": "approved" if approved else "rejected",
         "request_type": r.request_type, "action": r.action},
        dedupe_key=f"holiday_request:{r.request_id}:decision", request_id=r.request_id,
    )


def _announce_regular(db: Session, r: VendorHolidayRequest, kitchen: Provider, out: dict, notified: set) -> None:
    """
    Every running subscriber and the kitchen's partners hear about an approved
    change of the weekly days off (subscribers whose plan was re-planned were
    already told the exact dates and their new end date).
    """
    name = kitchen.business_name or "Your kitchen"
    label = out["holiday"]["label"]
    if r.action == "remove":
        headline = f"{name} removed a holiday"
        text = (f"{name} is open again on the days of '{label}' from now on. Your plan keeps every meal you "
                "paid for; days already planned around the holiday stay as they are.")
    elif r.action == "update":
        headline = f"{name} changed its weekly days off"
        text = f"{name} changed its weekly days off: {label}. Your plan keeps every meal you paid for."
    else:
        headline = f"{name} has new weekly days off"
        text = (f"{name} is now {label[0].lower() + label[1:]}. There is no delivery and no charge on those "
                "days, and your plan keeps every meal you paid for.")
    subs = db.query(Subscription.subscription_id, Subscription.user_reference_id).filter(
        Subscription.vendor_reference_id == kitchen.provider_id,
        Subscription.status.in_(RUNNING),
        Subscription.end_date > today_local(),
    ).all()
    for sub_id, user_id in subs:
        if str(sub_id) in notified:
            continue
        holiday_notices.queue(
            db, "customer", user_id, "vendor_holiday", headline, text,
            {"subscription_id": sub_id, "provider_id": kitchen.provider_id, "request_id": r.request_id,
             "weekly_off_days": sorted(r.weekdays or []), "action": r.action},
            dedupe_key=f"regular_change:{r.request_id}:{sub_id}", request_id=r.request_id,
            holiday_id=out["holiday"]["holiday_id"],
        )
    partners = set()
    row = vendor_partner.kitchen_row(db, kitchen.provider_id)
    if row is not None:
        partners.add(row.delivery_boy_reference_id)
    for (boy,) in db.query(Subscription.delivery_boy_reference_id).filter(
        Subscription.vendor_reference_id == kitchen.provider_id, Subscription.status.in_(RUNNING),
        Subscription.delivery_boy_reference_id.isnot(None),
    ).distinct():
        partners.add(boy)
    for boy in sorted((p for p in partners if p is not None), key=str):
        holiday_notices.queue(
            db, "delivery_boy", boy, "schedule_update", f"{name}: weekly days off changed",
            f"{headline}: {label}. No pickups from {name} on its days off; your schedule is updated.",
            {"provider_id": kitchen.provider_id, "request_id": r.request_id,
             "weekly_off_days": sorted(r.weekdays or []), "action": r.action},
            dedupe_key=f"regular_change_partner:{r.request_id}:{boy}", request_id=r.request_id,
            holiday_id=out["holiday"]["holiday_id"],
        )
