"""Canonical handling of a package's meal_type.

A package can be served in one slot, any two, or all three. The value is stored
as a canonically ordered comma separated string ("breakfast,lunch,dinner") so a
single `String(50)` column keeps working for every combination.
"""

# Canonical order — the stored string always follows it
MEAL_TYPE_SLOTS = ("breakfast", "lunch", "dinner")

# Shorthands the apps may send for "every slot"
ALL_SLOTS_ALIASES = {
    "all",
    "all_slots",
    "all_three",
    "all_day",
    "allday",
    "full_day",
    "fullday",
}


def normalize_meal_type(value) -> str:
    """
    Accept a list (`["lunch", "dinner"]`) or a string (`"lunch, dinner"`,
    `"full_day"`) and return the canonical stored form.

    Raises ValueError — surfaced by pydantic as a 422 — when a slot is not
    recognised or nothing is supplied.
    """

    if value is None:

        raise ValueError("meal_type is required")

    if isinstance(value, str):
        tokens = value.replace("|", ",").split(",")

    elif isinstance(value, (list, tuple, set)):
        tokens = []
        for entry in value:
            tokens.extend(str(entry).replace("|", ",").split(","))

    else:
        raise ValueError(
            "meal_type must be a string or a list of meal slots"
        )

    selected = set()

    for token in tokens:

        slot = token.strip().lower().replace(" ", "_").replace("-", "_")

        if not slot:
            continue

        if slot in ALL_SLOTS_ALIASES:
            selected.update(MEAL_TYPE_SLOTS)
            continue

        if slot not in MEAL_TYPE_SLOTS:

            raise ValueError(
                f"Invalid meal_type '{token.strip()}'. "
                f"Allowed: {', '.join(MEAL_TYPE_SLOTS)} "
                f"(one or more, comma separated or as a list) "
                f"or 'full_day' for all three"
            )

        selected.add(slot)

    if not selected:

        raise ValueError(
            f"meal_type must contain at least one of: {', '.join(MEAL_TYPE_SLOTS)}"
        )

    return ",".join(slot for slot in MEAL_TYPE_SLOTS if slot in selected)


def meal_type_to_list(value) -> list:
    """Split a stored meal_type back into its slots. Safe on None/legacy values."""

    if not value:
        return []

    return [slot.strip() for slot in str(value).split(",") if slot.strip()]


# ── Food type ─────────────────────────────────────────────────

FOOD_TYPES = ("veg", "non_veg", "egg", "vegan", "jain")

_FOOD_ALIASES = {
    "vegetarian": "veg",
    "nonveg": "non_veg",
    "non_vegetarian": "non_veg",
    "eggetarian": "egg",
}


def normalize_food_type(value) -> str:
    """
    Accept "Veg, Jain", ["veg", "jain"], "non-veg" ... and return the canonical
    comma separated form ("veg,jain"). Unknown values raise ValueError (422).
    """

    if value is None:
        raise ValueError("food_type is required")
    tokens = value if isinstance(value, (list, tuple, set)) else str(value).replace("|", ",").split(",")
    selected = set()
    for token in tokens:
        t = str(token).strip().lower().replace(" ", "_").replace("-", "_")
        if not t:
            continue
        t = _FOOD_ALIASES.get(t, t)
        if t not in FOOD_TYPES:
            raise ValueError(f"Invalid food_type '{token}'. Allowed: {', '.join(FOOD_TYPES)}")
        selected.add(t)
    if not selected:
        raise ValueError("food_type must contain at least one value")
    return ",".join(t for t in FOOD_TYPES if t in selected)
