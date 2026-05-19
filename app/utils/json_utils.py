# app/utils/json_utils.py

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any


def make_json_serializable(obj: Any) -> Any:
    """
    Chuyển đổi object không JSON-serializable thành dạng ghi JSON được.
    Hỗ trợ:
    - set
    - tuple
    - datetime/date
    - dict/list nested
    """
    if isinstance(obj, set):
        return list(obj)

    if isinstance(obj, tuple):
        return list(obj)

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, dict):
        return {
            key: make_json_serializable(value)
            for key, value in obj.items()
        }

    if isinstance(obj, list):
        return [
            make_json_serializable(item)
            for item in obj
        ]

    return obj


def dumps_json(data: Any, **kwargs: Any) -> str:
    """
    Dump JSON với ensure_ascii=False mặc định.
    """
    return json.dumps(
        make_json_serializable(data),
        ensure_ascii=False,
        **kwargs,
    )


def extract_json_object(text: str | None) -> dict[str, Any] | None:
    """
    Extract JSON object đầu tiên từ text LLM.

    Ví dụ LLM trả:
    'Đây là JSON: {"a": 1}'
    -> {"a": 1}
    """
    if not text:
        return None

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        return None

    try:
        parsed = json.loads(match.group())
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed