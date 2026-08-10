from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx


FetchJson = Callable[[int], Any]

HIGH_KEYWORDS = ("央行", "重磅", "紧急", "暴跌", "暴涨", "崩盘", "降息", "加息", "制裁")
MEDIUM_KEYWORDS = ("涨停", "利好", "利空", "增持", "减持", "业绩", "营收", "监管")


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(normalized, pattern).replace(tzinfo=UTC)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _importance(title: str) -> str:
    if any(word in title for word in HIGH_KEYWORDS):
        return "high"
    if any(word in title for word in MEDIUM_KEYWORDS):
        return "medium"
    return "normal"


class FlashNewsService:
    """Normalize and filter the crabpi flash-news feed for MCP consumers."""

    NEWS_URL = "https://news.crabpi.com/api/flash-news"

    def __init__(
        self,
        *,
        fetch_json: FetchJson | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._fetch_json = fetch_json or self._fetch_live
        self._now = now or (lambda: datetime.now(UTC))

    def _fetch_live(self, limit: int) -> Any:
        response = httpx.get(
            self.NEWS_URL,
            params={"limit": max(limit, 100)},
            timeout=10,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("data") or []
            return [item for item in items if isinstance(item, dict)]
        return []

    def search(
        self,
        *,
        query: str = "",
        hours: int = 24,
        limit: int = 30,
    ) -> dict[str, Any]:
        if not 1 <= hours <= 168:
            raise ValueError("hours must be between 1 and 168")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        retrieved_at = self._now().astimezone(UTC)
        cutoff = retrieved_at - timedelta(hours=hours)
        needle = query.strip().casefold()
        payload = self._fetch_json(max(limit, 100))
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in self._items(payload):
            title = str(item.get("title") or "").strip()
            content = str(item.get("content_text") or item.get("content") or "").strip()
            published_raw = str(
                item.get("date_published") or item.get("published_at") or ""
            ).strip()
            published = _parse_time(published_raw)
            if (
                not title
                or published is None
                or published < cutoff
                or published > retrieved_at + timedelta(minutes=5)
            ):
                continue
            if needle and needle not in f"{title}\n{content}".casefold():
                continue
            canonical = json.dumps(
                [title, published_raw, content], ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            digest = hashlib.sha256(canonical).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            source_url = str(item.get("url") or item.get("link") or self.NEWS_URL)
            records.append(
                {
                    "news_id": f"news_{digest[:24]}",
                    "title": title,
                    "content": (content or title)[:500],
                    "published_at": published.isoformat() if published else published_raw,
                    "importance": _importance(title),
                    "source": "crabpi",
                    "source_url": source_url,
                    "evidence": {
                        "evidence_id": f"evd_{digest[:24]}",
                        "source_type": "news_api",
                        "source_id": "crabpi-flash-news",
                        "title": title,
                        "locator": source_url,
                        "period": published.isoformat() if published else published_raw,
                        "content_hash": digest,
                    },
                }
            )
            if len(records) >= limit:
                break
        return {
            "source": "crabpi",
            "source_url": self.NEWS_URL,
            "retrieved_at": retrieved_at.isoformat(),
            "window_hours": hours,
            "query": query.strip(),
            "count": len(records),
            "items": records,
        }


def fixture_fetcher(path: str | Path) -> FetchJson:
    fixture = Path(path)

    def fetch(_limit: int) -> Any:
        return json.loads(fixture.read_text(encoding="utf-8"))

    return fetch
