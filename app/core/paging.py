"""Page / limit query parameters shared by list endpoints."""

from dataclasses import dataclass

from fastapi import Query


@dataclass(frozen=True)
class Paging:
    page: int = 1
    limit: int = 100

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit

    def meta(self, total: int) -> dict:
        return {"total": total, "page": self.page, "limit": self.limit, "has_more": self.offset + self.limit < total}


def paging(
    page: int = Query(1, ge=1, description="1-based page number"),
    limit: int = Query(100, ge=1, le=100, description="Items per page (newest first)"),
) -> Paging:
    return Paging(page, limit)


FIRST_PAGE = Paging()
