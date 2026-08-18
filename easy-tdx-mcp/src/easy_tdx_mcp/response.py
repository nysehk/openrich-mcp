from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .serialization import jsonable


def result(
    data: Any,
    *,
    source: str,
    request: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload = jsonable(data)
    count = len(payload) if isinstance(payload, list) else (0 if payload is None else 1)
    return {
        "status": "ok",
        "source": source,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "request": jsonable(request or {}),
        "data": payload,
        "meta": {"returned_count": count, "truncated": False},
        "warnings": warnings or ["仅供学习和技术研究，不构成投资建议。"],
        "error": None,
    }
