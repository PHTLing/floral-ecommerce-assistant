import json
from langchain_ollama import ChatOllama

from app.agent.message_utils import get_message_content
from app.agent.prompts import (
    SEARCH_RESPONSE_PROMPT,
    DETAIL_RESPONSE_PROMPT,
    ORDER_CONFIRMATION_PROMPT,
)

llm_response = ChatOllama(model="qwen3:8b", temperature=0)

def build_search_response(user_text: str, search_result: dict):
    prompt = SEARCH_RESPONSE_PROMPT.format(
        user_text=user_text,
        search_text=search_result.get("text", ""),
    )
    return llm_response.invoke([{"role": "user", "content": prompt}])

def build_detail_response(flower_name: str, flower_id, detail_result: dict):
    prompt = DETAIL_RESPONSE_PROMPT.format(
        flower_name=flower_name,
        flower_id=flower_id,
        detail=detail_result.get("detail") or detail_result.get("text"),
    )
    return llm_response.invoke([{"role": "user", "content": prompt}])

def build_order_confirmation(customer: dict, order_result: dict):
    prompt = ORDER_CONFIRMATION_PROMPT.format(
        ten_khach=customer.get("ten_khach"),
        sdt=customer.get("sdt"),
        dia_chi=customer.get("dia_chi"),
        loai_hang=customer.get("loai_hang"),
        so_luong=customer.get("so_luong"),
        ngay_nhan=customer.get("ngay_nhan"),
        gio_nhan=customer.get("gio_nhan"),
        tool_text=order_result.get("text", ""),
    )
    return llm_response.invoke([{"role": "user", "content": prompt}])

def build_missing_fields_question(missing_fields: list[str], field_labels: dict) -> str:
    labels = [field_labels.get(f, f) for f in missing_fields]

    if len(missing_fields) >= 5:
        return (
            "Để hoàn tất đơn hàng, anh/chị vui lòng cung cấp: "
            "tên, số điện thoại, địa chỉ giao hàng, mẫu hoa, số lượng, "
            "ngày nhận và giờ nhận ạ."
        )

    return "Anh/chị vui lòng cung cấp thêm: " + ", ".join(labels)


def build_fallback_response(user_text: str) -> str:
    t = (user_text or "").lower()

    if "giá" in t:
        return "Anh/chị muốn tìm hoa trong khoảng giá bao nhiêu ạ?"
    if "đặt" in t:
        return "Anh/chị muốn đặt mẫu hoa nào ạ?"

    return (
        "Em chưa hiểu rõ ý anh/chị 🌷 "
        "Anh/chị đang muốn tìm hoa, xem chi tiết mẫu hoa, hay đặt hàng ạ?"
    )


def get_last_ai_text(state: dict) -> str:
    if not state.get("messages"):
        return ""

    last = state["messages"][-1]
    return get_message_content(last)


def extract_frontend_data(state: dict) -> list[dict]:
    # Trích xuất thông tin để trả về cho Frontend (React) - 
    """
    Ưu tiên lấy từ state.search_results hoặc selected_flower thay vì parse lại tool message.
    """
    if state.get("last_tool") == "search_flowers":
        return [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "price": item.get("price_display"),
                "image": item.get("image"),
                "url": item.get("url"),
                "description": item.get("description", ""),
            }
            for item in state.get("search_results", [])
        ]

    selected = state.get("selected_flower")
    if selected:
        return [selected]

    return []