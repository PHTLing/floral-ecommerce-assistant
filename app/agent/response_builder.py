import json, re
from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage
from textwrap import dedent
from app.agent.message_utils import get_message_content
from app.agent.prompts import (
    SEARCH_RESPONSE_PROMPT,
    DETAIL_RESPONSE_PROMPT,
    ORDER_CONFIRMATION_PROMPT,
)

from app.utils.order_items import ensure_order_items

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

    if len(labels) == 1:
        return (
            f"Mình gần đủ thông tin để lên đơn rồi ạ. "
            f"Anh/chị cho mình xin thêm **{labels[0]}** nhé 🌷"
        )

    if len(missing_fields) >= 5:
        return (
            "Mình đã ghi nhận mẫu hoa anh/chị muốn đặt rồi ạ 🌷\n\n"
            "Để hoàn tất đơn hàng, anh/chị cho mình xin thêm các thông tin sau nhé: "
            "**tên người nhận**, **số điện thoại**, **địa chỉ giao hàng**, "
            "**số lượng**, **ngày nhận** và **giờ nhận**.\n\n"
            "Anh/chị có thể gửi tất cả trong một tin nhắn cũng được ạ."
        )

    return (
        "Mình gần đủ thông tin để hoàn tất đơn hàng rồi ạ 🌷\n"
        "Anh/chị cho mình xin thêm: "
        + ", ".join(f"**{label}**" for label in labels)
        + "."
    )

def build_order_review_message(order: dict) -> str:
    items = order.get("items") or []

    if items:
        item_lines = "\n".join(
            f"- **{item.get('loai_hang', 'Mẫu hoa')}**: {item.get('so_luong', '1')} bó"
            for item in items
        )
    else:
        item_lines = (
            f"- **{order.get('loai_hang', 'Chưa có')}**: "
            f"{order.get('so_luong', 'Chưa có')} bó"
        )

    return "\n".join([
        "Em đã ghi nhận thông tin đặt hoa như sau, anh/chị kiểm tra thông tin đơn hàng nhé 🌷",
        "",
        "**Sản phẩm**",
        item_lines,
        "",
        "**Thông tin giao hàng**",
        f"- **Tên khách hàng:** {order.get('ten_khach', 'Chưa có')}",
        f"- **Số điện thoại:** {order.get('sdt', 'Chưa có')}",
        f"- **Địa chỉ giao hàng:** {order.get('dia_chi', 'Chưa có')}",
        f"- **Ngày nhận:** {order.get('ngay_nhan', 'Chưa có')}",
        f"- **Giờ nhận:** {order.get('gio_nhan', 'Chưa có')}",
        "",
        'Nếu thông tin đã đúng, anh/chị nhắn **"xác nhận"** hoặc **"đúng rồi"** giúp mình ạ.',
        'Nếu cần sửa, anh/chị cứ nhắn phần cần đổi, ví dụ: **"sửa địa chỉ thành ..."**, **"đổi giờ nhận thành ..."**.',
    ]).strip()

