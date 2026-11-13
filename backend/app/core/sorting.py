"""Whitelisted ORDER BY for the server-paged lists (Call Log + Dialer history, Huvo calls,
Activity Logs). The browser holds one page, so a column sort has to happen in SQL."""
from fastapi import HTTPException


def order_by(sort: str | None, sort_dir: str | None, allowed: dict[str, str], default: str) -> str:
    """`allowed` maps a column key the page may send to SQL written in the router — raw input
    never reaches the statement; an unknown key or direction is a 422. Blanks sort last in
    both directions (as the browser's useSort does), and the default order breaks ties so
    paging over equal values is stable."""
    if sort is None:
        return f" ORDER BY {default}"
    if sort not in allowed:
        raise HTTPException(status_code=422, detail=f"can't sort by {sort!r}")
    d = (sort_dir or "asc").lower()
    if d not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail=f"sort direction must be asc or desc, not {sort_dir!r}")
    return f" ORDER BY {allowed[sort]} {d.upper()} NULLS LAST, {default}"
