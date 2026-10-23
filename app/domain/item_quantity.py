"""
How much of a food item a package contains: "400 g" rice, "4 pcs" roti,
"1 bowl (300 g)" sabji, "250 ml" dal.

A kitchen gives an amount and a unit (and, for bowls, optionally how much one
bowl holds). The structured values are stored next to a display label in the
item's `quantity` column, so every screen that already shows `quantity`
(customer app, admin panel, food summary) shows the measurement as-is.

Older app versions send `quantity` as free text with no unit; that text is
kept unchanged as the label and the structured fields stay empty.
"""

from decimal import Decimal, InvalidOperation

# unit -> label suffix
UNITS = {"g": "g", "kg": "kg", "pcs": "pcs", "bowl": "bowl", "ml": "ml", "l": "L"}
COUNTED_UNITS = ("pcs", "bowl")  # whole numbers only
BOWL_CAPACITY_UNITS = ("g", "ml")

MAX_VALUE = Decimal("10000")
MAX_BOWL_CAPACITY = Decimal("5000")

STRUCTURED_FIELDS = ("quantity_value", "quantity_unit", "bowl_capacity", "bowl_capacity_unit")
FIELDS = ("quantity",) + STRUCTURED_FIELDS


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Quantity must be a number")


def _num(value: Decimal) -> str:
    """400.00 -> "400", 1.50 -> "1.5"."""
    return f"{value.normalize():f}"


def label(value, unit: str, bowl_capacity=None, bowl_capacity_unit: str | None = None) -> str:
    value = _dec(value)
    amount = _num(value)
    if unit == "pcs":
        return f"{amount} {'pc' if value == 1 else 'pcs'}"
    if unit == "bowl":
        text = f"{amount} {'bowl' if value == 1 else 'bowls'}"
        capacity = _dec(bowl_capacity)
        if capacity is not None:
            text += f" ({_num(capacity)} {UNITS[bowl_capacity_unit]}{'' if value == 1 else ' each'})"
        return text
    return f"{amount} {UNITS[unit]}"


def normalize(quantity=None, quantity_value=None, quantity_unit=None,
              bowl_capacity=None, bowl_capacity_unit=None) -> dict:
    """
    Validated values for all quantity fields of an item (raises ValueError).
    With a unit the label is built from it; without one the free-text
    `quantity` is kept as sent (older app versions).
    """
    unit = (quantity_unit or "").strip().lower() or None
    value = _dec(quantity_value)
    capacity = _dec(bowl_capacity)
    capacity_unit = (bowl_capacity_unit or "").strip().lower() or None

    if unit is None:
        if value is not None:
            raise ValueError("Choose a unit for the quantity")
        if capacity is not None or capacity_unit is not None:
            raise ValueError("Bowl size can only be given for items measured in bowls")
        text = (quantity or "").strip() or None
        return {"quantity": text, "quantity_value": None, "quantity_unit": None,
                "bowl_capacity": None, "bowl_capacity_unit": None}

    if unit not in UNITS:
        raise ValueError(f"Unit must be one of: {', '.join(UNITS)}")
    if value is None:
        raise ValueError("Enter the quantity")
    if value <= 0 or value > MAX_VALUE:
        raise ValueError(f"Quantity must be more than 0 and at most {_num(MAX_VALUE)}")
    if value.as_tuple().exponent < -2:
        raise ValueError("Quantity can have at most 2 decimal places")
    if unit in COUNTED_UNITS and value != value.to_integral_value():
        raise ValueError("Pieces and bowls must be a whole number")

    if unit != "bowl":
        if capacity is not None or capacity_unit is not None:
            raise ValueError("Bowl size can only be given for items measured in bowls")
    elif capacity is not None or capacity_unit is not None:
        if capacity is None or capacity_unit is None:
            raise ValueError("Give the bowl size with its unit (g or ml)")
        if capacity_unit not in BOWL_CAPACITY_UNITS:
            raise ValueError("Bowl size must be in g or ml")
        if capacity <= 0 or capacity > MAX_BOWL_CAPACITY:
            raise ValueError(f"Bowl size must be more than 0 and at most {_num(MAX_BOWL_CAPACITY)}")
        if capacity.as_tuple().exponent < -2:
            raise ValueError("Bowl size can have at most 2 decimal places")

    return {
        "quantity": label(value, unit, capacity, capacity_unit),
        "quantity_value": value,
        "quantity_unit": unit,
        "bowl_capacity": capacity,
        "bowl_capacity_unit": capacity_unit,
    }


def sent(request) -> bool:
    """The request (add / update item) carries a quantity at all."""
    return any(getattr(request, f, None) is not None for f in FIELDS)


def from_request(request) -> dict:
    """Quantity fields of an item request (already validated by the schema)."""
    return normalize(**{f: getattr(request, f, None) for f in FIELDS})


def as_json(values: dict) -> dict:
    """The same fields, JSON-safe (pending revisions, API views)."""
    out = {f: values.get(f) for f in FIELDS}
    for f in ("quantity_value", "bowl_capacity"):
        if out[f] is not None:
            out[f] = float(out[f])
    return out


def of(item) -> dict:
    """JSON-safe quantity fields of a stored item (model row or revision dict)."""
    get = item.get if isinstance(item, dict) else (lambda f: getattr(item, f, None))
    return as_json({f: get(f) for f in FIELDS})


def to_model(values: dict) -> dict:
    """Quantity fields of a revision dict, ready for a MenuPackageItem."""
    return {
        "quantity": values.get("quantity"),
        "quantity_value": _dec(values.get("quantity_value")),
        "quantity_unit": values.get("quantity_unit"),
        "bowl_capacity": _dec(values.get("bowl_capacity")),
        "bowl_capacity_unit": values.get("bowl_capacity_unit"),
    }


def total(values: dict, servings: int) -> str | None:
    """
    How much to cook for `servings` (food summary): "4 kg" for 10 x 400 g,
    "10 bowls (300 g each)". None for items without a unit.
    """
    unit = values.get("quantity_unit")
    value = _dec(values.get("quantity_value"))
    if not unit or value is None:
        return None
    amount = value * servings
    if unit in ("g", "ml") and amount >= 1000:
        amount, unit = (amount / 1000).quantize(Decimal("0.01")), ("kg" if unit == "g" else "l")
    return label(amount, unit, values.get("bowl_capacity"), values.get("bowl_capacity_unit"))
