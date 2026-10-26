"""
The price breakup customers see before they pay, and again in order details
and subscription history.

It is built from the same pricing snapshot the payment uses
(app/domain/pricing.build_quote), never computed by an app. Every amount is
a Decimal rounded to the paisa, and the lines marked `in_total` add up to
`total` exactly - a test checks the invariant for every kind of breakup.

Every app shows the same layout (2026-10-26), so each line carries its
`section` and the lines come in this order:

  price        plan / item price: meals per meal slot (meals x per-meal
               price x quantity), add-ons, kitchen holiday dates inside the
               plan (not charged, Rs 0.00)
  adjustment   switches only: amount already paid and meals used (context),
               then the unused value of the current plan as a credit
  discount     plan discount / offer: name, percent and amount
  wallet       wallet balance used (quotes, when the wallet pays something);
               not part of `total`
  fees_taxes   delivery, packaging, platform, SMS, payment charges, the
               switch fee, each tax with its rate (GST 5% ...) or
               "Taxes Rs 0.00", and rounding
  then         `total_payable`: what is left to pay after the wallet (or the
               refund and where it goes), shown highlighted at the bottom

Lines with `show: false` (a zero add-on, switch fee or rounding, the
switch's internal difference) stay in the data but are not displayed. The
breakup never contains a skip price: skips are not part of what a purchase
costs.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal

from app.domain.pricing import money, ZERO, TAX_KEYS
from app.domain.holidays import NOT_CHARGED_LABEL

VERSION = 2
# display order of the sections (every app renders them in this order)
SECTIONS = ("price", "adjustment", "discount", "wallet", "fees_taxes")
_SECTION_OF_KIND = {
    "charge": "price", "info": "price", "credit": "adjustment", "subtotal": "adjustment",
    "discount": "discount", "wallet": "wallet", "fee": "fees_taxes", "tax": "fees_taxes",
    "rounding": "fees_taxes",
}
REFUND_DESTINATION = "wallet"
REFUND_WHEN = "Credited to your Orleeno wallet as soon as you confirm"

_SLOT_TITLE = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner"}


def _s(value) -> str:
    return str(money(value))


def _rupees(value) -> str:
    return f"₹{money(value):,.2f}"


def _line(key: str, label: str, amount, *, kind: str, detail: str | None = None, in_total: bool = True,
          meta: dict | None = None, section: str | None = None, show: bool | None = None) -> dict:
    value = money(amount)
    if show is None:
        # zero add-ons / switch fee / rounding add nothing: kept in the data, not displayed
        show = not (key in ("add_ons", "fee_switch", "rounding") and value == ZERO)
    return {
        "key": key,
        "label": label,
        "detail": detail,
        "amount": _s(value),
        "kind": kind,
        "section": section or _SECTION_OF_KIND.get(kind, "price"),
        "show": show,
        "in_total": in_total,
        "meta": meta or {},
    }


def _ordered(lines: list[dict]) -> list[dict]:
    """Lines in the display order of their sections (stable inside a section)."""
    rank = {name: i for i, name in enumerate(SECTIONS)}
    return sorted(lines, key=lambda l: rank.get(l.get("section"), 0))


def _meal_lines(snapshot: dict, slots: list[str], package_name: str | None) -> list[dict]:
    unit = Decimal(snapshot["base_unit_price"])
    qty = int(snapshot["quantity"])
    deliveries = int(snapshot["deliveries"])
    per_slot = deliveries // max(len(slots), 1)
    lines = []
    for slot in slots:
        amount = money(unit * qty * per_slot)
        qty_text = f" × {qty} qty" if qty > 1 else ""
        lines.append(_line(
            f"meals_{slot}", f"{_SLOT_TITLE.get(slot, slot.title())} meals",
            amount, kind="charge",
            detail=f"{per_slot} meals × {_rupees(unit)}{qty_text} = {_rupees(amount)}",
            meta={"meal_slot": slot, "meals": per_slot, "unit_price": _s(unit), "quantity": qty,
                  "package_name": package_name},
        ))
    return lines


def _fee_and_tax_lines(snapshot: dict) -> tuple[list[dict], list[dict]]:
    fees, taxes = [], []
    for c in snapshot.get("charges", []):
        if c["key"] in TAX_KEYS:
            rate = f"{Decimal(c['value']).normalize():f}%" if c.get("calc_type") == "percentage" else _rupees(c["value"])
            taxes.append(_line(
                f"tax_{c['key']}", f"{c['label']} {rate}", c["amount"], kind="tax",
                detail=f"{rate} of the food amount" if c.get("calc_type") == "percentage" else None,
                meta={"rate": c["value"], "calc_type": c.get("calc_type")},
            ))
        else:
            detail = None
            if c.get("calc_type") == "percentage":
                detail = f"{Decimal(c['value']).normalize():f}% of the food amount"
            elif c.get("basis") == "per_delivery":
                detail = f"{_rupees(c['value'])} per delivery"
            elif c.get("basis") == "per_unit":
                detail = f"{_rupees(c['value'])} per meal"
            fees.append(_line(f"fee_{c['key']}", c["label"], c["amount"], kind="fee", detail=detail,
                              meta={"value": c["value"], "calc_type": c.get("calc_type"), "basis": c.get("basis")}))
    if not taxes:
        taxes.append(_line("taxes", "Taxes", ZERO, kind="tax", detail="No tax applies to this order"))
    return fees, taxes


def _discount_line(snapshot: dict, name: str | None) -> dict:
    percent = Decimal(snapshot.get("discount_percent") or "0")
    amount = money(snapshot.get("discount_amount") or "0")
    if amount <= ZERO:
        return _line("discount", "Discount", ZERO, kind="discount", detail="No offer applied",
                     meta={"name": None, "percent": "0", "amount": "0.00"})
    pct = f"{percent.normalize():f}%"
    label = name or "Plan discount"
    return _line(
        "discount", f"{label} ({pct} off)", -amount, kind="discount",
        detail=f"{pct} of {_rupees(snapshot['base_amount'])}",
        meta={"name": label, "percent": str(percent), "amount": _s(amount)},
    )


def _holiday_line(holiday_dates) -> dict | None:
    dates = sorted({d if isinstance(d, date) else date.fromisoformat(str(d)) for d in (holiday_dates or [])})
    if not dates:
        return None
    return _line(
        "vendor_holidays", f"{NOT_CHARGED_LABEL} ({len(dates)} day{'s' if len(dates) != 1 else ''})", ZERO,
        kind="info", detail=", ".join(d.strftime("%a %d %b") for d in dates),
        meta={"dates": [d.isoformat() for d in dates]},
    )


def _wallet(total: Decimal, wallet_balance) -> dict:
    balance = money(wallet_balance)
    applied = min(balance, total) if total > ZERO else ZERO
    return {
        "wallet_balance": _s(balance),
        "wallet_applied": _s(applied),
        "wallet_balance_after": _s(balance - applied),
        "amount_payable": _s(total - applied),
    }


def quote_hash(breakup: dict) -> str:
    """Fingerprint of the price the customer was shown; changes whenever any amount does (not the wallet)."""
    payload = json.dumps(
        {"total": breakup["total"],
         "lines": [(l["key"], l["amount"]) for l in breakup["lines"] if l.get("section") != "wallet"]},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _wallet_line(applied) -> dict:
    return _line("wallet", "Wallet balance used", -money(applied), kind="wallet", in_total=False,
                 detail="Paid from your Orleeno wallet")


def _finish(kind: str, lines: list[dict], total: Decimal, wallet_balance, **extra) -> dict:
    summed = sum((Decimal(l["amount"]) for l in lines if l["in_total"]), ZERO)
    if summed != money(total):  # the invariant every breakup must keep
        raise AssertionError(f"price breakup lines add up to {summed}, total is {total}")
    breakup = {
        "version": VERSION,
        "currency": "INR",
        "kind": kind,
        "sections": list(SECTIONS),
        "lines": lines,
        "total": _s(total),
        # JSON-safe: it is stored with the purchase
        **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in extra.items()},
    }
    if wallet_balance is not None:
        breakup.update(_wallet(money(total), wallet_balance) if money(total) >= ZERO else {
            "wallet_balance": _s(wallet_balance), "wallet_applied": "0.00",
            "wallet_balance_after": _s(money(wallet_balance)), "amount_payable": "0.00",
        })
    if money(breakup.get("wallet_applied") or ZERO) > ZERO:
        lines.append(_wallet_line(breakup["wallet_applied"]))
    breakup["lines"] = _ordered(lines)
    # what is left to pay after the wallet (or the order total when no wallet is involved)
    breakup["total_payable"] = breakup.get("amount_payable") or _s(max(money(total), ZERO))
    breakup["quote_hash"] = quote_hash(breakup)
    return breakup


# ── New subscription ──────────────────────────────────────────

def subscription(snapshot: dict, *, slots: list[str], package_name: str | None, plan_name: str | None,
                 holiday_dates=(), wallet_balance=None, start_date=None, end_date=None, meal_days=None) -> dict:
    lines = _meal_lines(snapshot, slots, package_name)
    lines.append(_line("add_ons", "Package add-ons", ZERO, kind="charge", detail="No add-ons"))
    holiday = _holiday_line(holiday_dates)
    if holiday:
        lines.append(holiday)
    lines.append(_discount_line(snapshot, plan_name))
    fees, taxes = _fee_and_tax_lines(snapshot)
    lines += fees + taxes
    lines.append(_line("rounding", "Rounding adjustment", ZERO, kind="rounding"))
    return _finish(
        "subscription", lines, Decimal(snapshot["total_payable"]), wallet_balance,
        meals=int(snapshot["deliveries"]), meal_days=meal_days,
        package_name=package_name, start_date=start_date, end_date=end_date,
        holiday_dates=sorted(str(d) for d in (holiday_dates or [])),
        refund=None,
    )


# ── One-time order ────────────────────────────────────────────

def extra_order(priced: list, *, wallet_balance=None, delivery_date=None, meal_slot=None) -> dict:
    """priced: [(package, quantity, snapshot)] - one checkout (one trip)."""
    lines = []
    charges: dict = {}
    for package, qty, snap in priced:
        unit = Decimal(snap["base_unit_price"])
        amount = money(snap["base_amount"])
        lines.append(_line(
            f"item_{package.package_id}", package.package_name, amount, kind="charge",
            detail=f"{qty} × {_rupees(unit)} = {_rupees(amount)}",
            meta={"package_id": str(package.package_id), "quantity": qty, "unit_price": _s(unit)},
        ))
        for c in snap.get("charges", []):
            merged = charges.setdefault(c["key"], {**c, "amount": "0.00"})
            merged["amount"] = _s(Decimal(merged["amount"]) + Decimal(c["amount"]))
    lines.append(_line("add_ons", "Add-ons", ZERO, kind="charge", detail="No add-ons"))
    lines.append(_line("discount", "Discount", ZERO, kind="discount", detail="No offer applied",
                       meta={"name": None, "percent": "0", "amount": "0.00"}))
    fees, taxes = _fee_and_tax_lines({"charges": list(charges.values())})
    lines += fees + taxes
    lines.append(_line("rounding", "Rounding adjustment", ZERO, kind="rounding"))
    total = sum((Decimal(s["total_payable"]) for _, _, s in priced), ZERO)
    return _finish("extra_order", lines, total, wallet_balance, delivery_date=delivery_date,
                   meal_slot=meal_slot, refund=None)


class _NamedPackage:
    """The two fields the builders read, for a line whose package row is gone."""

    def __init__(self, package_id, package_name):
        self.package_id = package_id
        self.package_name = package_name


def extra_order_line(order, package=None) -> dict | None:
    """
    The breakup of ONE one-time order line, adding up to its `total_price`, so
    the customer, the kitchen and the admin see the same total for the same
    order. A one-line checkout keeps the breakup stored at payment; other lines
    (and orders placed before breakups were stored) are rebuilt from the line's
    own pricing snapshot, or from its stored amounts for the oldest orders.
    """
    snapshot = order.pricing_snapshot or {}
    total = money(order.total_price)
    stored = snapshot.get("price_breakup")
    if stored and money(stored.get("total")) == total:
        return normalize(stored)
    pkg = package or _NamedPackage(order.package_reference_id, "Package")
    qty = int(order.quantity or 1)
    common = {"delivery_date": order.delivery_date, "meal_slot": order.meal_slot}
    try:
        if snapshot.get("base_unit_price") is not None and snapshot.get("total_payable") is not None:
            return paid_copy(extra_order([(pkg, qty, snapshot)], **common))
    except (AssertionError, KeyError, ValueError, ArithmeticError):
        pass  # an older snapshot shape: fall back to the stored amounts
    unit = money(order.unit_price)
    food = money(unit * qty)
    charges = money(order.charges_amount)
    lines = [
        _line(f"item_{pkg.package_id}", pkg.package_name, food, kind="charge",
              detail=f"{qty} × {_rupees(unit)} = {_rupees(food)}",
              meta={"package_id": str(pkg.package_id), "quantity": qty, "unit_price": _s(unit)}),
        _line("discount", "Discount", ZERO, kind="discount", detail="No offer applied",
              meta={"name": None, "percent": "0", "amount": "0.00"}),
        _line("fees", "Delivery & other charges", charges, kind="fee"),
        _line("taxes", "Taxes", ZERO, kind="tax", detail="No tax applies to this order"),
    ]
    rounding = total - food - charges
    lines.append(_line("rounding", "Rounding adjustment", rounding, kind="rounding"))
    try:
        return paid_copy(_finish("extra_order", lines, total, None, refund=None, **common))
    except AssertionError:
        return None


def from_totals(kind: str, *, total, meals_amount=None, discount=None, charges=None,
                carried_over: bool = False) -> dict | None:
    """
    A breakup from a purchase's stored totals, for records kept before
    breakups were stored. Still adds up to what was paid; any difference the
    old totals do not explain is shown as rounding.
    """
    total = money(total)
    food = money(meals_amount) if meals_amount is not None else total
    off = money(discount)
    fees = money(charges)
    lines = [
        _line("meals", "Value carried over from your previous plan" if carried_over else "Meals", food,
              kind="charge"),
        _line("discount", "Discount", -off, kind="discount",
              detail=None if off > ZERO else "No offer applied"),
        _line("fees", "Delivery & other charges", fees, kind="fee"),
        _line("taxes", "Taxes", ZERO, kind="tax", detail="No tax applied"),
        _line("rounding", "Rounding adjustment", total - food + off - fees, kind="rounding"),
    ]
    try:
        return paid_copy(_finish(kind, lines, total, None, refund=None))
    except AssertionError:
        return None


def one_meal(snapshot: dict, package, *, meal_slot: str | None = None) -> dict:
    """
    What one meal of a package costs as a one-time order today: the item
    price × 1, every fee and tax at the current rates, and the total (package
    detail screen). The checkout builds the real breakup for the chosen day.
    """
    return extra_order([(package, int(snapshot.get("quantity") or 1), snapshot)], meal_slot=meal_slot)


# ── Package / kitchen switch ──────────────────────────────────

def switch(calc: dict, *, slots: list[str], new_package_name: str, plan_name: str | None,
           paid_amount, meals_total: int, meals_used: int, old_meal_value, holiday_dates=(),
           wallet_balance=None, vendor_changed: bool = False, old_vendor_name: str | None = None,
           new_vendor_name: str | None = None, old_package_name: str | None = None) -> dict:
    """
    Unused Service Value Method (app/services/package_switch_service.py):
    new cost of the remaining meals - remaining value of the current plan,
    settled to the paisa. Positive: payable; negative: refunded.
    """
    quote = calc["quote"]
    info = [
        _line("already_paid", "Amount already paid for your current plan", paid_amount, kind="info", in_total=False,
              detail=f"{meals_total} meals", section="adjustment"),
        _line("meals_used", "Meals already used", money(Decimal(old_meal_value) * meals_used), kind="info",
              in_total=False, detail=f"{meals_used} of {meals_total} meals × {_rupees(old_meal_value)}",
              meta={"meals": meals_used}, section="adjustment"),
    ]
    lines = list(info)
    lines += _meal_lines(quote, slots, new_package_name)
    for l in lines[len(info):]:
        l["label"] = f"New plan · {l['label']}"
    lines.append(_line("add_ons", "Package add-ons", ZERO, kind="charge", detail="No add-ons"))
    holiday = _holiday_line(holiday_dates)
    if holiday:
        lines.append(holiday)
    lines.append(_discount_line(quote, plan_name))
    fees, taxes = _fee_and_tax_lines(quote)
    lines += fees
    lines.append(_line("fee_switch", "Switch fee", ZERO, kind="fee", detail="No fee for switching"))
    lines += taxes
    remaining_value = money(calc["remaining_value"])
    lines.append(_line(
        "remaining_value", "Credit from your current package (unused value)", -remaining_value, kind="credit",
        detail=f"{calc['remaining_meals']} remaining meals × {_rupees(old_meal_value)}",
        meta={"meals": calc["remaining_meals"]},
    ))
    difference = money(calc["adjustment_amount"])
    lines.append(_line("difference", "Difference", difference, kind="subtotal", in_total=False,
                       detail="New plan cost − unused value", show=False))
    final = calc["payment_amount"] if calc["payment_amount"] > ZERO else -money(calc["wallet_credit_amount"])
    rounding = money(final) - difference
    lines.append(_line("rounding", "Rounding adjustment", rounding, kind="rounding",
                       detail=None))
    refund = None
    if final < ZERO:
        refund = {"amount": _s(-final), "destination": REFUND_DESTINATION, "when": REFUND_WHEN}
    breakup = _finish(
        "vendor_switch" if vendor_changed else "package_switch", lines, money(final),
        wallet_balance if final > ZERO else None,
        new_plan_cost=_s(calc["new_remaining_cost"]), remaining_value=_s(remaining_value),
        difference=_s(difference), effective_date=str(calc["effective_date"]),
        meals=int(quote["deliveries"]), holiday_dates=sorted(str(d) for d in (holiday_dates or [])),
        refund=refund, vendor_changed=vendor_changed, old_vendor_name=old_vendor_name,
        new_vendor_name=new_vendor_name, old_package_name=old_package_name, new_package_name=new_package_name,
    )
    if final <= ZERO:
        breakup.update({"wallet_applied": "0.00", "amount_payable": "0.00", "total_payable": "0.00"})
        if wallet_balance is not None:
            breakup["wallet_balance"] = _s(wallet_balance)
            breakup["wallet_balance_after"] = _s(money(wallet_balance) - money(final))
    return breakup


def paid_copy(breakup: dict) -> dict:
    """
    The breakup as stored with the purchase: everything was paid from the
    wallet, so history shows the total paid (no "wallet used" line).
    """
    stored = {k: v for k, v in breakup.items() if k not in ("wallet_balance", "wallet_balance_after")}
    stored["lines"] = [l for l in breakup.get("lines", []) if l.get("section") != "wallet"]
    stored["paid"] = True
    if Decimal(breakup["total"]) > ZERO:
        stored["wallet_applied"] = breakup["total"]
        stored["amount_payable"] = "0.00"
        stored["total_paid"] = breakup["total"]
    return stored


def normalize(breakup: dict | None) -> dict | None:
    """
    A breakup stored before the common layout (version 1) in the same shape
    as new ones: every line gets its section and `show`, in section order,
    and `total_payable` / `paid` are set. Newer breakups come back unchanged.
    """
    if not breakup or int(breakup.get("version") or 1) >= VERSION:
        return breakup
    lines = []
    for line in breakup.get("lines") or []:
        key = line.get("key")
        section = line.get("section") or (
            "adjustment" if key in ("already_paid", "meals_used") else _SECTION_OF_KIND.get(line.get("kind"), "price")
        )
        zero = money(line.get("amount") or ZERO) == ZERO
        show = line.get("show")
        if show is None:
            show = not (key == "difference" or (key in ("add_ons", "fee_switch", "rounding") and zero))
        lines.append({**line, "section": section, "show": show})
    out = {**breakup, "version": VERSION, "sections": list(SECTIONS), "lines": _ordered(lines)}
    stored_paid = out.get("amount_payable") == "0.00" and out.get("wallet_applied") == out.get("total")
    if stored_paid and money(out.get("total") or ZERO) > ZERO:
        out.update({"paid": True, "total_paid": out["total"]})
    out.setdefault("total_payable", out.get("amount_payable") or _s(max(money(out.get("total") or ZERO), ZERO)))
    return out
