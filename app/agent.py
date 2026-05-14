from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.globals import set_debug
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from typing import TypedDict, List
from app.tools import search_flowers, get_flower_details, process_order # Import từ file tools.py
from pydantic import BaseModel, Field
from typing import Optional

import re, uuid, json
# Bật chế độ xem chi tiết
set_debug(False)

# 1. Định nghĩa State
class AgentState(TypedDict):
    messages: List[dict]

    current_intent: str        # Nhiệm vụ đang làm

    selected_flower: dict     # Lưu thông tin hoa khách đang quan tâm (nếu có)

    search_context: dict    # Lưu ngữ cảnh tìm kiếm (nếu có), ví dụ: loại hoa, dịp lễ, ngân sách...

    customer_info: dict     # Lưu thông tin khách hàng đã thu thập được (Tên, SĐT, Địa chỉ, Tên hoa, Số lượng, Ngày nhận)

    pending_missing_fields: list  # Lưu các trường thông tin còn thiếu để hỏi khách (Tên, SĐT, Địa chỉ, Tên hoa, Số lượng, Ngày nhận)

    last_tool: str       # Lưu tên công cụ cuối cùng được gọi (nếu có) để Model biết kết quả đó đến từ đâu
    tool_retry_count: int # Đếm số lần đã retry công cụ này (nếu có) để tránh lặp vô hạn khi công cụ lỗi hoặc trả về kết quả không như ý. Nếu quá 3 lần thì bỏ qua và hỏi khách thông tin khác.

INTENTS = [
    "search_flower",
    "flower_detail",
    "checkout",
    "small_talk"
]

# 2. Khởi tạo Model và công cụ
llm = ChatOllama(model="qwen3:8b", temperature=0)
tools = [search_flowers, get_flower_details, process_order]
llm_with_tools = llm.bind_tools(tools)

# 3. Node xử lý chính 

# Helper function: Convert non-JSON-serializable objects to serializable ones
def make_json_serializable(obj):
    """Chuyển đổi các object không JSON-serializable (set, datetime, etc.) thành serializable."""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    else:
        return obj

def intent_classifier(state: AgentState):
    # Tôi muốn print agent state để debug
    print("\n" + "="*30)
    print("🧠 [Agent] Classifying intent ...")
    print("Agent State:", state)

    # 1. Trích xuất và định dạng lịch sử hội thoại thành chuỗi văn bản
    history_text = ""
    for msg in state['messages']:
        # Xử lý trường hợp msg là dict 
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
        # Xử lý trường hợp msg là Object của LangChain (HumanMessage, AIMessage, ToolMessage)
        else:
            role = msg.type  
            content = msg.content
            
        # Rút gọn bớt kết quả của ToolMessage nếu nó quá dài để tránh tràn context LLM
        if role == "tool" and len(str(content)) > 500:
            content = str(content)[:500] + "\n... [KẾT QUẢ ĐÃ ĐƯỢC RÚT GỌN]"
            
        history_text += f"[{role.upper()}]: {content}\n"
    # Thêm một System Message để định hướng phong cách
    prompt = f"""
    Bạn là intent classifier cho shop hoa.

    Chỉ trả về đúng 1 trong các nhãn sau:
    - search_flower
    - flower_detail
    - checkout
    - small_talk
    Dựa vào lịch sử hội thoại sau, phân loại ý định của khách hàng:
    {history_text}
    Chỉ trả về label.
    """
    result = llm.invoke(prompt).content.strip().lower()
    
    if result not in INTENTS:
        result = "fallback"

    print("Intent:", result)

    return {
        "current_intent": result
    }

def route_by_intent(state: AgentState):
    return state["current_intent"]

