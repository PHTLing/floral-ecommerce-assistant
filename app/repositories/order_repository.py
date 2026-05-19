from __future__ import annotations

import json
import os
from typing import Any


ORDERS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "orders.json",
)


def load_orders() -> list[dict[str, Any]]:
    """
    Đọc toàn bộ đơn hàng từ orders.json.
    Nếu file chưa tồn tại thì trả list rỗng.
    """
    if not os.path.exists(ORDERS_FILE):
        return []

    with open(ORDERS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        return []

    return data


def save_orders(orders: list[dict[str, Any]]) -> None:
    """
    Ghi toàn bộ danh sách đơn hàng xuống orders.json.
    """
    os.makedirs(os.path.dirname(ORDERS_FILE), exist_ok=True)

    with open(ORDERS_FILE, "w", encoding="utf-8") as file:
        json.dump(orders, file, ensure_ascii=False, indent=2)


def save_order(order_record: dict[str, Any]) -> dict[str, Any]:
    """
    Append một đơn mới vào orders.json.
    """
    orders = load_orders()
    orders.append(order_record)
    save_orders(orders)
    return order_record