def build_smalltalk_response(user_text: str) -> str:
    text = (user_text or "").lower().strip()

    # Chào hỏi
    if any(k in text for k in ["xin chào", "chào", "hello", "hi", "alo"]):
        return (
            "Dạ em chào anh/chị 🌷\n"
            "Em là chatbot hỗ trợ của FloraConsult. "
            "Em có thể giúp anh/chị tìm mẫu hoa, xem chi tiết sản phẩm và hỗ trợ đặt hoa ạ."
        )

    # Bot là ai
    if any(k in text for k in ["bạn là ai", "em là ai", "bot là ai", "chatbot là gì"]):
        return (
            "Dạ em là chatbot tư vấn của shop hoa FloraConsult 🌷\n"
            "Em có thể hỗ trợ anh/chị tìm hoa theo dịp, màu sắc, ngân sách, "
            "xem thông tin mẫu hoa và ghi nhận thông tin đặt hàng ạ."
        )

    # Shop bán gì
    if any(k in text for k in ["shop bán gì", "có những loại hoa nào", "bên mình có hoa gì"]):
        return (
            "Dạ shop có nhiều mẫu hoa tươi như hoa sinh nhật, hoa chúc mừng, hoa khai trương, "
            "hoa tình yêu, hoa chia buồn và các mẫu bó/giỏ/hộp hoa ạ 🌷\n"
            "Anh/chị có thể nói dịp tặng, màu yêu thích hoặc ngân sách để em gợi ý mẫu phù hợp."
        )

    # Thời gian giao hàng
    if any(k in text for k in ["giao hàng", "giao hoa", "mấy giờ giao", "thời gian giao", "bao lâu giao"]):
        return (
            "Dạ shop có hỗ trợ giao hoa trong ngày tùy khu vực và tình trạng mẫu hoa ạ 🌷\n"
            "Khi đặt hàng, anh/chị cho em xin địa chỉ, ngày nhận và giờ nhận mong muốn, "
            "em sẽ ghi nhận thông tin để shop kiểm tra và xử lý đơn."
        )

    # Phí ship
    if any(k in text for k in ["phí ship", "tiền ship", "phí giao", "ship bao nhiêu"]):
        return (
            "Dạ phí giao hàng có thể thay đổi theo khu vực và thời điểm giao ạ.\n"
            "Anh/chị cho em xin địa chỉ giao hàng, shop sẽ kiểm tra phí giao cụ thể cho mình."
        )

    # Thanh toán
    if any(k in text for k in ["thanh toán", "chuyển khoản", "cod", "trả tiền", "tiền mặt"]):
        return (
            "Dạ shop có thể hỗ trợ các hình thức thanh toán phổ biến như chuyển khoản "
            "hoặc thanh toán theo hướng dẫn của shop ạ.\n"
            "Sau khi anh/chị xác nhận đơn, nhân viên có thể hỗ trợ thêm thông tin thanh toán chi tiết."
        )

    # Cách đặt hàng
    if any(k in text for k in ["đặt hàng như thế nào", "cách đặt", "muốn đặt hoa", "đặt hoa sao"]):
        return (
            "Dạ để đặt hoa, anh/chị chỉ cần cho em các thông tin sau ạ:\n"
            "- Mẫu hoa muốn đặt\n"
            "- Số lượng\n"
            "- Tên người nhận\n"
            "- Số điện thoại\n"
            "- Địa chỉ giao hàng\n"
            "- Ngày và giờ nhận hoa\n\n"
            "Em sẽ hỗ trợ lên đơn hàng ạ 🌷"
        )

    # Cảm ơn
    if any(k in text for k in ["cảm ơn", "thanks", "thank you", "ok cảm ơn"]):
        return (
            "Dạ em cảm ơn anh/chị ạ 🌷\n"
            "Khi nào cần tìm mẫu hoa hoặc đặt hoa, anh/chị cứ nhắn em nhé."
        )

    # Mặc định smalltalk
    return (
        "Dạ em có thể hỗ trợ anh/chị tìm mẫu hoa, xem chi tiết sản phẩm hoặc đặt hoa ạ 🌷\n"
        "Anh/chị muốn tìm hoa cho dịp nào hoặc cần em hỗ trợ gì thêm không ạ?"
    )

def build_fallback_response(user_text: str) -> str:
    text = (user_text or "").lower()

    if any(k in text for k in ["nhân viên", "người thật", "tư vấn viên"]):
        return (
            "Dạ em đã ghi nhận yêu cầu gặp nhân viên hỗ trợ ạ 🌷\n"
            "Hiện tại em chưa thể kết nối trực tiếp trong khung chat này, "
            "anh/chị vui lòng để lại số điện thoại hoặc nội dung cần hỗ trợ, "
            "shop sẽ liên hệ lại sớm nhất có thể."
        )

    if any(k in text for k in ["khiếu nại", "hoàn tiền", "giao sai", "hoa héo", "hoa hư", "chưa nhận được"]):
        return (
            "Dạ em rất tiếc vì trải nghiệm chưa tốt của anh/chị ạ 🌷\n"
            "Vấn đề này cần nhân viên shop kiểm tra trực tiếp. "
            "Anh/chị vui lòng để lại mã đơn hàng hoặc số điện thoại đặt hàng, "
            "shop sẽ hỗ trợ kiểm tra và phản hồi sớm nhất có thể."
        )
    return (
        "Dạ nội dung này có thể cần nhân viên shop hỗ trợ trực tiếp để xử lý chính xác hơn ạ 🌷\n\n"
        "Anh/chị vui lòng để lại yêu cầu cụ thể hoặc số điện thoại liên hệ, "
        "shop sẽ kiểm tra và phản hồi lại mình sớm nhất có thể.\n\n"
        "Trong lúc chờ, em vẫn có thể hỗ trợ anh/chị tìm mẫu hoa, xem chi tiết sản phẩm "
        "hoặc ghi nhận thông tin đặt hàng ạ."
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