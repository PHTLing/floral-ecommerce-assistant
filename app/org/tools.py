from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional
from app.database import query_flowers # Import hàm từ file database
import json, time, os, re
from datetime import datetime


FLOWER_TYPE_ALIASES = {
    "hoa hồng": ["hoa hồng", "hồng", "rose", "only rose"],
    "hoa hướng dương": ["hoa hướng dương", "hướng dương", "sunflower"],
    "hoa sen đá": ["hoa sen đá", "sen đá", "succulent"],
    "hoa cúc": ["hoa cúc", "cúc", "daisy"],
    "hoa ly": ["hoa ly", "ly", "lily", "loa kèn"],
    "hoa lan": ["hoa lan", "lan", "orchid"],
    "hoa baby": ["hoa baby", "baby"],
    "hoa tulip": ["hoa tulip", "tulip"],
    "hoa đồng tiền": ["hoa đồng tiền", "đồng tiền"],
    "hoa cẩm chướng": ["hoa cẩm chướng", "cẩm chướng"],
    "hoa cẩm tú cầu": ["hoa cẩm tú cầu", "cẩm tú cầu", "hydrangea"],
    "hoa mẫu đơn": ["hoa mẫu đơn", "mẫu đơn", "peony"],
    "hoa cát tường": ["hoa cát tường", "cát tường", "lisianthus"],
    "hoa lan hồ điệp": ["hoa lan hồ điệp", "lan hồ điệp", "phalaenopsis"],
}

COLORS = [
    "đỏ", "trắng", "hồng", "vàng", "cam", "tím",
    "xanh lá", "xanh dương", "xanh ngọc"
]

def _normalize(s: str):
    return (s or "").lower().strip()

def _token_set(s: str):
    return set(re.findall(r'\w+', _normalize(s)))

def _fuzzy_score(query: str, name: str, description: str):
    q_tokens = _token_set(query)
    if not q_tokens:
        return 0.0
    name_tokens = _token_set(name)
    desc_tokens = _token_set(description)
    overlap = len(q_tokens & (name_tokens | desc_tokens))
    return overlap / len(q_tokens)

def _extract_id(s: str):
    m = re.search(r'(\d{3,6})', s)
    return int(m.group(1)) if m else None


def _infer_flower_type(text: str):
    normalized = _normalize(text)
    for canonical, aliases in FLOWER_TYPE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def _infer_color(text: str):
    normalized = _normalize(text)
    for color in COLORS:
        if color in normalized:
            return color
    return None


