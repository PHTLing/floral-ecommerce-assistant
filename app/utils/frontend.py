# app/utils/frontend.py

from __future__ import annotations

from typing import Any

from app.utils.text import format_vnd


def normalize_search_item_for_frontend(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("ten_hoa") or "Hoa đẹp",
        "price": item.get("price_display") or format_vnd(item.get("price") or item.get("gia_so")),
        "image": item.get("image") or item.get("hinh_anh") or "",
        "url": item.get("url", ""),
        "description": item.get("description") or item.get("mo_ta") or "",
    }


def normalize_detail_for_frontend(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": detail.get("id"),
        "name": detail.get("name") or detail.get("ten_hoa") or "Hoa đẹp",
        "price": detail.get("price_display") or format_vnd(detail.get("price") or detail.get("gia_so")),
        "image": detail.get("image") or detail.get("hinh_anh") or "",
        "url": detail.get("url", ""),
        "description": detail.get("description") or detail.get("mo_ta") or "",
        "components": detail.get("components") or detail.get("thanh_phan") or "",
        "purpose": detail.get("purpose") or detail.get("muc_dich") or "",
    }


from app.utils.text import format_vnd


def normalize_search_item_for_frontend(item: dict):
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("ten_hoa") or "Hoa đẹp",
        "price": item.get("price_display") or format_vnd(item.get("price") or item.get("gia_so")),
        "image": item.get("image") or item.get("hinh_anh") or "",
        "url": item.get("url", ""),
        "description": item.get("description") or item.get("mo_ta") or "",
    }


def normalize_detail_for_frontend(detail: dict):
    return {
        "id": detail.get("id"),
        "name": detail.get("name") or detail.get("ten_hoa") or "Hoa đẹp",
        "price": detail.get("price_display") or format_vnd(detail.get("price") or detail.get("gia_so")),
        "image": detail.get("image") or detail.get("hinh_anh") or "",
        "url": detail.get("url", ""),
        "description": detail.get("description") or detail.get("mo_ta") or "",
        "components": detail.get("components") or detail.get("thanh_phan") or "",
        "purpose": detail.get("purpose") or detail.get("muc_dich") or "",
    }


def extract_frontend_data(state: dict):
    current_intent = state.get("current_intent")
    last_tool = state.get("last_tool")

    # Khi đang đặt hàng / thu thập thông tin đơn thì không hiển thị ảnh nữa
    if current_intent == "checkout" or last_tool == "process_order":
        return []

    if last_tool == "search_flowers":
        display_items = (
            state.get("recommended_results")
            or state.get("search_results")
            or []
        )

        return [
            normalize_search_item_for_frontend(item)
            for item in display_items
        ]

    if last_tool == "get_flower_details":
        detail = state.get("selected_flower_detail") or state.get("selected_flower")
        if not detail:
            return []

        return [normalize_detail_for_frontend(detail)]

    return []