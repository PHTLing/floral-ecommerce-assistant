# Chứa toàn bộ logic search hiện đang nằm trong search_flowers.

# Hiện search logic gồm: infer loại hoa/màu, build filter Chroma, thử filter từ chặt tới lỏng, dedupe, scoring, format kết quả.


from app.database import query_flowers
from app.utils.constants import FLOWER_TYPE_ALIASES, COLOR_ALIASES, STYLE_ALIASES, COLORS, STYLES
from app.utils.text import normalize_text, fuzzy_score


def infer_flower_type(text: str):
    normalized = normalize_text(text)
    for canonical, aliases in FLOWER_TYPE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def infer_color(text: str):
    normalized = normalize_text(text)
    for color in COLORS:
        if color in normalized:
            return color
    return None


def build_filter(
    max_price=None,
    min_price=None,
    color=None,
    style=None,
    flower_type=None,
    include_type=True,
    include_color=True,
    include_style=True,
):
    conditions = []

    if max_price:
        conditions.append({"gia_so": {"$lte": max_price}})
    if min_price:
        conditions.append({"gia_so": {"$gte": min_price}})
    if include_color and color:
        conditions.append({"color": {"$eq": color}})
    if include_style and style:
        conditions.append({"style": {"$eq": style}})
    if include_type and flower_type and flower_type.lower() != "hoa":
        conditions.append({"primary_flower_type": {"$eq": flower_type}})

    if len(conditions) > 1:
        return {"$and": conditions}
    if len(conditions) == 1:
        return conditions[0]
    return None


def extract_candidates(query_text, filter_cond, limit=8):
    try:
        result = query_flowers(query_text, filter_cond, n_results=limit)
        return result.get("metadatas", [[]])[0] or []
    except Exception as exc:
        print(f"[flower_search_service] Query failed filter={filter_cond}: {exc}")
        return []


def metadata_to_flower_item(meta: dict, query: str, effective_type: str, effective_color: str, style: str):
    raw_price = meta.get("gia_so", 0)
    price_display = f"{raw_price:,} VNĐ" if raw_price and raw_price > 1000 else "Giá liên hệ"

    name = meta.get("ten_hoa", "")
    desc = meta.get("mo_ta", "") or meta.get("description", "")
    tags = [t.strip().lower() for t in meta.get("purpose", "").split(",")] if meta.get("purpose") else []

    primary_flower_type = normalize_text(meta.get("primary_flower_type", ""))
    flower_types_text = normalize_text(meta.get("flower_types_text", ""))

    score = fuzzy_score(query, name, desc)

    query_norm = normalize_text(query)
    type_norm = normalize_text(effective_type)
    color_norm = normalize_text(effective_color)
    style_norm = normalize_text(style)

    if primary_flower_type and primary_flower_type in query_norm:
        score += 1.5
    if type_norm and primary_flower_type == type_norm:
        score += 1.0
    if type_norm and type_norm in flower_types_text:
        score += 1.0

    meta_text = normalize_text(" ".join([name, desc, meta.get("purpose", ""), flower_types_text]))

    if color_norm and color_norm in meta_text:
        score += 0.5
    if style_norm and style_norm in meta_text:
        score += 0.35
    if any(tag in query_norm for tag in tags if tag):
        score += 0.25

    return {
        "id": meta.get("id") or meta.get("ma_so"),
        "name": name,
        "description": desc,
        "price": raw_price,
        "price_display": price_display,
        "tags": tags,
        "match_score": score,
        "primary_flower_type": meta.get("primary_flower_type", ""),
        "flower_types_text": meta.get("flower_types_text", ""),
        "image": meta.get("hinh_anh", ""),
        "url": meta.get("url", ""),
        "raw_meta": meta,
    }


def process_search_results(state: dict, filtered_results: list[dict], intro: str):
    """
    Cập nhật state với kết quả tìm kiếm đã được LLM lọc qua.
    """
    # Cập nhật kết quả tìm kiếm đã lọc vào state
    state["search_results"] = filtered_results
    state["search_context"] = {"intro": intro}

    return state

def search_flowers_service(
    query: str,
    type_of_flower: str = None,
    min_price: int = None,
    max_price: int = None,
    color: str = None,
    style: str = None,
):
    effective_type = type_of_flower or infer_flower_type(query)
    effective_color = color or infer_color(query)

    search_text = effective_type or query or "hoa"

    filter_variants = [
        build_filter(max_price, min_price, effective_color, style, effective_type, True, True, True),
        build_filter(max_price, min_price, effective_color, style, effective_type, True, True, False),
        build_filter(max_price, min_price, effective_color, style, effective_type, True, False, False),
        build_filter(max_price, min_price, effective_color, style, effective_type, False, False, False),
        None,
    ]

    seen = set()
    metas = []
    used_relaxed_search = False

    for idx, filter_cond in enumerate(filter_variants):
        candidates = extract_candidates(search_text, filter_cond, limit=8)

        if idx > 0 and candidates:
            used_relaxed_search = True

        for meta in candidates:
            key = str(meta.get("id") or meta.get("ma_so") or meta.get("url") or meta.get("ten_hoa") or "")
            if key and key not in seen:
                seen.add(key)
                metas.append(meta)

        if len(metas) >= 8:
            break

    flower_list = [
        metadata_to_flower_item(meta, query, effective_type, effective_color, style)
        for meta in metas
    ]

    flower_list.sort(key=lambda x: x["match_score"], reverse=True)
    print(f"[flower_search_service] Found {len(flower_list)} candidates, used_relaxed_search={used_relaxed_search}")
    if flower_list:
        top_score = flower_list[0]["match_score"]
        strong_matches = [
            item for item in flower_list
            if item["match_score"] >= max(0.8, top_score * 0.6)
        ]
        flower_list = (strong_matches or flower_list)[:5]

    items_for_frontend = [
        {
            "id": item["id"],
            "name": item["name"],
            "image": item["image"],
            "price_display": item["price_display"],
            "url": item.get("url", ""),
            "description": item.get("description", ""),
        }
        for item in flower_list
    ]
    print(f"[flower_search_service] Returning {len(items_for_frontend)} items for frontend")
    intro = (
        "Không tìm thấy mẫu khớp hoàn toàn. Dưới đây là một số mẫu gần nhất để anh/chị tham khảo:\n"
        if used_relaxed_search and flower_list
        else "Các mẫu tương ứng đã được tìm thấy:\n"
    )

    flower_strings = [
        f"- Tên hoa: {item['name']} [ID: {item['id']}]\n"
        f"  Giá: {item['price_display']}\n"
        f"  Mô tả: {item['description']}\n"
        for item in flower_list
    ]
    print(f"[flower_search_service] Intro: {intro}")
    print(f"[flower_search_service] Flower strings: {flower_strings}")
    # Cập nhật state với kết quả đã lọc
    state = {}
    process_search_results(state, items_for_frontend, intro)

    return {
        "success": True,
        "text": intro + "\n".join(flower_strings),
        "items": items_for_frontend,
        "results": flower_list,
        "meta": {
            "query": query,
            "min_price": min_price,
            "max_price": max_price,
            "color": color,
            "style": style,
            "used_relaxed_search": used_relaxed_search,
        },
    }