from app.core_ai import get_query_intent
def search_node(state: AgentState):
    """
    🌸 Search Node - Agentic Workflow
    1. Trích xuất intent từ user query
    2. Gọi search_flowers trực tiếp
    3. Tạo ToolMessage với kết quả
    4. Extract selected_flower từ kết quả
    5. Sinh câu trả lời thân thiện bằng LLM
    6. Return messages kèm selected_flower và search_context
    """
    print("🌸 search node (Agentic Workflow)")

    # Helper merge
    def merge_search_context(old_context: dict, new_context: dict) -> dict:
        merged = dict(old_context or {})
        for key, value in (new_context or {}).items():
            if value not in [None, "", []]:
                merged[key] = value
        return merged
        
    last_msg = state["messages"][-1]
    user_text = last_msg.get("content") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")

    # 1. Trích xuất intent từ user query (Regex + LLM hybrid)
    intent = get_query_intent(user_text) or {}
    for k in ("flower", "min_price", "max_price"):
        intent.setdefault(k, None)

    # 2. Nếu core regex không trả price thì dùng LLM để cố gắng trích thêm (color/style)
    if intent.get("min_price") is None and intent.get("max_price") is None:
        prompt = f"""
        Bạn là một extractor. Từ câu sau, trả về JSON duy nhất với các khóa:
        {{ "flower": "...", "min_price": null_or_number, "max_price": null_or_number, "color":"...", "style":"..." }}
        Nếu không có giá thì để null. Câu: \"{user_text}\"
        """
        llm_resp = llm.invoke([{"role": "user", "content": prompt}])
        try:
            match = re.search(r'\{.*\}', llm_resp.content, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                for k in ("min_price", "max_price", "flower", "color", "style"):
                    if parsed.get(k) not in [None, "", []]:
                        intent[k] = parsed[k]
        except Exception:
            pass

    # 3. Chuẩn bị args để gọi tool trực tiếp
    query_for_tool = intent.get("flower") or "hoa"
    try:
        min_p = int(intent.get("min_price")) if intent.get("min_price") else None
    except Exception:
        min_p = None
    try:
        max_p = int(intent.get("max_price")) if intent.get("max_price") else None
    except Exception:
        max_p = None

    tool_args = {
        "query": query_for_tool,
        "min_price": min_p,
        "max_price": max_p,
        "color": intent.get("color"),
        "style": intent.get("style")
    }

    # 4. Gộp context
    old_context = state.get("search_context", {}) or {}
    merged_context = merge_search_context(old_context, intent)

    # ============ GỌI SEARCH_FLOWERS ============
    print(f"🔨 Gọi search_flowers trực tiếp với args: {tool_args}")
    try:
        tool_result = search_flowers.invoke(tool_args)
    except Exception as e:
        print(f"❌ Lỗi search_flowers: {e}")
        tool_result = {"success": False, "text": f"Lỗi tìm kiếm: {str(e)}", "items": []}

    # 5. Tạo ToolMessage thủ công để lưu kết quả vào lịch sử
    tool_call_id = str(uuid.uuid4())
    tool_msg = ToolMessage(
        content=json.dumps(make_json_serializable(tool_result), ensure_ascii=False),
        name="search_flowers",
        tool_call_id=tool_call_id
    )
    print(f"✅ Tool result: {tool_result.get('success')} - {len(tool_result.get('items', []))} items")

    # 6. Extract selected_flower từ tool result
    selected_flower = {}
    items = tool_result.get("items", [])
    if items and len(items) > 0:
        first_item = items[0]
        selected_flower = {
            "name": first_item.get("name", ""),
            "id": first_item.get("id") or first_item.get("ma_so")
        }
        print(f"📌 Selected first flower: {selected_flower}")

    # 7. Sinh câu trả lời thân thiện bằng LLM (Gộp logic từ summarize)
    # Đọc ToolMessage và user query để tạo câu trả lời tự nhiên
    response_prompt = f"""
    Khách hàng vừa tìm kiếm: "{user_text}"
    
    Kết quả tìm kiếm:
    {tool_result.get('text', 'Không tìm thấy kết quả')}
    
    Hãy trả lời khách thân thiện, mô tả các mẫu hoa tìm được (nếu có) và mời khách xem chi tiết hoặc đặt hàng.
    Nếu không tìm thấy, hãy xin lỗi và gợi ý khác.
    """
    ai_response = llm.invoke([{"role": "user", "content": response_prompt}])
    
    # 8. Return state với messages, selected_flower, và search_context
    return {
        "messages": [tool_msg, ai_response],
        "selected_flower": selected_flower if selected_flower else None,
        "search_context": merged_context,
        "last_tool": "search_flowers"
    }


def detail_node(state: AgentState):
    """
    🔎 Detail Node - Agentic Workflow
    1. Extract flower_name và flower_id từ lịch sử
    2. Gọi get_flower_details trực tiếp
    3. Tạo ToolMessage với kết quả
    4. Sinh câu trả lời thân thiện bằng LLM
    5. Return messages
    """
    print("🔎 detail node (Agentic Workflow)")
    
    def extract_flower_info():
        """Tìm `flower_name` và `flower_id` từ user query rồi scan toàn bộ lịch sử (hybrid).
        ⭐ PRIORITY: Extract từ user message hiện tại TRƯỚC, rồi mới fallback vào selected_flower"""
        
        # 1) Lấy user message CUỐI CÙNG (message hiện tại)
        user_msg = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, dict) and msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break
            elif not isinstance(msg, dict) and getattr(msg, "type", "") in ("human",):
                user_msg = getattr(msg, "content", "")
                break

        flower_name = None
        flower_id = None

        # 2) ⭐ TRY EXTRACT TỪ USER MESSAGE HIỆN TẠI TRƯỚC
        if user_msg:
            # Cố lấy tên trực tiếp từ câu hỏi: "Mẫu X", "mẫu X", "Tên hoa X", "lấy X"
            m_name = re.search(r'(?:[Mm]ẫu|[Tt]ên hoa|lấy)\s+[:\-]?\s*([^\?\.,\n\[]+)', user_msg)
            if m_name:
                flower_name = m_name.group(1).strip()
                print(f"  ✅ Extracted từ user message: {flower_name}")

            # Fallback: ask LLM only with the user_msg để extract name/id JSON
            if not flower_name:
                try:
                    prompt = (
                        'Trích xuất JSON {"flower_name":"...", "flower_id": number_or_null} từ: '
                        f'"{user_msg}"'
                    )
                    r = llm.invoke([{"role": "user", "content": prompt}])
                    mm = re.search(r'\{.*\}', r.content, re.DOTALL)
                    if mm:
                        parsed = json.loads(mm.group())
                        flower_name = parsed.get("flower_name") or flower_name
                        fid = parsed.get("flower_id")
                        if fid:
                            try:
                                flower_id = int(fid)
                            except Exception:
                                flower_id = None
                        if flower_name:
                            print(f"  ✅ Extracted by LLM: {flower_name}")
                except Exception as e:
                    print(f"  ⚠️ LLM extraction failed: {e}")
        
        # 3) ⭐ FALLBACK: Chỉ nếu không extract được từ user message, mới dùng selected_flower
        if not flower_name:
            sf = state.get("selected_flower") or {}
            if sf and sf.get("name"):
                flower_name = sf.get("name")
                flower_id = sf.get("id")
                if flower_id:
                    try:
                        flower_id = int(flower_id) if flower_id is not None else None
                    except Exception:
                        flower_id = None
                print(f"  📌 Fallback to selected_flower: {flower_name}")

        # Normalize lower for matching
        name_lower = (flower_name or "").lower()
        user_tokens = set(re.findall(r'\w+', (user_msg or "").lower()))

        # 4) Nếu đã có flower_name từ user message nhưng chưa có ID, scan lịch sử để tìm ID
        if flower_name and not flower_id:
            for msg in reversed(state["messages"]):
                if isinstance(msg, dict):
                    content = str(msg.get("content", "") or "")
                    role = msg.get("role", "")
                else:
                    content = str(getattr(msg, "content", "") or "")
                    role = getattr(msg, "type", "")

                cont_lower = content.lower()

                # a) tìm pattern id: 'mã nội bộ: 12345' hoặc 'mã: 12345'
                m_id = re.search(r'mã\s*nội\s*bộ[:\s]*([0-9]{3,7})', cont_lower)
                if not m_id:
                    m_id = re.search(r'\b(?:mã|id)[:\s]*([0-9]{3,7})\b', cont_lower)

                if m_id:
                    try:
                        cand_id = int(m_id.group(1))
                    except Exception:
                        cand_id = None

                    # Nếu message chứa tên đã trích → xác định ID
                    if cand_id and name_lower and name_lower in cont_lower:
                        flower_id = cand_id
                        print(f"  ✅ Found ID from history: {cand_id}")
                        return flower_name, flower_id

                    # Nếu user tokens trùng → chấp nhận
                    if cand_id and user_tokens and any(tok in cont_lower for tok in user_tokens):
                        flower_id = cand_id
                        return flower_name, flower_id

                # b) Inspect items từ tool result
                if isinstance(msg, dict) and msg.get("role") == "tool":
                    items = msg.get("results") or msg.get("items") or []
                    if isinstance(items, list) and items:
                        for it in items:
                            iname = str(it.get("name", "") or "")
                            iid = it.get("id") or it.get("ma_so") or it.get("maSo")
                            if iname:
                                if name_lower and name_lower in iname.lower():
                                    try:
                                        flower_id = int(iid) if iid else None
                                        print(f"  ✅ Found ID from search result: {flower_id}")
                                        return iname, flower_id
                                    except Exception:
                                        return iname, None

        # 5) Return kết quả
        return flower_name, flower_id
    
    flower_name, flower_id = extract_flower_info()
    print(f"📌 Extracted: flower_name='{flower_name}', flower_id={flower_id}")

    # ============ AGENTIC WORKFLOW: GỌI TOOL TRỰC TIẾP ============
    print(f"🔨 Gọi get_flower_details trực tiếp với name={flower_name}, id={flower_id}")
    try:
        tool_result = get_flower_details.invoke({"flower_name": flower_name, "flower_id": flower_id})
    except Exception as e:
        print(f"❌ Lỗi get_flower_details: {e}")
        tool_result = {"success": False, "detail": f"Lỗi lấy chi tiết: {str(e)}"}

    # Tạo ToolMessage thủ công
    tool_call_id = str(uuid.uuid4())
    tool_msg = ToolMessage(
        content=json.dumps(make_json_serializable(tool_result), ensure_ascii=False),
        name="get_flower_details",
        tool_call_id=tool_call_id
    )
    print(f"✅ Detail result: {tool_result.get('success')}")

    # Sinh câu trả lời thân thiện bằng LLM
    response_prompt = f"""
    Khách hàng muốn xem chi tiết mẫu hoa: {flower_name} (ID: {flower_id})
    
    Thông tin chi tiết:
    {tool_result.get('detail', 'Không tìm thấy thông tin')}
    
    Hãy trình bày thông tin chi tiết một cách thân thiện, hấp dẫn (nếu có).
    Kết thúc bằng câu mời khách đặt hàng hoặc xem thêm.
    """
    ai_response = llm.invoke([{"role": "user", "content": response_prompt}])

    return {
        "messages": [tool_msg, ai_response],
        "selected_flower": {"name": flower_name, "id": flower_id} if flower_name else None,
        "last_tool": "get_flower_details"
    }

