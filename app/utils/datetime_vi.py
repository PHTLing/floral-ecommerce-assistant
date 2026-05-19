from __future__ import annotations

import re
from datetime import datetime

def normalize_text(text: str | None):
    return (text or "").lower().strip()

def parse_time_vietnamese(raw_time: str):
    """Chuẩn hóa giờ từ các dạng tiếng Việt hoặc tiếng Anh.
    Hỗ trợ: "17:00", "17h", "17h30", "5 giờ chiều", "3pm", v.v.
    Trả về (chuỗi "HH:MM", None) hoặc (None, "error_msg") nếu lỗi.
    """
    original = raw_time or ""
    text = normalize_text(original)
    text = re.sub(r"\s+", "", text)

    if not text:
        return None, "Vui lòng nhập giờ nhận."

    # 17:00 hoặc 17h30
    match = re.match(r"^(\d{1,2})[h:](\d{2})$", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}", None

        return None, f"Giờ {hour}:{minute} không hợp lệ. Vui lòng nhập từ 00:00 đến 23:59."

    # 5h, 17h, 5giờ
    match = re.match(r"^(\d{1,2})(h|giờ)$", text)
    if match:
        hour = int(match.group(1))

        if 0 <= hour <= 23:
            return f"{hour:02d}:00", None

        return None, f"Giờ {hour} không hợp lệ. Vui lòng nhập từ 0 đến 23."

    # 5 giờ chiều, 8 sáng, 9 tối
    match = re.match(r"^(\d{1,2})(giờ)?(sáng|chiều|tối|đêm)?$", text)
    if match:
        hour_raw = int(match.group(1))
        period = match.group(3) or ""

        if period in ["chiều", "tối"]:
            hour = hour_raw if hour_raw >= 12 else hour_raw + 12
        elif period == "sáng":
            # 8 sáng -> 08:00, 12 sáng hơi mơ hồ nhưng xử lý thành 00:00
            hour = 0 if hour_raw == 12 else hour_raw
        elif period == "đêm":
            # 1 đêm -> 01:00, 10 đêm -> 22:00
            hour = hour_raw if hour_raw < 6 else hour_raw + 12
        else:
            hour = hour_raw

        if 0 <= hour <= 23:
            return f"{hour:02d}:00", None

        return None, f"Giờ '{original}' không hợp lệ."

    # 5pm, 5am
    match = re.match(r"^(\d{1,2})(am|pm)$", text)
    if match:
        hour_raw = int(match.group(1))
        period = match.group(2)

        if hour_raw < 1 or hour_raw > 12:
            return None, f"Giờ '{original}' không hợp lệ."

        if period == "pm":
            hour = hour_raw if hour_raw == 12 else hour_raw + 12
        else:
            hour = 0 if hour_raw == 12 else hour_raw

        return f"{hour:02d}:00", None

    return None, (
        f"Định dạng giờ '{original}' chưa được hỗ trợ. "
        "Vui lòng nhập ví dụ: 17:00, 16h30, 5h, 5 giờ chiều."
    )

def extract_date_and_time_combined(text: str):
    """
    Trích ngày và giờ từ câu có dạng:
    - 17/5 lúc 17h
    - 17/5/2026 lúc 5 giờ chiều
    - nhận ngày 20/6 vào 15:00
    """
    source = text or ""

    date_str = None
    date_patterns = [
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}/\d{1,2}\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, source)
        if match:
            date_str = match.group(0)
            break

    time_str = None

    # lúc 5 giờ chiều
    match = re.search(
        r"(?:lúc|vào)\s+(\d{1,2}\s*giờ\s*(?:sáng|chiều|tối|đêm)?)",
        source,
        re.IGNORECASE,
    )
    if match:
        time_str = match.group(1).strip()
    else:
        # lúc 17h30, lúc 17:00, vào 3pm
        match = re.search(
            r"(?:lúc|vào)\s+(\d{1,2}(?::\d{2})?(?:h\d{0,2})?(?:am|pm)?)",
            source,
            re.IGNORECASE,
        )
        if match:
            time_str = match.group(1).strip()

    return date_str, time_str

def normalize_order_date(raw_date: str | None) -> tuple[str | None, str | None]:
    """
    Chuẩn hóa ngày nhận về dd/mm/YYYY.

    Hỗ trợ:
    - dd/mm
    - dd/mm/yyyy
    - yyyy-mm-dd
    - yyyy/mm/dd

    Nếu thiếu năm thì mặc định năm hiện tại.
    Không cho phép ngày trong quá khứ.
    """
    text = normalize_text(raw_date)
    text = text.replace(".", "/").replace("-", "/")
    text = re.sub(r"\s+", "", text)

    today = datetime.now().date()

    if not text:
        return None, "Vui lòng nhập ngày nhận."

    candidates: list[tuple[int, int, int]] = []

    # yyyy/mm/dd
    match = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        candidates.append((year, month, day))

    # dd/mm[/yyyy]
    match = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", text)
    if match:
        first = int(match.group(1))
        second = int(match.group(2))
        year_raw = match.group(3)

        year = int(year_raw) if year_raw else today.year
        if year < 100:
            year += 2000

        # Ưu tiên kiểu Việt Nam dd/mm.
        day = first
        month = second

        candidates.append((year, month, day))

    for year, month, day in candidates:
        try:
            parsed_date = datetime(year, month, day).date()
        except ValueError:
            continue

        if parsed_date < today:
            return (
                None,
                f"Ngày nhận {parsed_date.strftime('%d/%m/%Y')} đã qua. "
                "Vui lòng chọn ngày hôm nay hoặc trong tương lai.",
            )

        return parsed_date.strftime("%d/%m/%Y"), None

    return None, (
        "Ngày nhận không hợp lệ. "
        "Vui lòng nhập theo dạng dd/mm hoặc dd/mm/yyyy, ví dụ: 25/12 hoặc 25/12/2026."
    )