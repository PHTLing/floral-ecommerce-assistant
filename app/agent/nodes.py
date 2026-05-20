from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage

from app.agent.message_utils import get_last_user_text, make_tool_message, make_ai_message
from app.agent.response_builder import (
    build_search_response,
    build_detail_response,
    build_order_confirmation,
    build_missing_fields_question,
    build_fallback_response,
    build_search_response_with_selection
)

from app.extractors.search_intent_extractor import get_query_intent
from app.extractors.flower_reference_resolver import resolve_flower_reference
from app.extractors.order_info_extractor import extract_order_info

from app.services.flower_search_service import search_flowers_service, process_search_results
from app.services.flower_detail_service import get_flower_detail_service
from app.services.order_service import (
    merge_order_info,
    get_missing_fields,
    FIELD_LABELS,
    get_missing_order_labels,
    create_order,
)

from app.utils.messages import get_last_user_text

llm = ChatOllama(model="qwen3:4b", temperature=0)

def merge_search_context(old_context: dict, new_context: dict) -> dict:
    merged = dict(old_context or {})
    for key, value in (new_context or {}).items():
        if value not in [None, "", []]:
            merged[key] = value
    return merged

def search_node(state: dict):
    user_text = get_last_user_text(state)

    intent = get_query_intent(user_text) or {}
    query = intent.get("flower") or "hoa"

    result = search_flowers_service(
        query=query,
        min_price=int(intent["min_price"]) if intent.get("min_price") else None,
        max_price=int(intent["max_price"]) if intent.get("max_price") else None,
        color=intent.get("color"),
        style=intent.get("style"),
    )
    search_results = result.get("results") or result.get("items") or []

    ai_response, recommended_results = build_search_response_with_selection(
        llm=llm,
        user_text=user_text,
        search_results=search_results,
    )

    return {
        "messages": [ai_response],
        "search_results": search_results,
        "search_context": merge_search_context(state.get("search_context", {}), intent),
        "selected_flower": None,
        "recommended_results": recommended_results,
        "last_tool": "search_flowers",
    }


def detail_node(state: dict):
    user_text = get_last_user_text(state)

    resolved = resolve_flower_reference(user_text, state)
    flower_name = resolved.get("flower_name")
    flower_id = resolved.get("flower_id")

    result = get_flower_detail_service(
        flower_name=flower_name,
        flower_id=flower_id,
    )

    tool_msg = make_tool_message("get_flower_details", result)
    ai_msg = build_detail_response(flower_name, flower_id, result)

    selected_flower = None
    if result.get("success") and result.get("detail"):
        d = result["detail"]
        selected_flower = {
            "id": d.get("id"),
            "name": d.get("name"),
            "price": d.get("price"),
            "price_display": f"{d.get('price', 0):,} VNĐ",
            "image": d.get("image"),
            "url": d.get("url"),
            "description": d.get("description"),
            "components": d.get("components"),
        }

    return {
        "messages": [tool_msg, ai_msg],
        "selected_flower": selected_flower,
        "last_tool": "get_flower_details",
    }


def checkout_node(state: dict):
    user_text = get_last_user_text(state)

    old_customer = state.get("customer_info") or {}
    extracted = extract_order_info(user_text, state)

    print("[Checkout] extracted:", extracted)

    customer = merge_order_info(old_customer, extracted)

    print("[Checkout] merged customer:", customer)

    missing = get_missing_fields(customer)

    if missing:
        
        question = build_missing_fields_question(missing, FIELD_LABELS)
        return {
            "messages": [
                AIMessage(content=question)
            ],
            "customer_info": customer,
            "pending_missing_fields": missing,
            "last_tool": "checkout",
        }

    result = create_order(customer)

    if not result.get("success"):
        pending = result.get("missing_fields") or []
        invalid = result.get("invalid_field")
        if invalid:
            pending = [invalid]

        return {
            "messages": [
                AIMessage(content=result.get("text", "Thông tin đơn hàng chưa hợp lệ."))
            ],
            "customer_info": result.get("order", customer),
            "pending_missing_fields": pending,
        }

    return {
        "messages": [
            AIMessage(content=f"Đã ghi nhận đơn hàng {result.get('order_id')} cho anh/chị ạ 🌷")
        ],
        "customer_info": {},
        "pending_missing_fields": [],
        "last_tool": "process_order",
    }


def smalltalk_node(state: dict):
    user_text = get_last_user_text(state)
    return {
        "messages": [make_ai_message("Dạ em chào anh/chị 🌷 Em có thể giúp mình tìm hoa, xem chi tiết mẫu hoa hoặc đặt hàng ạ.")],
        "last_tool": "smalltalk",
    }


def fallback_node(state: dict):
    user_text = get_last_user_text(state)
    return {
        "messages": [make_ai_message(build_fallback_response(user_text))],
        "last_tool": "fallback",
    }