def _parse_time_vietnamese(raw_time: str):
    """Chuẩn hóa giờ từ các dạng tiếng Việt hoặc tiếng Anh.
    Hỗ trợ: "17:00", "17h", "17h30", "5 giờ chiều", "3pm", v.v.
    Trả về (chuỗi "HH:MM", None) hoặc (None, "error_msg") nếu lỗi.
    """
    text = _normalize(raw_time).replace(" ", "")
    
    # Trường hợp đã là HH:MM hoặc HHhMM hoặc HHhMM
    match = re.match(r"^(\d{1,2})[h:](\d{2})$", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}", None
        return None, f"Giờ {hour}:{minute} không hợp lệ (0-23:59)."
    
    # Trường hợp "5h", "5giờ", "17h"
    match = re.match(r"^(\d{1,2})(h|giờ)$", text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return f"{hour:02d}:00", None
        return None, f"Giờ {hour} không hợp lệ (0-23)."
    
    # Trường hợp "5 giờ chiều/tối/sáng/đêm"
    match = re.match(r"^(\d{1,2})(giờ)?(sáng|chiều|tối|đêm)?$", text)
    if match:
        hour_raw = int(match.group(1))
        period = match.group(3) or ""
        
        if period in ("chiều", "tối"):
            if hour_raw < 12:
                hour = hour_raw + 12
            else:
                hour = hour_raw
        elif period == "sáng":
            if hour_raw < 6:
                hour = hour_raw + 12
            else:
                hour = hour_raw
        elif period == "đêm":
            if hour_raw < 6:
                hour = hour_raw
            else:
                hour = hour_raw + 12
        else:
            hour = hour_raw
        
        if 0 <= hour <= 23:
            return f"{hour:02d}:00", None
        return None, f"Giờ không hợp lệ."
    
    # Trường hợp "5pm", "5am"
    match = re.match(r"^(\d{1,2})(am|pm)$", text)
    if match:
        hour_raw = int(match.group(1))
        period = match.group(2)
        
        if period == "pm":
            hour = hour_raw if hour_raw == 12 else hour_raw + 12
        else:
            hour = 0 if hour_raw == 12 else hour_raw
        
        if 0 <= hour <= 23:
            return f"{hour:02d}:00", None
        return None, f"Giờ không hợp lệ."
    
    return None, f"Định dạng giờ '{raw_time}' không được hỗ trợ. Vui lòng nhập 17:00, 16h30, 5h, '5 giờ chiều', v.v."


def _extract_date_and_time_combined(text: str):
    """Trích cả ngày và giờ từ một đoạn text dạng '17/5 lúc 17h' hoặc '17/5/2026 lúc 5 giờ chiều'.
    Trả về (date_str, time_str) hoặc (None, None) nếu không tìm được cả hai.
    """
    date_patterns = [
        r"(\d{1,2})/(\d{1,2})/(\d{2,4})",
        r"(\d{1,2})/(\d{1,2})",
    ]
    
    date_str = None
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(0)
            break
    
    # Regex để tìm giờ: sau "lúc" hoặc "vào", capture đủ dòng với các từ tiếng Việt (chiều, sáng, v.v.)
    time_str = None
    # Pattern 1: "lúc/vào <time> giờ <period>" e.g. "lúc 5 giờ chiều"
    match = re.search(r"(?:lúc|vào)\s+(\d+\s+giờ\s+(?:sáng|chiều|tối|đêm)?)", text, re.IGNORECASE)
    if match:
        time_str = match.group(1).strip()
    # Pattern 2: "lúc/vào <time>" (đơn giản hơn) - capture cho đến khi gặp space hoặc ký tự không phải time
    else:
        match = re.search(r"(?:lúc|vào)\s+(\d+(?::\d{2})?(?:h(?:\d{2})?)?(?:am|pm)?)\s*", text, re.IGNORECASE)
        if match:
            time_str = match.group(1).strip()
    
    return date_str, time_str


def _normalize_order_date(raw_date: str):
    """Chuẩn hóa ngày nhận về dd/mm/YYYY.
    Hỗ trợ d/m, m/d, d/m/y, m/d/y, yyyy-mm-dd.
    Nếu thiếu năm thì mặc định năm hiện tại.
    """
    text = _normalize(raw_date).replace(".", "/").replace("-", "/")
    text = re.sub(r"\s+", "", text)
    today = datetime.now().date()

    if not text:
        return None, "Ngày nhận không hợp lệ."

    candidates = []

    # yyyy/mm/dd hoặc yyyy/m/d
    match = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", text)
    if match:
        candidates.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))

    # dd/mm[/yyyy] hoặc mm/dd[/yyyy]
    match = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", text)
    if match:
        first = int(match.group(1))
        second = int(match.group(2))
        year_raw = match.group(3)
        year = int(year_raw) if year_raw else today.year
        if year < 100:
            year += 2000

        # Ưu tiên kiểu Việt Nam dd/mm.
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            month, day = first, second
        else:
            day, month = first, second

        candidates.append((year, month, day))

    for year, month, day in candidates:
        try:
            parsed_date = datetime(year, month, day).date()
        except ValueError:
            continue

        if parsed_date < today:
            return None, f"Ngày nhận {parsed_date.strftime('%d/%m/%Y')} đã qua so với hôm nay. Vui lòng chọn ngày trong tương lai."

        return parsed_date.strftime("%d/%m/%Y"), None

    return None, "Ngày nhận không hợp lệ. Vui lòng nhập theo dạng dd/mm/yyyy hoặc mm/dd/yyyy; nếu thiếu năm, hệ thống sẽ tự hiểu là năm hiện tại."

