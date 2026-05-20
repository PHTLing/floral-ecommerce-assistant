import json, re
from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage

from app.agent.message_utils import get_message_content
from app.agent.prompts import (
    SEARCH_RESPONSE_PROMPT,
    DETAIL_RESPONSE_PROMPT,
    ORDER_CONFIRMATION_PROMPT,
)

llm_response = ChatOllama(model="qwen3:8b", temperature=0)

def extract_json_from_text(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}

    try:
        data = json.loads(match.group())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_search_response_with_selection(llm, user_text: str, search_results: list[dict]):
    """
    Cho LLM chọn ra các mẫu phù hợp nhất từ search_results.
    Trả về:
    - AIMessage để hiển thị chat
    - recommended_results để frontend hiển thị card ảnh
    """

    if not search_results:
        return (
            AIMessage(content="Mình chưa tìm thấy mẫu hoa phù hợp. Bạn có thể đổi khoảng giá, màu sắc hoặc loại hoa nhé."),
            []
        )

    product_lines = []
    for index, item in enumerate(search_results, start=1):
        product_lines.append(
            f"""
STT: {index}
ID: {item.get("id")}
Tên: {item.get("name")}
Giá: {item.get("price_display") or item.get("price")}
Mô tả: {item.get("description", "")}
Loại hoa: {item.get("primary_flower_type", "")}
"""
        )

    products_text = "\n".join(product_lines)

    prompt = f"""
Bạn là tư vấn viên bán hoa.

Khách hỏi:
"{user_text}"

Danh sách sản phẩm database trả về:
{products_text}

Nhiệm vụ:
- Chọn tối đa 3 mẫu phù hợp nhất với nhu cầu của khách.
- Nếu chỉ có 1-2 mẫu thật sự phù hợp thì chỉ chọn 1-2 mẫu.
- Không chọn mẫu quá lệch nhu cầu chỉ để đủ số lượng.
- Viết câu trả lời tự nhiên, thân thiện bằng tiếng Việt.
- BẮT BUỘC trả về JSON hợp lệ, không markdown, không giải thích ngoài JSON.

Format:
{{
  "reply": "Nội dung trả lời cho khách...",
  "selected_ids": ["id_1", "id_2"]
}}
"""

    try:
        response = llm.invoke([{"role": "user", "content": prompt}])
        parsed = extract_json_from_text(response.content)
    except Exception:
        parsed = {}

    reply = parsed.get("reply")
    selected_ids = parsed.get("selected_ids") or []

    # Normalize ID về string để so sánh chắc chắn
    selected_ids = [str(x) for x in selected_ids]

    recommended_results = [
        item for item in search_results
        if str(item.get("id")) in selected_ids
    ]

    # Fallback nếu LLM trả JSON lỗi hoặc selected_ids không khớp
    if not reply:
        top_items = search_results[:3]
        names = ", ".join(item.get("name", "mẫu hoa") for item in top_items)
        reply = f"Mình tìm thấy một số mẫu phù hợp cho bạn như: {names}. Bạn có thể xem chi tiết từng mẫu bên dưới nhé."

    if not recommended_results:
        recommended_results = search_results[:3]

    return AIMessage(content=reply), recommended_results

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

    if not labels:
        return "Mình đã có đủ thông tin để lên đơn cho anh/chị rồi ạ 🌷"

    if len(missing_fields) >= 5:
        return (
            "Mình đã ghi nhận mẫu hoa anh/chị muốn đặt rồi ạ 🌷\n\n"
            "Để hoàn tất đơn hàng, anh/chị cho mình xin thêm các thông tin sau nhé: "
            "**tên người nhận**, **số điện thoại**, **địa chỉ giao hàng**, "
            "**số lượng**, **ngày nhận** và **giờ nhận**.\n\n"
            "Anh/chị có thể gửi tất cả trong một tin nhắn cũng được ạ."
        )

    if len(labels) == 1:
        return (
            f"Mình gần đủ thông tin để lên đơn rồi ạ. "
            f"Anh/chị cho mình xin thêm **{labels[0]}** nhé 🌷"
        )

    return (
        "Mình gần đủ thông tin để hoàn tất đơn hàng rồi ạ 🌷\n"
        "Anh/chị cho mình xin thêm: "
        + ", ".join(f"**{label}**" for label in labels)
        + "."
    )

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
        # Hiển thị ảnh của các mẫu gợi ý khi search
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

    if state.get("last_tool") == "detail_flower":
        # Hiển thị ảnh của mẫu hoa đang hỏi khi xem chi tiết
        selected = state.get("selected_flower")
        if selected:
            return [
                {
                    "id": selected.get("id"),
                    "name": selected.get("name"),
                    "price": selected.get("price_display"),
                    "image": selected.get("image"),
                    "url": selected.get("url"),
                    "description": selected.get("description", ""),
                }
            ]

    # Các phản hồi còn lại không hiển thị ảnh
    return []