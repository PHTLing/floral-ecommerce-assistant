# app/utils/text.py

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_text(text: Any) -> str:
    """
    Chuẩn hóa text cơ bản:
    - None -> ""
    - lower
    - strip
    - gom nhiều khoảng trắng thành một
    """
    if text is None:
        return ""

    value = str(text).lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def remove_vietnamese_accents(text: Any) -> str:
    """
    Bỏ dấu tiếng Việt để hỗ trợ so khớp nhẹ.
    Ví dụ: 'hoa hồng' -> 'hoa hong'
    """
    value = str(text or "")
    normalized = unicodedata.normalize("NFD", value)
    without_accents = "".join(
        char
        for char in normalized
        if unicodedata.category(char) != "Mn"
    )
    return without_accents.replace("đ", "d").replace("Đ", "D")


def token_set(text: Any) -> set[str]:
    """
    Tách token dạng chữ/số.
    """
    return set(re.findall(r"\w+", normalize_text(text)))


def fuzzy_score(query: Any, *texts: Any) -> float:
    """
    Tính điểm overlap token đơn giản giữa query và nhiều text.

    Dùng cho search/detail ranking nhẹ.
    """
    query_tokens = token_set(query)
    if not query_tokens:
        return 0.0

    target_tokens: set[str] = set()
    for text in texts:
        target_tokens |= token_set(text)

    if not target_tokens:
        return 0.0

    overlap = len(query_tokens & target_tokens)
    return overlap / len(query_tokens)


def extract_id(text: Any, min_digits: int = 3, max_digits: int = 7) -> int | None:
    """
    Extract ID/mã sản phẩm từ text.
    Ví dụ:
    - 'mẫu 15568'
    - 'ID: 3167'
    - 'Hoa hồng - 3167'
    """
    pattern = rf"\b(\d{{{min_digits},{max_digits}}})\b"
    match = re.search(pattern, str(text or ""))

    if not match:
        return None

    return int(match.group(1))


def clean_none_values(data: dict[str, Any]) -> dict[str, Any]:
    """
    Loại bỏ các field rỗng khỏi dict.
    """
    return {
        key: value
        for key, value in data.items()
        if value not in [None, "", [], {}]
    }


def format_vnd(price: Any) -> str:
    """
    Format giá tiền VND.
    """
    try:
        value = int(price)
    except Exception:
        return "Giá liên hệ"

    if value <= 0:
        return "Giá liên hệ"

    return f"{value:,} VNĐ"