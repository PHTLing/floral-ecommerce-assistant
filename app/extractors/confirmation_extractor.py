def is_order_confirmation_yes(text: str) -> bool:
    text = (text or "").lower().strip()

    yes_keywords = [
        "đúng",
        "đúng rồi",
        "ok",
        "oke",
        "okay",
        "xác nhận",
        "chốt",
        "đồng ý",
        "chuẩn",
        "được",
        "đúng ạ",
        "đúng rồi ạ",
        "xác nhận đơn",
        "ổn",
        "chính xác",
        "yes"
    ]

    return any(keyword in text for keyword in yes_keywords)


def is_order_correction(text: str) -> bool:
    text = (text or "").lower().strip()

    correction_keywords = [
        "sửa",
        "đổi",
        "cập nhật",
        "thay",
        "sai",
        "nhầm",
        "không đúng",
        "không phải",
        "chỉnh",
        "thêm",
        "bỏ",
        "rút",
        "hủy",
    ]

    return any(keyword in text for keyword in correction_keywords)

def is_order_confirmation_no_or_wait(text: str) -> bool:
    text = (text or "").lower().strip()

    keywords = [
        "chưa",
        "để tôi xem lại",
        "đợi chút",
        "khoan",
        "chưa đúng",
        "không xác nhận",
        "hủy",
        "thôi",
    ]

    return any(k in text for k in keywords)