class SearchFlowerInput(BaseModel):
    query: str = Field(..., description="Từ khóa tìm hoa")

    type_of_flower: Optional[str] = Field(
        default=None,
        description="Loại hoa (ví dụ: 'hồng', 'cúc', 'ly', hoặc 'hoa' nếu khách không nói rõ)"
    )

    color: Optional[str] = Field(
        default=None,
        description="Màu sắc (ví dụ: 'đỏ', 'trắng', 'hồng', 'vàng', 'cam', 'tím', 'xanh lá', 'xanh dương')"
    )

    min_price: Optional[int] = Field(
        default=None,
        description="Giá tối thiểu, bỏ qua nếu khách không nói"
    )

    max_price: Optional[int] = Field(
        default=None,
        description="Giá tối đa, bỏ qua nếu khách không nói"
    )

    style: Optional[str] = Field(
        default=None,
        description="Phong cách (ví dụ: 'pastel', 'sang trọng', 'nhẹ nhàng', 'hiện đại')"
    )
    
@tool(args_schema=SearchFlowerInput)
def search_flowers(query: str, type_of_flower: str = None, min_price: int = None, max_price: int = None, color: str = None, style: str = None):
    """Dùng để tìm kiếm các mẫu hoa trên TOÀN BỘ cơ sở dữ liệu của tiệm dựa trên nhu cầu chung. 
    Luôn gọi công cụ này khi khách hàng thay đổi tiêu chí về giá cả hoặc loại hoa, KHÔNG phụ thuộc vào việc bạn đã gợi ý gì trước đó.
    Nếu khách không chỉ định loại hoa mà chỉ nói về giá/dịp, hãy dùng query='hoa'.
   """
    
    effective_type = type_of_flower or _infer_flower_type(query)
    effective_color = color or _infer_color(query)

    def build_filter(include_type=True, include_color=True, include_style=True):
        conditions = []
        if max_price:
            conditions.append({"gia_so": {"$lte": max_price}})
        if min_price:
            conditions.append({"gia_so": {"$gte": min_price}})
        if include_color and effective_color:
            conditions.append({"color": {"$eq": effective_color}})
        if include_style and style:
            conditions.append({"style": {"$eq": style}})
        if include_type and effective_type and effective_type.lower() != "hoa":
            conditions.append({"primary_flower_type": {"$eq": effective_type}})

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
            print(f"⚠️ [DEBUG TOOL] Query failed with filter={filter_cond}: {exc}")
            return []

    # Thử từ chặt tới lỏng để không mất gợi ý khi filter quá strict
    search_text = effective_type or query or "hoa"
    filter_variants = [
        build_filter(include_type=True, include_color=True, include_style=True),
        build_filter(include_type=True, include_color=True, include_style=False),
        build_filter(include_type=True, include_color=False, include_style=False),
        build_filter(include_type=True, include_color=False, include_style=True),
        build_filter(include_type=False, include_color=False, include_style=False),
        None,
    ]

    seen_keys = set()
    matched_metas = []
    used_relaxed_search = False
    for idx, filter_cond in enumerate(filter_variants):
        metas = extract_candidates(search_text, filter_cond, limit=8)
        if idx > 0 and metas:
            used_relaxed_search = True
        for meta in metas:
            unique_key = str(meta.get('id') or meta.get('ma_so') or meta.get('url') or meta.get('ten_hoa') or '')
            if unique_key and unique_key not in seen_keys:
                seen_keys.add(unique_key)
                matched_metas.append(meta)
        if len(matched_metas) >= 8:
            break

    print(f"🕵️ [DEBUG CHROMA] Số lượng DB thực tế nhả ra: {len(matched_metas)}")

    flower_list = []
    flower_strings = []
    for meta in matched_metas:
        raw_price = meta.get('gia_so', 0)
        price_display = f"{raw_price:,} VNĐ" if raw_price and raw_price > 1000 else "Giá liên hệ"
        name = meta.get('ten_hoa', '')
        desc = meta.get('mo_ta', '') or meta.get('description', '')
        tags = [t.strip().lower() for t in meta.get('purpose', '').split(',')] if meta.get('purpose') else []
        primary_flower_type = _normalize(meta.get('primary_flower_type', ''))
        flower_types_text = _normalize(meta.get('flower_types_text', ''))
        score = _fuzzy_score(query, name, desc)
        query_norm = _normalize(query)
        effective_type_norm = _normalize(effective_type)
        effective_color_norm = _normalize(effective_color)
        style_norm = _normalize(style)

        # Ưu tiên khớp trực tiếp với loại hoa canonical
        if primary_flower_type and primary_flower_type in query_norm:
            score += 1.5
        if effective_type_norm and primary_flower_type == effective_type_norm:
            score += 1.0
        if effective_type_norm and effective_type_norm in flower_types_text:
            score += 1.0

        # Điểm mềm cho màu sắc / phong cách để giữ khả năng gợi ý
        meta_text = _normalize(" ".join([name, desc, meta.get('purpose', ''), flower_types_text]))
        if effective_color_norm and effective_color_norm in meta_text:
            score += 0.5
        if style_norm and style_norm in meta_text:
            score += 0.35
        if any(tag in query_norm for tag in tags if tag):
            score += 0.25

        # Build structured item
        item = {
            "id": meta.get('id') or meta.get('ma_so'),
            "name": name,
            "description": desc,
            "price": raw_price,
            "price_display": price_display,
            "tags": tags,
            "match_score": score,
            "primary_flower_type": meta.get('primary_flower_type', ''),
            "flower_types_text": meta.get('flower_types_text', ''),
            "image": meta.get('hinh_anh', ''),
            "url": meta.get('url', ''),
            "raw_meta": meta
        }
        flower_list.append(item)

    # 1. SẮP XẾP FLOWER_LIST TRƯỚC
    flower_list.sort(key=lambda x: x['match_score'], reverse=True)
    if flower_list:
        top_score = flower_list[0]['match_score']
        strong_matches = [item for item in flower_list if item['match_score'] >= max(0.8, top_score * 0.6)]
        flower_list = (strong_matches or flower_list)[:5]

    # Nếu không có kết quả chặt nhưng có kết quả lỏng, báo rõ đây là gợi ý gần đúng
    if used_relaxed_search and flower_list:
        intro_text = "Không tìm thấy mẫu khớp hoàn toàn. Dưới đây là một số mẫu gần nhất để anh/chị tham khảo:\n"
    else:
        intro_text = "Các mẫu tương ứng đã được tìm thấy:\n"

    items_for_frontend = [
        {
            "id": item["id"],
            "name": item["name"],
            "image": item["image"],
            "price_display": item["price_display"],
            "url": item.get("url", "")
        }
        for item in flower_list
    ]

    # 2. TẠO FLOWER_STRINGS TỪ DANH SÁCH ĐÃ SẮP XẾP
    for item in flower_list:
        flower_info = (
            f"- Tên hoa: {item['name']} [ID: {item['id']}]\n" 
            f"  Giá: {item['price_display']}\n"
            f"  Mô tả: {item['description']}\n"
        )
        flower_strings.append(flower_info) # Biến nạp LLM

    print(f"🛠️ [DEBUG TOOL] Tổng số hoa tìm được để mớm cho AI: {len(flower_list)}")
    print(f"🛠️ [DEBUG TOOL] Nội dung mớm:\n" + "\n".join(flower_strings)) 

    return {
        "success": True,
        "text": intro_text + "\n".join(flower_strings),
        "items": items_for_frontend,
        "results": flower_list,
        "meta": {"query": query, "min_price": min_price, "max_price": max_price, "color": color, "style": style, "used_relaxed_search": used_relaxed_search}
    }