def checkout_node(state: AgentState):
    """
    🛒 Checkout Node - Agentic Workflow (Batch Information Collection)
    1. Trích xuất thông tin khách từ messages
    2. Kiểm tra thông tin còn thiếu
    3. Hỏi TẤT CẢ thông tin còn thiếu trong 1 lần (batch)
    4. Nếu vẫn còn thiếu sau 1 lần, hỏi từng trường còn lại
    5. Khi đủ, gọi process_order trực tiếp
    6. Tạo ToolMessage với kết quả
    7. Sinh câu trả lời xác nhận đơn hàng
    8. Return messages
    """
    print("🛒 checkout node (Batch Information Collection)")
    
    # Required fields and friendly labels
    required = ["ten_khach", "sdt", "dia_chi", "loai_hang", "so_luong", "ngay_nhan", "gio_nhan"]
    field_labels = {
        "ten_khach": "Tên khách hàng",
        "sdt": "Số điện thoại",
        "dia_chi": "Địa chỉ giao hàng",
        "loai_hang": "Tên mẫu hoa",
        "so_luong": "Số lượng",
        "ngay_nhan": "Ngày nhận",
        "gio_nhan": "Giờ nhận"
    }
    
    customer = dict(state.get("customer_info") or {})

    # Prefill loai_hang from selected_flower if available
    sel = state.get("selected_flower") or {}
    if sel and sel.get("name") and not customer.get("loai_hang"):
        sid = sel.get("id")
        customer["loai_hang"] = f"{sel.get('name')} - {sid}" if sid else sel.get("name")

    # Try to extract any fields from the last user message using LLM
    last_user = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user = msg.get("content", "")
            break

    if last_user:
        extract_prompt = (
            "Từ đoạn sau, trích xuất JSON chỉ các trường có thể: "
            "{\"ten_khach\":..., \"sdt\":..., \"dia_chi\":..., \"loai_hang\":..., \"so_luong\":..., \"ngay_nhan\":..., \"gio_nhan\":...}\. "
            f"Nếu không có trường nào thì không include. Đoạn:\n" + last_user
        )
        try:
            resp = llm.invoke([{"role": "user", "content": extract_prompt}])
            match = re.search(r'\{.*\}', resp.content, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                for k, v in parsed.items():
                    if v not in [None, "", []]:
                        customer[k] = v
        except Exception:
            pass

    # Determine missing fields
    missing = [f for f in required if not customer.get(f)]

    # Validate phone if present
    if customer.get("sdt"):
        sdt_clean = re.sub(r'\D', '', str(customer.get("sdt")))
        if len(sdt_clean) < 9 or len(sdt_clean) > 12:
            # invalidate and ask again
            customer.pop("sdt", None)
            missing = [f for f in required if not customer.get(f)]
            ask = "SĐT không hợp lệ, vui lòng nhập lại số điện thoại (ví dụ: 0901234567)."
            return {"messages": [AIMessage(content=ask)], "customer_info": customer, "pending_missing_fields": missing}
        else:
            customer["sdt"] = sdt_clean

    # If still missing, ask for ALL remaining fields at once (BATCH)
    if missing:
        # ✨ BATCH REQUEST: Hỏi tất cả trường còn thiếu trong 1 lần
        missing_labels = [field_labels.get(f, f) for f in missing]
        
        if len(missing) == len(required):
            # Lần đầu tiên: Hỏi toàn bộ thông tin với format friendly
            question = f"""
Để hoàn tất đơn hàng, vui lòng cung cấp các thông tin sau (có thể nhập cùng lúc):

📋 **Thông tin cần thiết:**
- Tên của anh/chị
- Số điện thoại liên hệ (ví dụ: 0901234567)
- Địa chỉ giao hàng
- Tên mẫu hoa muốn đặt
- Số lượng
- Ngày nhận (ví dụ: 25/12/2026)
- Giờ nhận (ví dụ: 15:00 hoặc 3 giờ chiều)

💡 **Ví dụ trả lời:** "Tôi tên Linh, SĐT 0901234567, địa chỉ 123 Nguyễn Huệ Q1, muốn 2 cái hoa hồng đỏ, nhận ngày 25/12 lúc 15:00"
"""
        else:
            # Hỏi các trường còn lại nếu có
            remaining = ", ".join(missing_labels)
            question = f"Vui lòng cung cấp các thông tin còn thiếu: {remaining}"
        
        # Save state
        return {
            "messages": [AIMessage(content=question)], 
            "customer_info": customer, 
            "pending_missing_fields": missing
        }

    # ============ AGENTIC WORKFLOW: GỌI TOOL TRỰC TIẾP KHI ĐỦ THÔNG TIN ============
    print(f"🔨 Gọi process_order trực tiếp với thông tin khách:")
    try:
        order_args = {
            "ten_khach": customer.get("ten_khach"),
            "sdt": customer.get("sdt"),
            "dia_chi": customer.get("dia_chi"),
            "loai_hang": customer.get("loai_hang"),
            "so_luong": customer.get("so_luong"),
            "ngay_nhan": customer.get("ngay_nhan"),
            "gio_nhan": customer.get("gio_nhan")
        }
        print(f"  Tên: {order_args['ten_khach']}, SĐT: {order_args['sdt']}, Loại: {order_args['loai_hang']}")
        tool_result = process_order.invoke(order_args)
    except Exception as e:
        print(f"❌ Lỗi process_order: {e}")
        tool_result = {"success": False, "text": f"Lỗi ghi đơn: {str(e)}"}

    # Tạo ToolMessage thủ công
    tool_call_id = str(uuid.uuid4())
    tool_msg = ToolMessage(
        content=json.dumps(make_json_serializable(tool_result), ensure_ascii=False),
        name="process_order",
        tool_call_id=tool_call_id
    )
    print(f"✅ Order result: {tool_result.get('success')}")

    # Sinh câu trả lời xác nhận đơn hàng thân thiện bằng LLM
    response_prompt = f"""
    Đơn hàng vừa được ghi nhận với thông tin:
    - Tên khách: {customer.get('ten_khach')}
    - SĐT: {customer.get('sdt')}
    - Địa chỉ: {customer.get('dia_chi')}
    - Loại hoa: {customer.get('loai_hang')}
    - Số lượng: {customer.get('so_luong')}
    - Ngày nhận: {customer.get('ngay_nhan')}
    - Giờ nhận: {customer.get('gio_nhan')}
    
    Kết quả xử lý: {tool_result.get('text', 'Thành công')}
    
    Hãy xác nhận đơn hàng lại với khách thân thiện, đề nghị các mẫu khác hoặc tạo cảm giác hài lòng.
    """
    ai_response = llm.invoke([{"role": "user", "content": response_prompt}])

    # Clear pending fields after success
    return {"messages": [tool_msg, ai_response], "customer_info": {}, "pending_missing_fields": []}
  
def smalltalk_node(state: AgentState):
    """💬 Smalltalk Node - Trả lời câu hỏi thông thường"""
    print("💬 smalltalk node")
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def fallback_node(state):
    """❌ Fallback Node - Khi không hiểu intent"""
    user_text = state["messages"][-1]["content"].lower()

    if "giá" in user_text:
        msg = "Anh/chị muốn tìm hoa trong khoảng giá bao nhiêu ạ?"
    elif "đặt" in user_text:
        msg = "Anh/chị muốn đặt mẫu hoa nào ạ?"
    else:
        msg = """
            Em chưa hiểu rõ ý anh/chị 🌷
            Anh/chị đang muốn:
            - tìm hoa
            - xem chi tiết
            - hay đặt hàng ạ?
            """
    return {"messages": [AIMessage(content=msg)]}


def route_should_continue(state: AgentState):
    """Router để lấy decision từ state"""
    return state.get("should_continue_result", "end")

# 4. Lắp ráp Graph (Agentic Workflow)
"""
🏗️ KIẾN TRÚC AGENTIC WORKFLOW:
- Không sử dụng ToolNode (Pure Autonomous Agent)
- Các node gọi tool trực tiếp bằng code Python
- Tạo ToolMessage thủ công để lưu kết quả vào lịch sử
- Sinh câu trả lời ngay tại node bằng LLM thuần
- Nối trực tiếp tới should_continue để kiểm tra kết quả
"""
workflow = StateGraph(AgentState)

# Thêm các node
workflow.add_node("intent_classifier", intent_classifier)
workflow.add_node("search_flower", search_node)
workflow.add_node("flower_detail", detail_node)
workflow.add_node("checkout", checkout_node)
workflow.add_node("smalltalk", smalltalk_node)
workflow.add_node("fallback", fallback_node)

# Cạnh từ START
workflow.add_edge(START, "intent_classifier")

# Định tuyến từ intent_classifier
workflow.add_conditional_edges(
    "intent_classifier",
    route_by_intent,
    {
        "search_flower": "search_flower",
        "flower_detail": "flower_detail",
        "checkout": "checkout",
        "smalltalk": "smalltalk",
        "fallback": "fallback"
    }
)

# ⭐ AGENTIC WORKFLOW: Nối trực tiếp từ các node action tới should_continue
# (Không cần conditional edges vì các node đã xử lý tool trực tiếp và return luôn AIMessage)
workflow.add_edge("search_flower", "should_continue")
workflow.add_edge("flower_detail", "should_continue")
workflow.add_edge("checkout", "should_continue")
workflow.add_edge("smalltalk", "should_continue")
workflow.add_edge("fallback", "should_continue")

app = workflow.compile()

if __name__ == "__main__":
    print("🌟 HỆ THỐNG AGENT (LANGGRAPH) ĐÃ SẴN SÀNG 🌟")
    
    # Khởi tạo trạng thái ban đầu
    current_state = {"messages": []}
    while True:
        user_input = input("\n" + "="*50 + "\n👤 Khách hàng: ")

        if user_input.lower() in ['exit', 'quit']: 
            break

        current_state["messages"].append({"role": "user", "content": user_input})
        final_output = None
        for output in app.stream(current_state):
            for key, value in output.items():
                print(f"\n📍 Đang xử lý tại: [{key}]")
                final_output = value

                if "messages" in value:
                    last_m = value["messages"][-1]
                    # Nếu là tin nhắn gọi Tool (Action)
                    if hasattr(last_m, 'tool_calls') and last_m.tool_calls:
                        print(f"🛠️ Agent quyết định gọi công cụ: {last_m.tool_calls[0]['name']}")

        if final_output:
            # LangGraph sẽ tự merge messages, nhưng ta cần giữ lại toàn bộ list
            # Cách an toàn nhất cho người mới là lấy kết quả cuối cùng từ app.invoke hoặc cập nhật thủ công
            current_state = app.invoke(current_state)
        bot_reply = current_state["messages"][-1]
        print(f"\n🤖 FloraConsult: {bot_reply.content if hasattr(bot_reply, 'content') else bot_reply['content']}")  