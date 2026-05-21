from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage

from app.agent.message_utils import get_last_user_text, make_tool_message, make_ai_message
from app.agent.response_builder import (
    build_search_response,
    build_detail_response,
    build_order_confirmation,
    build_missing_fields_question,
    build_fallback_response,
    build_search_response_with_selection,
    build_order_review_message,
)

from app.extractors.search_intent_extractor import get_query_intent
from app.extractors.flower_reference_resolver import resolve_flower_reference
from app.extractors.order_info_extractor import (
    extract_order_info,
    is_add_more_request,
    is_reuse_previous_delivery_request,
)
from app.extractors.confirmation_extractor import (
    is_order_confirmation_yes,
    is_order_confirmation_no_or_wait,
)

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
from app.utils.order_items import (
    ensure_order_items,
    append_item_to_order,
    normalize_order_to_items,
)

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
    print("[Checkout] user_text:", user_text)
    print("[Checkout] is_add_more_request:", is_add_more_request(user_text))
    print("[Checkout] is_yes:", is_order_confirmation_yes(user_text))
    print("[Checkout] is_no_or_wait:", is_order_confirmation_no_or_wait(user_text))

    # ======================================================
    # 1. Đang chờ khách xác nhận / sửa đơn
    # ======================================================
    if state.get("pending_order_confirmation"):
        order_draft = normalize_order_to_items(state.get("order_draft") or {})

        # Khách xác nhận đúng
        if is_order_confirmation_yes(user_text):
            result = create_order(order_draft)

            if not result.get("success"):
                pending = result.get("missing_fields") or []
                invalid = result.get("invalid_field")

                if invalid:
                    pending = [invalid]

                failed_order = normalize_order_to_items(
                    result.get("order", order_draft)
                )

                return {
                    "messages": [
                        AIMessage(
                            content=result.get(
                                "text",
                                "Thông tin đơn hàng chưa hợp lệ, anh/chị kiểm tra lại giúp mình nhé.",
                            )
                        )
                    ],
                    "customer_info": failed_order,
                    "order_draft": failed_order,
                    "pending_missing_fields": pending,
                    "pending_order_confirmation": False,
                    "last_tool": "checkout",
                }

            order = normalize_order_to_items(result.get("order", {}))
            order_id = result.get("order_id")

            last_delivery_info = {
                "ten_khach": order.get("ten_khach"),
                "sdt": order.get("sdt"),
                "dia_chi": order.get("dia_chi"),
                "ngay_nhan": order.get("ngay_nhan"),
                "gio_nhan": order.get("gio_nhan"),
            }

            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"Em đã ghi nhận đơn hàng **{order_id}** cho anh/chị rồi ạ 🌷\n"
                            "Cảm ơn anh/chị đã đặt hoa tại FloraConsult!"
                        )
                    )
                ],
                "customer_info": {},
                "order_draft": {},
                "last_order": order,
                "last_delivery_info": last_delivery_info,
                "pending_missing_fields": [],
                "pending_order_confirmation": False,
                "last_tool": "process_order",
            }

        # 1.2. Khách chưa muốn xác nhận
        if is_order_confirmation_no_or_wait(user_text):
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "Dạ được ạ, mình sẽ chưa tạo đơn vội 🌷\n"
                            "Khi nào anh/chị muốn chỉnh thông tin thì cứ nhắn phần cần sửa, "
                            "hoặc nhắn **xác nhận** nếu thông tin đã đúng nhé."
                        )
                    )
                ],
                "customer_info": order_draft,
                "order_draft": order_draft,
                "pending_missing_fields": [],
                "pending_order_confirmation": True,
                "last_tool": "checkout",
            }
        
    # 1.3. Đang review đơn mà khách muốn lấy thêm item
        if is_add_more_request(user_text):
            extracted = extract_order_info(user_text, state)
            new_items = extracted.get("items") or []

            print("[Checkout] add_more while pending - user_text:", user_text)
            print("[Checkout] add_more while pending - order_draft before:", order_draft)
            print("[Checkout] add_more while pending - extracted:", extracted)
            print("[Checkout] add_more while pending - new_items:", new_items)
            if not new_items:
                return {
                    "messages": [
                        AIMessage(
                            content="Anh/chị muốn lấy thêm mẫu hoa nào và số lượng bao nhiêu ạ?"
                        )
                    ],
                    "customer_info": order_draft,
                    "order_draft": order_draft,
                    "pending_missing_fields": ["items"],
                    "pending_order_confirmation": True,
                    "last_tool": "checkout",
                }

            # Lấy lại toàn bộ đơn đang review, bao gồm items cũ
            updated_order = normalize_order_to_items(order_draft)

            # Lấy items cũ rõ ràng
            old_items = ensure_order_items(updated_order)

            # Append items mới vào items cũ
            updated_order["items"] = old_items + new_items

            delivery_update = {
                    key: value
                    for key, value in extracted.items()
                    if key not in ["items", "loai_hang", "so_luong"]
                }

            if delivery_update:
                updated_order = merge_order_info(updated_order, delivery_update)
                updated_order = normalize_order_to_items(updated_order)

            print("[Checkout] add_more while pending - updated_order:", updated_order)

            missing = get_missing_fields(updated_order)
            if missing:
                question = build_missing_fields_question(missing, FIELD_LABELS)

                return {
                    "messages": [AIMessage(content=question)],
                    "customer_info": updated_order,
                    "order_draft": updated_order,
                    "pending_missing_fields": missing,
                    "pending_order_confirmation": False,
                    "last_tool": "checkout",
                }

            review_message = build_order_review_message(updated_order)

            return {
                "messages": [AIMessage(content=review_message)],
                "customer_info": updated_order,
                "order_draft": updated_order,
                "pending_missing_fields": [],
                "pending_order_confirmation": True,
                "last_tool": "checkout",
            }
        # --------------------------------------------------
        # 1.4. Khách sửa thông tin đơn
        # Ví dụ:
        # - sửa địa chỉ thành ...
        # - đổi giờ nhận thành 18h
        # - đổi ngày nhận thành mai
        # --------------------------------------------------
        # Khách sửa thông tin
        correction_info = extract_order_info(user_text, state)
        print("[Checkout] correction_info:", correction_info)

        updated_order = merge_order_info(order_draft, correction_info)
        updated_order = normalize_order_to_items(updated_order)

        missing = get_missing_fields(updated_order)

        if missing:
            question = build_missing_fields_question(missing, FIELD_LABELS)

            return {
                "messages": [AIMessage(content=question)],
                "customer_info": updated_order,
                "order_draft": updated_order,
                "pending_missing_fields": missing,
                "pending_order_confirmation": False,
                "last_tool": "checkout",
            }

        review_message = build_order_review_message(updated_order)

        return {
            "messages": [AIMessage(content=review_message)],
            "customer_info": updated_order,
            "order_draft": updated_order,
            "pending_missing_fields": [],
            "pending_order_confirmation": True,
            "last_tool": "checkout",
        }
    # ======================================================
    # 2. KHÁCH LẤY THÊM SAU KHI ĐÃ CÓ ĐƠN TRƯỚC ĐÓ
    # ======================================================
    if is_add_more_request(user_text) and state.get("last_delivery_info"):
        extracted = extract_order_info(user_text, state)
        new_items = extracted.get("items") or []

        print("[Checkout] add more after created order - extracted:", extracted)
        print("[Checkout] add more after created order - new_items:", new_items)

        last_delivery = state.get("last_delivery_info") or {}
        last_order = normalize_order_to_items(state.get("last_order") or {})

        # Tạo draft mới từ thông tin giao hàng cũ + items cũ
        draft = {
            **last_delivery,
            "items": ensure_order_items(last_order),
        }

        if not new_items:
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "Mình sẽ dùng lại thông tin giao hàng như đơn trước ạ 🌷\n"
                            "Anh/chị muốn lấy thêm mẫu hoa nào và số lượng bao nhiêu ạ?"
                        )
                    )
                ],
                "customer_info": draft,
                "order_draft": draft,
                "pending_missing_fields": ["items"],
                "pending_order_confirmation": False,
                "last_tool": "checkout",
            }

        old_items = ensure_order_items(draft)
        draft["items"] = old_items + new_items

        # Nếu câu lấy thêm có cập nhật giao hàng mới thì merge vào
        delivery_update = {
            key: value
            for key, value in extracted.items()
            if key not in ["items", "loai_hang", "so_luong"]
        }

        if delivery_update:
            draft = merge_order_info(draft, delivery_update)
            draft = normalize_order_to_items(draft)

        missing = get_missing_fields(draft)

        if missing:
            question = build_missing_fields_question(missing, FIELD_LABELS)

            return {
                "messages": [AIMessage(content=question)],
                "customer_info": draft,
                "order_draft": draft,
                "pending_missing_fields": missing,
                "pending_order_confirmation": False,
                "last_tool": "checkout",
            }

        review_message = build_order_review_message(draft)

        return {
            "messages": [AIMessage(content=review_message)],
            "customer_info": draft,
            "order_draft": draft,
            "pending_missing_fields": [],
            "pending_order_confirmation": True,
            "last_tool": "checkout",
        }

    # ======================================================
    # 3. CHECKOUT BÌNH THƯỜNG
    # ======================================================
    old_customer = normalize_order_to_items(state.get("customer_info") or {})
    extracted = extract_order_info(user_text, state)

    print("[Checkout] extracted:", extracted)

    customer = merge_order_info(old_customer, extracted)
    customer = normalize_order_to_items(customer)

    print("[Checkout] merged customer:", customer)

    missing = get_missing_fields(customer)

    if missing:
        question = build_missing_fields_question(missing, FIELD_LABELS)

        return {
            "messages": [AIMessage(content=question)],
            "customer_info": customer,
            "order_draft": customer,
            "pending_missing_fields": missing,
            "pending_order_confirmation": False,
            "last_tool": "checkout",
        }

    review_message = build_order_review_message(customer)

    return {
        "messages": [AIMessage(content=review_message)],
        "customer_info": customer,
        "order_draft": customer,
        "pending_missing_fields": [],
        "pending_order_confirmation": True,
        "last_tool": "checkout",
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