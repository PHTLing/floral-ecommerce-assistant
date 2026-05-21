from __future__ import annotations


INVALID_PRODUCT_VALUES = {
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


def is_valid_item(item: dict) -> bool:
    loai_hang = str(item.get("loai_hang") or "").strip()
    so_luong = str(item.get("so_luong") or "").strip()

    if not loai_hang or not so_luong:
        return False

    if loai_hang.lower() in INVALID_PRODUCT_VALUES:
        return False

    return True


def make_item(loai_hang: str | None, so_luong: str | int | None = "1") -> dict | None:
    item = {
        "loai_hang": loai_hang,
        "so_luong": str(so_luong or "1"),
    }

    if not is_valid_item(item):
        return None

    return item


def ensure_order_items(order: dict) -> list[dict]:
    """
    Chuẩn hóa order về items[].
    Nếu order cũ có loai_hang/so_luong top-level thì convert sang 1 item.
    """
    items = list(order.get("items") or [])

    valid_items = [item for item in items if is_valid_item(item)]

    if valid_items:
        return valid_items

    legacy_item = make_item(
        order.get("loai_hang"),
        order.get("so_luong") or "1",
    )

    return [legacy_item] if legacy_item else []


def normalize_order_to_items(order: dict) -> dict:
    """
    Trả về order chỉ dùng items[], bỏ loai_hang/so_luong top-level.
    """
    normalized = dict(order or {})
    normalized["items"] = ensure_order_items(normalized)
    normalized.pop("loai_hang", None)
    normalized.pop("so_luong", None)
    return normalized


def append_item_to_order(order: dict, item: dict) -> dict:
    """
    Append item mới vào order và luôn trả về format items[].
    """
    normalized = normalize_order_to_items(order)
    items = ensure_order_items(normalized)

    if is_valid_item(item):
        items.append(item)

    normalized["items"] = items
    normalized.pop("loai_hang", None)
    normalized.pop("so_luong", None)

    return normalized


def order_has_items(order: dict) -> bool:
    return bool(ensure_order_items(order))