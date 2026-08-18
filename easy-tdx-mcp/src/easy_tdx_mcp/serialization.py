from __future__ import annotations

import base64
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
import math
from pathlib import Path
from typing import Any

import pandas as pd


def jsonable(value: Any) -> Any:
    """Convert fork-core results to strict JSON values without losing provenance."""
    if isinstance(value, pd.DataFrame):
        return [jsonable(row) for row in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return jsonable(value.to_dict())
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        return {
            "encoding": "base64",
            "byte_count": len(raw),
            "content": base64.b64encode(raw).decode("ascii"),
        }
    if is_dataclass(value) and not isinstance(value, type):
        return jsonable(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return jsonable(value.to_dict())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "item"):
        try:
            return jsonable(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    return value
