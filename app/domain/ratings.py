"""
Package ratings.

Every package keeps its own rating: the average of the valid package ratings
customers gave it and their count, computed in the database from
provider.reviews. A valid rating is a visible review with a package_rating
(1-5) for that package; ratings of other packages, even of the same kitchen,
never mix in. An Orleeno catalogue package sold by several kitchens is rated
per kitchen, because each kitchen cooks it.

    average = sum of valid ratings of the package / number of valid ratings

Lists use one grouped query for the whole page (no query per package).
"""

import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, tuple_
from sqlalchemy.orm import Session

from app.models.review_model import Review

NO_RATINGS = "No ratings yet"


def _valid():
    return (Review.is_visible == True, Review.package_rating.isnot(None))  # noqa: E712


def _view(total, count) -> dict:
    count = int(count or 0)
    if not count:
        return {"rating_average": None, "rating_count": 0, "rating_label": NO_RATINGS}
    average = (Decimal(total) / Decimal(count)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return {
        "rating_average": float(average),
        "rating_count": count,
        "rating_label": f"{average} ({count} review{'s' if count != 1 else ''})",
    }


def empty() -> dict:
    return _view(0, 0)


def _uuid(value):
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def for_offers(db: Session, pairs) -> dict:
    """
    {(package_id, provider_id): rating view} for (package, kitchen) pairs, in
    one query. Keys are UUIDs whatever the caller passed (str or UUID); read
    them with get().
    """
    keys = {(_uuid(p), _uuid(k)) for p, k in pairs if p is not None and k is not None}
    if not keys:
        return {}
    rows = (
        db.query(
            Review.package_reference_id, Review.vendor_reference_id,
            func.sum(Review.package_rating), func.count(Review.package_rating),
        )
        .filter(*_valid(), tuple_(Review.package_reference_id, Review.vendor_reference_id).in_(list(keys)))
        .group_by(Review.package_reference_id, Review.vendor_reference_id)
        .all()
    )
    found = {(pkg, vendor): _view(total, count) for pkg, vendor, total, count in rows}
    return {key: found.get(key, empty()) for key in keys}


def get(stats: dict, package_id, provider_id) -> dict:
    """One (package, kitchen) rating from for_offers(), 'No ratings yet' when absent."""
    return stats.get((_uuid(package_id), _uuid(provider_id))) or empty()


def for_packages(db: Session, package_ids) -> dict:
    """{package_id: rating view} over all kitchens (the kitchen and admin views of a package)."""
    ids = {_uuid(p) for p in package_ids if p is not None}
    if not ids:
        return {}
    rows = (
        db.query(Review.package_reference_id, func.sum(Review.package_rating), func.count(Review.package_rating))
        .filter(*_valid(), Review.package_reference_id.in_(list(ids)))
        .group_by(Review.package_reference_id)
        .all()
    )
    found = {pkg: _view(total, count) for pkg, total, count in rows}
    return {pid: found.get(pid, empty()) for pid in ids}


def recent_reviews(db: Session, package_id, provider_id=None, limit: int = 5, offset: int = 0) -> list:
    """Latest visible reviews of one package (no customer identifiers)."""
    q = db.query(Review).filter(Review.is_visible == True, Review.package_reference_id == package_id)  # noqa: E712
    if provider_id is not None:
        q = q.filter(Review.vendor_reference_id == provider_id)
    return [
        {
            "review_id": r.review_id,
            "package_reference_id": r.package_reference_id,
            "vendor_reference_id": r.vendor_reference_id,
            "package_rating": r.package_rating,
            "vendor_rating": r.vendor_rating,
            "review_text": r.review_text,
            "review_date": r.review_date,
            "created_at": r.created_at,
        }
        for r in q.order_by(Review.created_at.desc()).offset(offset).limit(limit).all()
    ]


def review_count(db: Session, package_id, provider_id=None) -> int:
    q = db.query(func.count(Review.review_id)).filter(
        Review.is_visible == True, Review.package_reference_id == package_id  # noqa: E712
    )
    if provider_id is not None:
        q = q.filter(Review.vendor_reference_id == provider_id)
    return int(q.scalar() or 0)
