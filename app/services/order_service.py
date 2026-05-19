import re
import time
from datetime import datetime

from app.repositories.order_repository import save_order
from app.utils.datetime_vi import normalize_order_date, parse_time_vietnamese, extract_date_and_time_combined

# - Định nghĩa field bắt buộc của đơn hàng
# - Gộp thông tin đơn hàng cũ + thông tin mới
# - Kiểm tra thiếu field
# - Validate và chuẩn hóa SĐT
# - Validate và chuẩn hóa ngày nhận
# - Validate và chuẩn hóa giờ nhận
# - Tạo order_id
# - Gọi repository để lưu đơn
# - Trả kết quả chuẩn cho node/tool/API

REQUIRED_ORDER_FIELDS = [
    "ten_khach",
    "sdt",
    "dia_chi",
    "loai_hang",
    "so_luong",
    "ngay_nhan",
    "gio_nhan",
]

FIELD_LABELS = {
    "ten_khach": "Tên khách hàng",
    "sdt": "Số điện thoại",
    "dia_chi": "Địa chỉ giao hàng",
    "loai_hang": "Tên mẫu hoa",
    "so_luong": "Số lượng",
    "ngay_nhan": "Ngày nhận",
    "gio_nhan": "Giờ nhận",
}


def merge_order_info(old: dict, new: dict):
    merged = dict(old or {})
    for key, value in (new or {}).items():
        if value not in [None, "", []]:
            merged[key] = value
    return merged


def get_missing_fields(order_info: dict):
    return [
        field
        for field in REQUIRED_ORDER_FIELDS
        if not order_info.get(field)
    ]

def get_missing_order_labels(missing_fields: list[str]) -> list[str]:
    """
    Convert field key sang nhãn thân thiện để hỏi khách.
    """
    return [
        FIELD_LABELS.get(field, field)
        for field in missing_fields
    ]

def normalize_phone(phone: str):
    cleaned = re.sub(r"\D", "", str(phone or ""))

    if not phone:
        return None, "Vui lòng nhập số điện thoại."

    if len(cleaned) < 9 or len(cleaned) > 12:
        return None, "SĐT không hợp lệ. Vui lòng nhập lại số điện thoại."

    return cleaned, None


def normalize_quantity(quantity):
    text = str(quantity or "").strip()
    if not text:
        return None, "Vui lòng cho biết số lượng hoa muốn đặt."

    match = re.search(r"\d+", text)
    if not match:
        return None, "Số lượng không hợp lệ. Vui lòng nhập số lượng, ví dụ: 1 hoặc 2."

    quantity = int(match.group())

    if quantity <= 0:
        return None, "Số lượng phải lớn hơn 0."

    return str(quantity), None


def validate_and_normalize_order(order_info: dict):
    normalized = dict(order_info or {})
    errors: dict[str, str] = {}

    missing_fields = get_missing_fields(normalized)
    if missing_fields:
        return normalized, missing_fields, errors

    # 1. SĐT
    phone, phone_error = normalize_phone(normalized.get("sdt"))
    if phone_error:
        errors["sdt"] = phone_error
    else:
        normalized["sdt"] = phone

    # 2. Số lượng
    quantity, quantity_error = normalize_quantity(normalized.get("so_luong"))
    if quantity_error:
        errors["so_luong"] = quantity_error
    else:
        normalized["so_luong"] = quantity

    # 3. Ngày nhận
    normalized_date, date_error = normalize_order_date(normalized.get("ngay_nhan"))
    if date_error:
        errors["ngay_nhan"] = date_error
    else:
        normalized["ngay_nhan"] = normalized_date
        normalized["ngay_nhan_parsed"] = datetime.strptime(
            normalized_date,
            "%d/%m/%Y",
        ).isoformat()

    # 4. Giờ nhận
    normalized_time, time_error = parse_time_vietnamese(normalized.get("gio_nhan"))
    if time_error:
        errors["gio_nhan"] = time_error
    else:
        normalized["gio_nhan"] = normalized_time

    return normalized, [], errors


def build_order_id() -> str:
    """
    Tạo mã đơn hàng.
    Format FLORA-{timestamp}
    """
    return f"FLORA-{int(time.time())}"

def create_order(order_info: dict) -> dict:
    """
    Validate, normalize và lưu đơn hàng.

    Hàm này là điểm chính mà checkout_node hoặc process_order tool nên gọi.
    """
    normalized, missing_fields, errors = validate_and_normalize_order(order_info)

    if missing_fields:
        missing_labels = get_missing_order_labels(missing_fields)
        return {
            "success": False,
            "status": "missing_fields",
            "text": f"Đơn hàng còn thiếu thông tin: {', '.join(missing_labels)}.",
            "missing_fields": missing_fields,
            "errors": {},
            "order": normalized,
        }

    if errors:
        first_field = next(iter(errors))
        return {
            "success": False,
            "status": "invalid_fields",
            "text": errors[first_field],
            "invalid_field": first_field,
            "errors": errors,
            "order": normalized,
        }

    order_id = build_order_id()
    order_record = {
        "order_id": order_id,
        "created_at": datetime.now().isoformat(),
        **normalized,
    }

    try:
        save_order(order_record)
    except Exception as exc:
        return {
            "success": False,
            "status": "save_failed",
            "text": f"Lỗi khi lưu đơn: {exc}",
            "errors": {"storage": str(exc)},
            "order": order_record,
        }

    return {
        "success": True,
        "status": "created",
        "text": f"THÀNH CÔNG: Đơn hàng {order_id} đã được ghi nhận.",
        "order_id": order_id,
        "order": order_record,
    }