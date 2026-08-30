from __future__ import annotations

import json

from easy_tdx.mac.commands.symbol_belong_board import SymbolBelongBoardCmd


def test_symbol_belong_board_decodes_gb18030_names_without_replacement():
    rows = [[12, 1, "880301", "𠮷酒", 100.0, 99.0, 0, 0, 0]]
    body = bytes(27) + json.dumps(rows, ensure_ascii=False).encode("gb18030")

    result = SymbolBelongBoardCmd(1, "600519").parse_response(body)

    assert result[0].board_name == "𠮷酒"
    assert "�" not in result[0].board_name
