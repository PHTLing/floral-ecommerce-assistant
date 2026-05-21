import json
import re
from langchain_ollama import ChatOllama

from app.utils.datetime_vi import (
    extract_date_and_time_combined,
    normalize_order_date,
    parse_time_vietnamese,
)

from app.utils.order_items import make_item

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
    - giao đến số 35, Nguyễn Trãi, quận 3, TP HCM vào lúc 4 giờ chiều
    - ship về Quận 1 ngày mai
    """
    patterns = [
        r"(?:giao về|giao tới|giao đến|giao|ship về|ship tới|ship đến|địa chỉ)\s+(.+?)(?=\s+(?:vào lúc|vào|lúc|ngày|ngày nhận|giờ nhận)\b|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            value = match.group(1).strip()

            # Dọn dấu câu cuối nếu có
            value = value.strip(" ,.")

            if value:
                return value

    return None

GENERIC_PRODUCT_WORDS = {
    "bó",
    "giỏ",
    "hộp",
    "cái",
    "mẫu",
    "hoa",
    "bông",
    "1 bó",
    "1 giỏ",
    "1 hộp",
}


def is_valid_flower_name(value: str | None) -> bool:
    if not value:
        return False

    text = value.strip().lower()

    if not text:
        return False

    if text in GENERIC_PRODUCT_WORDS:
        return False

    invalid_starts = [
        "giao",
        "ship",
        "về",
        "tới",
        "đến",
        "vào",
        "lúc",
        "ngày",
        "đường",
        "địa chỉ",
    ]

    if any(text.startswith(prefix) for prefix in invalid_starts):
        return False

    # Nếu chỉ toàn số hoặc chỉ 1 từ quá chung chung thì bỏ
    if text.isdigit():
        return False

    return True

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

    # 2. Nếu user nói rõ "mẫu X"
    match = re.search(
        r"(?:mẫu|hoa mẫu|sản phẩm)\s+(.+?)(?=,|\.|\s+sđt|\s+sdt|\s+giao|\s+ship|\s+vào|\s+lúc|\s+ngày|$)",
        text or "",
        re.IGNORECASE,
    )
    if match:
        flower_name = match.group(1).strip()
        if is_valid_flower_name(flower_name):
            return flower_name

    # 3. Nếu user nói "lấy 1 bó Dreaming" hoặc "đặt thêm 1 bó Just for you"
    match = re.search(
        r"(?:lấy thêm|đặt thêm|mua thêm|lấy|đặt|mua)\s+"
        r"(?:\d+\s*)?"
        r"(?:bó|giỏ|hộp|cái)?\s+"
        r"(.+?)(?=,|\.|\s+sđt|\s+sdt|\s+giao|\s+ship|\s+vào|\s+lúc|\s+ngày|$)",
        text or "",
        re.IGNORECASE,
    )
    if match:
        flower_name = match.group(1).strip()
        if is_valid_flower_name(flower_name):
            return flower_name

    # 4. Nếu câu hiện tại không có tên mẫu mới,
    # ưu tiên giữ mẫu đang nằm trong customer_info/order_draft
    current_order = state.get("customer_info") or {}
    if current_order.get("loai_hang"):
        return current_order.get("loai_hang")

    order_draft = state.get("order_draft") or {}
    if order_draft.get("loai_hang"):
        return order_draft.get("loai_hang")
    
    # 5. Fallback selected_flower cuối cùng
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

def is_add_more_request(text: str) -> bool:
    text = (text or "").lower()

    keywords = [
        "lấy thêm",
        "đặt thêm",
        "mua thêm",
        "thêm 1",
        "thêm một",
        "cho thêm",
        "muốn lấy thêm",
        "muốn đặt thêm",
    ]

    return any(keyword in text for keyword in keywords)


def is_reuse_previous_delivery_request(text: str) -> bool:
    text = (text or "").lower()

    keywords = [
        "như trên",
        "thông tin như trên",
        "giao như trên",
        "địa chỉ như trên",
        "giờ như trên",
        "ngày giờ như trên",
        "thời gian như trên",
        "vẫn giao",
        "vẫn địa chỉ",
        "giao đến thông tin như trên",
        "như trước đó",
        "đã cung cấp trước đó",
        "đã nói trước đó",
        "giữ nguyên thông tin giao hàng trước đó",
        "giữ nguyên địa chỉ giao hàng trước đó",
        "giữ nguyên thời gian giao hàng trước đó",
        "giữ nguyên ngày giờ giao hàng trước đó",
    ]

    return any(keyword in text for keyword in keywords)

def extract_order_info(user_text: str, state: dict) -> dict:
    extracted = {}
    
    name = extract_customer_name(user_text)
    if name:
        extracted["ten_khach"] = name

    phone = extract_phone(user_text)
    if phone:
        extracted["sdt"] = phone

    quantity = extract_quantity(user_text)

    address = extract_address(user_text)
    if address:
        extracted["dia_chi"] = address

    flower = extract_flower_from_state_or_text(user_text, state)

    extracted.update(extract_date_time(user_text))

    llm_data = clean_llm_data(extract_with_llm(user_text))
    for key, value in llm_data.items():
        if key == "loai_hang" and not is_valid_flower_name(str(value)):
            continue

        if key not in extracted:
            extracted[key] = value

    if is_reuse_previous_delivery_request(user_text) or is_add_more_request(user_text):
        last_delivery = state.get("last_delivery_info") or {}

        for field in ["ten_khach", "sdt", "dia_chi", "ngay_nhan", "gio_nhan"]:
            if not extracted.get(field) and last_delivery.get(field):
                extracted[field] = last_delivery[field]

    # Ưu tiên flower đã resolve bằng rule/state/text
    if flower:
        loai_hang = flower
    else:
        loai_hang = extracted.get("loai_hang")

    so_luong = quantity or extracted.get("so_luong")

    item = make_item(loai_hang, so_luong)

    if item:
        extracted["items"] = [item]

    # Từ giờ không trả loai_hang/so_luong top-level nữa
    extracted.pop("loai_hang", None)
    extracted.pop("so_luong", None)

    return extracted