@tool
def get_flower_details(flower_name: str, flower_id: int = None):
    """Lấy thông tin chi tiết về thành phần của MỘT mẫu hoa cụ thể.
    QUY TẮC QUAN TRỌNG: Bạn PHẢI truyền vào tên đầy đủ kèm theo MÃ SỐ của hoa từ lịch sử chat.
    Ví dụ: Khách hỏi 'mẫu Spring rythm', bạn phải truyền đúng chuỗi 'Hoa hồng - Spring rythm - 3167'."""
    print(f"🔍 [DEBUG TOOL] get_flower_details được gọi với: flower_name='{flower_name}', flower_id='{flower_id}'")
    
    def _strip_id_suffix(text: str):
        text = _normalize(text)
        text = re.sub(r'\s*-\s*\d{3,6}\s*$', '', text)
        return " ".join(text.split())

    def _score_candidate(query: str, meta: dict):
        name = meta.get('ten_hoa', '')
        desc = meta.get('mo_ta', '') or meta.get('description', '')
        components = meta.get('thanh_phan', '') or ''
        raw_text = f"{name} {desc} {components}"

        query_norm = _normalize(query)
        name_norm = _normalize(name)
        name_core = _strip_id_suffix(name)
        query_core = _strip_id_suffix(query)

        score = _fuzzy_score(query, name, raw_text)

        if query_norm == name_norm:
            score += 2.0
        if query_core and query_core == name_core:
            score += 1.5
        if query_core and query_core in name_norm:
            score += 1.0
        if query_core and name_core in query_core:
            score += 0.8

        return score

    query_text = (flower_name or "").strip()
    if not query_text:
        return {
            "success": False,
            "text": "Xin lỗi, bạn chưa cung cấp tên mẫu hoa cần tra cứu.",
            "detail": None
        }

    query_core = _strip_id_suffix(query_text)

    if flower_id is None:
        effective_flower_id = _extract_id(query_text)
    else:
        effective_flower_id = flower_id
    print(f"🔍 [DEBUG TOOL] Hiệu quả ID được trích xuất: {effective_flower_id}")
    candidates = []
    exact_id_search = {}  # Initialize để tránh "referenced before assignment"

    if effective_flower_id:
        exact_id_search = query_flowers(
            query_core or query_text,
            filter_cond={"id": {"$eq": effective_flower_id}},
            n_results=1
        )
        candidates = exact_id_search.get("metadatas", [[]])[0] or []

        if not candidates:
            exact_id_search = query_flowers(
                query_core or query_text,
                filter_cond={"id": {"$eq": str(effective_flower_id)}},
                n_results=1
            )
            candidates = exact_id_search.get("metadatas", [[]])[0] or []

        if not candidates:
            exact_id_search = query_flowers(
                query_core or query_text,
                filter_cond={"ma_so": {"$eq": effective_flower_id}},
                n_results=1
            )
            candidates = exact_id_search.get("metadatas", [[]])[0] or []

        if not candidates:
            exact_id_search = query_flowers(
                query_core or query_text,
                filter_cond={"ma_so": {"$eq": str(effective_flower_id)}},
                n_results=1
            )
            candidates = exact_id_search.get("metadatas", [[]])[0] or []

    print(f"🔍 exact_id_search raw: {exact_id_search}")
    print(f"🔍 exact_id_search count: {len(candidates)}") 
    # 2) Không có ID hoặc tìm theo ID không ra thì mới tìm theo tên
    if not candidates:
        broad = query_flowers(query_core or query_text, None, n_results=10)
        candidates = broad.get('metadatas', [[]])[0] or []
        print(f"🔍 [DEBUG TOOL] Số ứng viên tìm được khi search theo tên: {len(candidates)}")

    if not candidates:
        return {
            "success": False,
            "text": f"Xin lỗi, tiệm không tìm thấy thông tin chi tiết cho mẫu '{flower_name}'. Bạn vui lòng cung cấp lại tên mẫu hoa rõ hơn.",
            "detail": None
        }

    best = None
    best_score = -1.0
    for meta in candidates:
        score = _score_candidate(query_text, meta)
        if score > best_score:
            best_score = score
            best = meta

    if not best:
        return {
            "success": False,
            "text": f"Xin lỗi, tiệm không tìm thấy thông tin chi tiết cho mẫu '{flower_name}'.",
            "detail": None
        }

    detail = {
        "name": best.get('ten_hoa', 'Đang cập nhật'),
        "components": best.get('thanh_phan', 'Đang cập nhật'),
        "price": best.get('gia_so', 0),
        "id": best.get('id') or best.get('ma_so'),
        "description": best.get('mo_ta', ''),
        "url": best.get('url', ''),
        "image": best.get('hinh_anh', ''),
        "purpose": best.get('muc_dich', '')
    }

    detail_str =(
        f"Tên: {detail['name']} (ID: {detail['id']})\n"
        f"Thành phần: {detail['components']}\n"
        f"Giá: {detail['price']} VNĐ\n"
        f"Mô tả: {detail['description']}\n"
        f"Sử dụng: {detail['purpose']}\n"
    )

    return {
        "success": True,
        "text": detail_str,
        "detail": detail
    }


