from __future__ import annotations

from easy_tdx_mcp.cninfo_compat import CninfoHttpClient


def test_cninfo_compat_builds_traceable_urls_and_type_fallback(monkeypatch):
    client = CninfoHttpClient()
    monkeypatch.setattr(
        client,
        "_get_json",
        lambda url: {
            "stockList": [{"code": "688017", "orgId": "9900041602"}]
        },
    )
    captured = {}

    def response(url, payload):
        captured.update(payload)
        return {
            "announcements": [
                {
                    "announcementTitle": "2025 年年度报告",
                    "announcementTypeName": None,
                    "adjunctType": "PDF",
                    "announcementTime": 1774656000000,
                    "announcementId": "12345",
                    "adjunctUrl": "finalpage/2026-03-28/12345.PDF",
                }
            ]
        }

    monkeypatch.setattr(client, "_post_form", response)

    frame = client.get_announcements("688017", count=10, page=2)

    assert captured["pageSize"] == "10"
    assert captured["pageNum"] == "2"
    assert captured["stock"] == "688017,9900041602"
    assert frame.iloc[0]["type"] == "PDF"
    assert "stockCode=688017" in frame.iloc[0]["url"]
    assert "announcementId=12345" in frame.iloc[0]["url"]
    assert "orgId=9900041602" in frame.iloc[0]["url"]
    assert "announcementTime=1774656000000" in frame.iloc[0]["url"]
    assert frame.iloc[0]["pdf_url"].endswith("12345.PDF")


def test_cninfo_compat_falls_back_to_conventional_org_id(monkeypatch):
    client = CninfoHttpClient()
    monkeypatch.setattr(client, "_get_json", lambda url: {"stockList": []})
    captured = {}

    def response(url, payload):
        captured.update(payload)
        return {"announcements": []}

    monkeypatch.setattr(client, "_post_form", response)

    frame = client.get_announcements("600519")

    assert frame.empty
    assert captured["stock"] == "600519,gssh0600519"
