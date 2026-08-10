from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from openrich_news_mcp.service import FlashNewsService


FIXTURE = Path(__file__).parent / "fixtures" / "flash-news.json"


def build_service() -> FlashNewsService:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return FlashNewsService(
        fetch_json=lambda _limit: payload,
        now=lambda: datetime(2026, 8, 9, 8, 0, tzinfo=UTC),
    )


def test_search_filters_by_24_hour_window_and_company():
    result = build_service().search(query="华星精密", hours=24, limit=20)
    assert result["count"] == 1
    item = result["items"][0]
    assert item["title"] == "华星精密发布年度业绩预告"
    assert item["evidence"]["source_id"] == "crabpi-flash-news"
    assert len(item["evidence"]["content_hash"]) == 64


def test_search_marks_high_importance_and_accepts_dict_payload():
    result = build_service().search(hours=24, limit=20)
    assert result["count"] == 2
    assert result["items"][1]["importance"] == "high"


@pytest.mark.parametrize("hours,limit", [(0, 10), (24, 0), (169, 10), (24, 101)])
def test_search_rejects_unbounded_requests(hours: int, limit: int):
    with pytest.raises(ValueError):
        build_service().search(hours=hours, limit=limit)