@tool
def process_order(ten_khach: str, sdt: str, dia_chi: str, loai_hang: str, so_luong: str, ngay_nhan: str, gio_nhan: str):
    """Ghi nhận đơn hàng. Bắt buộc phải thu thập đủ 6 thông tin này.
    Args:
        ten_khach: Tên của khách hàng.
        sdt: Số điện thoại của khách.
        dia_chi: Địa chỉ giao hàng.
        loai_hang: Tên mẫu hoa khách chọn (lấy từ lịch sử chat, kèm ID).
        so_luong: Số lượng khách mua (ví dụ: '1').
        ngay_nhan: Thời gian nhận.
        gio_nhan: Thời gian nhận (chuyển về dạng 24h nếu khách nói '3 giờ chiều' -> '15:00').
    """
    
    # 1. Tự động gom lại thành dict để tận dụng code cũ của bạn
    order_data = {
        "ten_khach": ten_khach,
        "sdt": sdt,
        "dia_chi": dia_chi,
        "loai_hang": loai_hang,
        "so_luong": so_luong,
        "ngay_nhan": ngay_nhan,
        "gio_nhan": gio_nhan 
    }
    
    # Kiểm tra thiếu sót (Validation)
    missing = [k for k, v in order_data.items() if not v]
    
    if missing:
        return {"success": False, "text": f"THẤT BẠI: Đơn hàng còn thiếu các thông tin: {', '.join(missing)}. Hãy hỏi khách để bổ sung."}

    # Validate phone 
    sdt_clean = re.sub(r'\D', '', order_data['sdt'])
    if len(sdt_clean) < 9 or len(sdt_clean) > 12:
        return {"success": False, "text": "SĐT không hợp lệ. Vui lòng hỏi lại số điện thoại đúng.", "invalid_field": "sdt"}
    order_data['sdt'] = sdt_clean

    normalized_date, date_error = _normalize_order_date(order_data['ngay_nhan'])
    if not normalized_date:
        return {
            "success": False,
            "text": date_error,
            "invalid_field": "ngay_nhan"
        }
    order_data['ngay_nhan'] = normalized_date
    order_data['ngay_nhan_parsed'] = datetime.strptime(normalized_date, "%d/%m/%Y").isoformat()
 
    gio = order_data['gio_nhan']
    gio = re.sub(r'(\d{1,2})\s*(giờ|h|:)?\s*(\d{0,2})\s*(phút|p)?', lambda m: f"{int(m.group(1))}:{int(m.group(3) or 0):02d}", gio)
    order_data['gio_nhan'] = gio

    # Tạo order ID và lưu vào file orders.json
    order_id = f"FLORA-{int(time.time())}"
    order_record = {"order_id": order_id, "created_at": datetime.now().isoformat(), **order_data}

    orders_file = os.path.join(os.path.dirname(__file__), "orders.json")
    try:
        if os.path.exists(orders_file):
            with open(orders_file, "r", encoding="utf-8") as f:
                existing = json.load(f) or []
        else:
            existing = []
        existing.append(order_record)
        with open(orders_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"success": False, "text": f"Lỗi khi lưu đơn: {e}"}

    print(f"✅ ĐÃ TẠO ĐƠN HÀNG: {order_id}")
    return {"success": True, "text": f"THÀNH CÔNG: Đơn hàng {order_id} đã được ghi nhận. Hãy báo tin vui này cho khách!"}