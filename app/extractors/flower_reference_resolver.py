# 1. Nếu user nói "mẫu thứ 2" -> lấy từ state.search_results[1]
# 2. Nếu user nói tên có trong search_results -> lấy đúng item đó
# 3. Nếu user nói "mẫu này" -> lấy selected_flower
# 4. Nếu có ID trong câu -> dùng ID
# 5. Nếu có tên mẫu bằng regex -> dùng tên
# 6. Cuối cùng mới gọi LLM extract JSON

import json
import re
from langchain_ollama import ChatOllama

llm_extract = ChatOllama(model="qwen3:4b", temperature=0)


def extract_ordinal_reference(text: str):
    match = re.search(r"mẫu\s*(?:thứ\s*)?(\d{1,2})", (text or "").lower())
    if not match:
        return None
    return int(match.group(1))


def extract_id_reference(text: str):
    match = re.search(r"\b(?:id|mã|mã số|mã nội bộ)\s*[:\-]?\s*(\d{3,7})\b", text or "", re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def extract_name_by_regex(text: str):
    if not text:
        return None

    match = re.search(
        r"(?:mẫu|tên hoa|lấy)\s+[:\-]?\s*(.+?)(?:\s+(?:gồm|là gì|giá bao|bao nhiêu|chi tiết|thì).*)?$",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    name = match.group(1).strip()
    name = re.sub(
        r"\s+(?:gồm|là gì|giá bao|bao nhiêu|chi tiết|thì|gì|nào).*$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    return name.strip() or None


def find_in_search_results_by_name(text: str, search_results: list):
    t = (text or "").lower()

    for item in search_results or []:
        name = (item.get("name") or "").lower()
        if name and name in t:
            return {
                "flower_name": item.get("name"),
                "flower_id": item.get("id") or item.get("ma_so") or item.get("maSo"),
                "source": "search_results_name",
                "confidence": 0.95,
            }

    return None


def resolve_by_ordinal(index: int, search_results: list):
    if not index or not search_results:
        return None

    if 1 <= index <= len(search_results):
        item = search_results[index - 1]
        return {
            "flower_name": item.get("name"),
            "flower_id": item.get("id") or item.get("ma_so") or item.get("maSo"),
            "source": "search_results_ordinal",
            "confidence": 0.95,
        }

    return None


def resolve_by_selected_flower(state: dict):
    selected = state.get("selected_flower") or {}
    if not selected:
        return None

    return {
        "flower_name": selected.get("name"),
        "flower_id": selected.get("id"),
        "source": "selected_flower",
        "confidence": 0.8,
    }


def extract_by_llm(text: str):
    prompt = f"""
Trích xuất JSON từ câu sau:
"{text}"

Schema:
{{"flower_name": "...", "flower_id": null}}

Chỉ trả về JSON.
"""

    try:
        response = llm_extract.invoke([{"role": "user", "content": prompt}])
        match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if not match:
            return None

        parsed = json.loads(match.group())
        if not parsed.get("flower_name") and not parsed.get("flower_id"):
            return None

        return {
            "flower_name": parsed.get("flower_name"),
            "flower_id": parsed.get("flower_id"),
            "source": "llm_extract",
            "confidence": 0.6,
        }
    except Exception:
        return None


def resolve_flower_reference(user_text: str, state: dict) -> dict:
    search_results = state.get("search_results") or []

    ordinal = extract_ordinal_reference(user_text)
    resolved = resolve_by_ordinal(ordinal, search_results)
    if resolved:
        return resolved

    resolved = find_in_search_results_by_name(user_text, search_results)
    if resolved:
        return resolved

    flower_id = extract_id_reference(user_text)
    flower_name = extract_name_by_regex(user_text)

    if flower_id or flower_name:
        return {
            "flower_name": flower_name,
            "flower_id": flower_id,
            "source": "regex",
            "confidence": 0.75,
        }

    if any(k in (user_text or "").lower() for k in ["mẫu này", "cái này", "bó này"]):
        resolved = resolve_by_selected_flower(state)
        if resolved:
            return resolved

    resolved = extract_by_llm(user_text)
    if resolved:
        return resolved

    resolved = resolve_by_selected_flower(state)
    if resolved:
        return resolved

    return {
        "flower_name": None,
        "flower_id": None,
        "source": "not_found",
        "confidence": 0.0,
    }