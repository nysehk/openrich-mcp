"""Minimal CNInfo client compatible with easy_tdx's announcement API.

The request contract and URL construction follow the MIT-licensed
``handsomejustin/easy_tdx`` CNInfo client (copyright easy-tdx contributors).
Only read-only search is retained here; PDF download is intentionally excluded.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from urllib import parse
from urllib import request as urlrequest

import pandas as pd


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_STOCK_MAP_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
_PDF_BASE = "http://static.cninfo.com.cn/"
_COLUMNS = [
    "title",
    "type",
    "date",
    "url",
    "code",
    "org_id",
    "announcement_id",
    "announcement_time",
    "pdf_url",
]


class CninfoHttpClient:
    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._org_ids: dict[str, str] = {}

    def _get_json(self, url: str) -> Any:
        request = urlrequest.Request(url, headers={"User-Agent": _USER_AGENT})
        with urlrequest.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_form(self, url: str, payload: dict[str, str]) -> Any:
        request = urlrequest.Request(
            url,
            data=parse.urlencode(payload).encode("utf-8"),
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.cninfo.com.cn/new/disclosure",
                "Origin": "https://www.cninfo.com.cn",
            },
            method="POST",
        )
        with urlrequest.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _resolve_org_id(self, code: str) -> str:
        if not self._org_ids:
            try:
                payload = self._get_json(_STOCK_MAP_URL)
                stock_list = payload.get("stockList", []) if isinstance(payload, dict) else []
                self._org_ids.update(
                    {
                        item["code"]: item["orgId"]
                        for item in stock_list
                        if isinstance(item, dict) and "code" in item and "orgId" in item
                    }
                )
            except Exception:
                # The query can still work for conventional identifiers.
                pass
        if code in self._org_ids:
            return self._org_ids[code]
        if code.startswith("6"):
            return f"gssh0{code}"
        if code.startswith(("4", "8")):
            return f"gsbj0{code}"
        return f"gssz0{code}"

    def get_announcements(
        self,
        code: str,
        *,
        count: int = 30,
        page: int = 1,
    ) -> pd.DataFrame:
        org_id = self._resolve_org_id(code)
        payload = {
            "stock": f"{code},{org_id}",
            "tabName": "fulltext",
            "pageSize": str(count),
            "pageNum": str(page),
            "column": "",
            "category": "",
            "plate": "",
            "seDate": "",
            "searchkey": "",
            "secid": "",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        response = self._post_form(_QUERY_URL, payload)
        items = response.get("announcements", []) if isinstance(response, dict) else []
        records: list[dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            announcement_id = str(item.get("announcementId", "") or "")
            announcement_time = int(item.get("announcementTime", 0) or 0)
            detail_query = parse.urlencode(
                {
                    "stockCode": code,
                    "announcementId": announcement_id,
                    "orgId": org_id,
                    "announcementTime": announcement_time,
                }
            )
            adjunct_url = str(item.get("adjunctUrl", "") or "")
            records.append(
                {
                    "title": str(item.get("announcementTitle", "") or ""),
                    "type": str(
                        item.get("announcementTypeName")
                        or item.get("adjunctType")
                        or ""
                    ),
                    "date": (
                        datetime.fromtimestamp(announcement_time / 1000).strftime(
                            "%Y-%m-%d"
                        )
                        if announcement_time
                        else ""
                    ),
                    "url": (
                        "https://www.cninfo.com.cn/new/disclosure/detail?"
                        f"{detail_query}"
                    ),
                    "code": code,
                    "org_id": org_id,
                    "announcement_id": announcement_id,
                    "announcement_time": announcement_time,
                    "pdf_url": f"{_PDF_BASE}{adjunct_url}" if adjunct_url else "",
                }
            )
        return pd.DataFrame(records, columns=_COLUMNS)
