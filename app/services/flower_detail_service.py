# Chứa logic chi tiết hoa hiện trong get_flower_details.

# Hiện logic này tìm theo ID trước, thử id/ma_so dạng int/string, rồi fallback query tên và scoring

import re

from app.database import query_flowers
from app.utils.text import normalize_text, fuzzy_score, extract_id


def strip_id_suffix(text: str):
    text = normalize_text(text)
    text = re.sub(r"\s*-\s*\d{3,6}\s*$", "", text)
    return " ".join(text.split())


def score_candidate(query: str, meta: dict):
    name = meta.get("ten_hoa", "")
    desc = meta.get("mo_ta", "") or meta.get("description", "")
    components = meta.get("thanh_phan", "") or ""
    raw_text = f"{name} {desc} {components}"

    query_norm = normalize_text(query)
    name_norm = normalize_text(name)
    name_core = strip_id_suffix(name)
    query_core = strip_id_suffix(query)

    score = fuzzy_score(query, name, raw_text)

    if query_norm == name_norm:
        score += 2.0
    if query_core and query_core == name_core:
        score += 1.5
    if query_core and query_core in name_norm:
        score += 1.0
    if query_core and name_core in query_core:
        score += 0.8

    return score


def find_candidates_by_id(query_text: str, flower_id):
    if not flower_id:
        return []

    query_core = strip_id_suffix(query_text)

    filters = [
        {"id": {"$eq": flower_id}},
        {"id": {"$eq": str(flower_id)}},
        {"ma_so": {"$eq": flower_id}},
        {"ma_so": {"$eq": str(flower_id)}},
    ]

    for filter_cond in filters:
        result = query_flowers(
            query_core or query_text,
            filter_cond=filter_cond,
            n_results=1,
        )
        candidates = result.get("metadatas", [[]])[0] or []
        if candidates:
            return candidates

    return []


def find_candidates_by_name(query_text: str):
    query_core = strip_id_suffix(query_text)
    result = query_flowers(query_core or query_text, None, n_results=10)
    return result.get("metadatas", [[]])[0] or []


def metadata_to_detail(meta: dict):
    return {
        "name": meta.get("ten_hoa", "Đang cập nhật"),
        "components": meta.get("thanh_phan", "Đang cập nhật"),
        "price": meta.get("gia_so", 0),
        "id": meta.get("id") or meta.get("ma_so"),
        "description": meta.get("mo_ta", ""),
        "url": meta.get("url", ""),
        "image": meta.get("hinh_anh", ""),
        "purpose": meta.get("muc_dich", ""),
    }


def format_detail_text(detail: dict):
    return (
        f"Tên: {detail['name']} (ID: {detail['id']})\n"
        f"Thành phần: {detail['components']}\n"
        f"Giá: {detail['price']} VNĐ\n"
        f"Mô tả: {detail['description']}\n"
        f"Sử dụng: {detail['purpose']}\n"
    )


def get_flower_detail_service(flower_name: str, flower_id: int = None):
    query_text = (flower_name or "").strip()

    if not query_text and not flower_id:
        return {
            "success": False,
            "text": "Xin lỗi, bạn chưa cung cấp tên mẫu hoa cần tra cứu.",
            "detail": None,
        }

    effective_id = flower_id or extract_id(query_text)

    candidates = find_candidates_by_id(query_text, effective_id)

    if not candidates and query_text:
        candidates = find_candidates_by_name(query_text)

    if not candidates:
        return {
            "success": False,
            "text": f"Xin lỗi, tiệm không tìm thấy thông tin chi tiết cho mẫu '{flower_name}'.",
            "detail": None,
        }

    best = max(candidates, key=lambda meta: score_candidate(query_text, meta))
    detail = metadata_to_detail(best)

    return {
        "success": True,
        "text": format_detail_text(detail),
        "detail": detail,
    }