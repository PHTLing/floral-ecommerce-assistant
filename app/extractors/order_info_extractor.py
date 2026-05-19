import json
import re
from langchain_ollama import ChatOllama

from app.utils.datetime_vi import (
    extract_date_and_time_combined,
    normalize_order_date,
    parse_time_vietnamese,
)

llm_extract = ChatOllama(model="qwen3:4b", temperature=0)


def extract_phone(text: str):
    """
    Bắt SĐT dạng:
    - 0774046929
    - sdt 0774046929
    - sđt: 0774046929
    - +84...
    """
    match = re.search(r"(0|\+84)[\d\s\.\-]{8,14}", text or "")
    if not match:
        return None

    phone = re.sub(r"\D", "", match.group())

    # Nếu user nhập +84..., có thể convert về 0...
    if phone.startswith("84") and len(phone) >= 10:
        phone = "0" + phone[2:]

    return phone

def extract_customer_name(text: str):
    """
    Bắt tên khách từ:
    - Tôi tên Linh
    - mình tên Linh
    - tên là Linh
    """
    patterns = [
        r"(?:tôi tên|mình tên|em tên|anh tên|chị tên)\s+([A-Za-zÀ-ỹ\s]+?)(?=,|\.|sđt|sdt|số điện thoại|điện thoại|$)",
        r"(?:tên là)\s+([A-Za-zÀ-ỹ\s]+?)(?=,|\.|sđt|sdt|số điện thoại|điện thoại|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return " ".join(match.group(1).strip().split())

    return None


def extract_quantity(text: str):
    match = re.search(r"(?:số lượng|sl|lấy|đặt|mua)\s*(\d{1,3})", text or "", re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(r"\b(\d{1,3})\s*(?:bó|giỏ|hộp|cái)\b", text or "", re.IGNORECASE)
    if match:
        return match.group(1)

    return None

def extract_address(text: str):
    """
    Bắt địa chỉ từ:
    - giao về TP HCM
    - giao tới 123 Nguyễn Huệ
    - ship về Quận 1
    """
    patterns = [
        r"(?:giao về|giao tới|giao đến|ship về|ship tới|địa chỉ)\s+(.+?)(?=\s+(?:vào|lúc|ngày)\b|,|\.|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                return value

    return None

def extract_flower_from_state_or_text(text: str, state: dict):
    """
    Ưu tiên đúng:
    1. Nếu user nhắc tên mẫu trong search_results -> lấy mẫu đó.
    2. Nếu user viết sau 'lấy/đặt/mua 1 bó ...' -> lấy text đó.
    3. Cuối cùng mới fallback selected_flower.
    """
    t = (text or "").lower()

    # 1. Ưu tiên tên mẫu xuất hiện trực tiếp trong câu user
    search_results = state.get("search_results") or []
    for item in search_results:
        name = item.get("name") or ""
        if name and name.lower() in t:
            flower_id = item.get("id")
            return f"{name} - {flower_id}" if flower_id else name

    # 2. Regex lấy tên mẫu sau cụm lấy/đặt/mua
    # Ví dụ: "tôi lấy 1 bó Dreaming, sdt..."
    match = re.search(
        r"(?:lấy|đặt|mua)\s+\d*\s*(?:bó|giỏ|hộp|cái)?\s*(.+?)(?=,|\.|\s+sđt|\s+sdt|\s+giao|\s+ship|\s+vào|\s+lúc|\s+ngày|$)",
        text or "",
        re.IGNORECASE,
    )
    if match:
        flower_name = match.group(1).strip()

        # Tránh lấy nhầm câu chung chung như "giao về TP HCM"
        invalid_starts = ["giao", "ship", "về", "tới", "đến", "vào", "lúc", "ngày"]
        if flower_name and not any(flower_name.lower().startswith(x) for x in invalid_starts):
            return flower_name

    # 3. Fallback selected_flower cuối cùng
    selected = state.get("selected_flower") or {}
    if selected.get("name"):
        flower_id = selected.get("id")
        return f"{selected.get('name')} - {flower_id}" if flower_id else selected.get("name")

    return None


def extract_date_time(text: str):
    result = {}

    date_raw, time_raw = extract_date_and_time_combined(text)

    if date_raw:
        normalized_date, date_error = normalize_order_date(date_raw)
        if normalized_date:
            result["ngay_nhan"] = normalized_date

    if time_raw:
        normalized_time, time_error = parse_time_vietnamese(time_raw)
        if normalized_time:
            result["gio_nhan"] = normalized_time

    return result


def extract_with_llm(text: str):
    prompt = f"""
        Từ đoạn sau, trích xuất JSON các trường nếu có:
        {{
        "ten_khach": null,
        "sdt": null,
        "dia_chi": null,
        "loai_hang": null,
        "so_luong": null,
        "ngay_nhan": null,
        "gio_nhan": null
        }}

    Quy tắc:
    - Chỉ trả về JSON.
    - Không giải thích.
    - Không thêm markdown.
    - Nếu không có field thì để null.
    - Giữ nguyên tiếng Việt.
    - "giao về/giao tới/ship về" thường là địa chỉ.
    - "lúc/vào lúc" thường là giờ nhận.
    - "ngày" hoặc dạng dd/mm là ngày nhận.

     Đoạn:
    {text}
    """

    try:
        response = llm_extract.invoke([{"role": "user", "content": prompt}])
        match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if not match:
            return {}
        data = json.loads(match.group())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def clean_llm_data(data: dict):
    """
    Bỏ field rỗng từ LLM.
    """
    cleaned = {}

    for key, value in (data or {}).items():
        if value not in [None, "", []]:
            cleaned[key] = value

    return cleaned


def extract_order_info(user_text: str, state: dict) -> dict:
    extracted = {}

    name = extract_customer_name(user_text)
    if name:
        extracted["ten_khach"] = name

    phone = extract_phone(user_text)
    if phone:
        extracted["sdt"] = phone

    quantity = extract_quantity(user_text)
    if quantity:
        extracted["so_luong"] = quantity

    address = extract_address(user_text)
    if address:
        extracted["dia_chi"] = address

    flower = extract_flower_from_state_or_text(user_text, state)
    if flower:
        extracted["loai_hang"] = flower

    extracted.update(extract_date_time(user_text))

    # LLM chỉ bổ sung field còn thiếu, không overwrite field regex đã bắt được
    llm_data = clean_llm_data(extract_with_llm(user_text))
    for key, value in llm_data.items():
        if key not in extracted:
            extracted[key] = value

    if flower:
        extracted["loai_hang"] = flower

    return extracted