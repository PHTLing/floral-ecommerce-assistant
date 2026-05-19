from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

from langchain_core.globals import set_debug

from langchain_core.messages import BaseMessage
from typing import Annotated
from langgraph.graph.message import add_messages

from typing import TypedDict
from app.org.tools import search_flowers, get_flower_details, process_order
from pydantic import BaseModel, Field
from typing import Optional

import re, uuid, json
# Bật chế độ xem chi tiết
set_debug(False)

# 1. Định nghĩa State

class AgentState(TypedDict, total=False):
    messages:  Annotated[list[BaseMessage], add_messages]

    current_intent: str      

    selected_flower: dict     

    search_context: dict    

    search_results: list

    customer_info: dict     

    pending_missing_fields: list  

    last_tool: str      
    tool_retry_count: int

INTENTS = [
    "search_flower",
    "flower_detail",
    "checkout",
    "smalltalk",
    "fallback"
]

# 2. Khởi tạo Model và công cụ
llm = ChatOllama(model="qwen3:8b", temperature=0)
tools = [search_flowers, get_flower_details, process_order]

# 3. Node xử lý chính 
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
    Bạn là intent classifier cho shop hoa. **QUANTRỌNG: Phân loại CHÍNH XÁC intent cuối cùng của khách.**

    5 INTENT:
    1. search_flower: Khách **TÌM KIẾM** hoa (từ khóa: tìm, search, loại, giá, màu, style, có tiêu chí)
    2. flower_detail: Khách **HỎI CHI TIẾT MỘT MẪU CỤ THỂ** (có tên mẫu + hỏi: gồm, chi tiết, giá, hình)
    3. checkout: Khách **MUỐN ĐẶT HÀNG** (từ khóa: đặt, mua, giao, nhận, thanh toán)
    4. small_talk: Chuyện thông thường, chào hỏi
    5. fallback: Không xác định được

    ⭐ PRIORITY RULES:
    - Nếu message **CÓ TÊN MẪU HỌA CỤ THỂ + HỎI CHI TIẾT** (gồm, là gì, giá, ảnh, mô tả) → **flower_detail**
      VD: "Just for you gồm hoa gì", "còn mẫu Dreaming", "Just for you chi tiết?"
    - Nếu message chỉ **TÌM KIẾM** (có tiêu chí: giá, màu, loại) → **search_flower**
      VD: "tìm hoa giá 300-500", "tìm hoa vàng", "tìm hoa gì"
    - Nếu message **ĐỀ CẬP ĐẶT HÀNG** → **checkout**
    - Nếu **KO RÕ** → **search_flower** (default)

    **LỊCH SỬ HỘI THOẠI:**
    {history_text}

    **CHỈNH LẠI: Chỉ trả về label duy nhất (search_flower, flower_detail, checkout, small_talk, fallback).**
    """
    result = llm.invoke(prompt).content.strip().lower()

    if result not in INTENTS:
        result = "fallback"

    print("Intent:", result)

    # Persist predicted intent into state so router can use it deterministically
    return {"current_intent": result}

from app.core_ai import get_query_intent

"""
🌸 Search Node - Agentic Workflow
1. Trích xuất intent từ user query
2. Gọi search_flowers trực tiếp
3. Tạo ToolMessage với kết quả
4. Extract selected_flower từ kết quả
5. Sinh câu trả lời thân thiện bằng LLM
6. Return messages kèm selected_flower và search_context
"""
# Helper merge
def merge_search_context(old_context: dict, new_context: dict) -> dict:
    merged = dict(old_context or {})
    for key, value in (new_context or {}).items():
        if value not in [None, "", []]:
            merged[key] = value
    return merged


def search_node(state: AgentState):
    last_msg = state["messages"][-1]
    user_text = last_msg.get("content") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")

    # 1. Trích xuất intent từ user query (Regex + LLM hybrid)
    intent = get_query_intent(user_text) or {}
    for k in ("flower", "min_price", "max_price"):
        intent.setdefault(k, None)

    # 2. Tạm thời tắt enrichment LLM lần 2 để tránh tự đổi field query sang tiếng Anh.
    # Chỉ dùng intent đã qua xử lý trong core_ai.

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


def route_by_intent(state: AgentState):
    ci = state.get("current_intent")
    if ci in INTENTS:
        return ci
    return "fallback"

def detail_node(state: AgentState):
    """
    🔎 Detail Node - Agentic Workflow
    1. Extract flower_name và flower_id từ lịch sử
    2. Gọi get_flower_details trực tiếp
    3. Tạo ToolMessage với kết quả
    4. Sinh câu trả lời thân thiện bằng LLM
    5. Return messages
    """
    print("[Detail Node] Processing...")
    
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
            # Chỉ lấy tới khi gặp "gồm", "là gì", "chi tiết", etc.
            m_name = re.search(
                r'(?:[Mm]ẫu|[Tt]ên hoa|lấy)\s+[:\-]?\s*(.+?)(?:\s+(?:gồm|là gì|dó là gì|giá bao|bao nhiêu|ở đâu|như thế nào|chi tiết|thì).*)?$',
                user_msg
            )
            if m_name:
                raw_name = m_name.group(1).strip()
                # ⭐ FINAL CLEAN UP: Loại bỏ phần dư thừa nếu còn (dự phòng)
                cleaned_name = re.sub(r'\s+(?:gồm|là gì|dó là gì|giá bao|bao nhiêu|ở đâu|như thế nào|thì|gì|nào).*$', '', raw_name, flags=re.IGNORECASE)
                flower_name = cleaned_name.strip() or raw_name.strip()
                print(f"  [OK] Extracted từ user message: {flower_name}")

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
        
        # Nếu user nói "mẫu thứ 2" hoặc "mẫu 2", thử lấy trực tiếp từ search_results đã lưu
        m_ord = re.search(r'mẫu\s*(?:thứ\s*)?(\d{1,2})', (user_msg or "").lower())
        if m_ord and state.get("search_results"):
            try:
                idx = int(m_ord.group(1))
                results = state.get("search_results", [])
                if 1 <= idx <= len(results):
                    chosen = results[idx-1]
                    flower_name = chosen.get("name") or flower_name
                    flower_id = chosen.get("id") or chosen.get("ma_so") or chosen.get("maSo")
                    try:
                        flower_id = int(flower_id)
                    except Exception:
                        pass
                    print(f"  ✅ User referenced ordinal: using search_results index {idx} -> {flower_name} (id={flower_id})")
                    return flower_name, flower_id
            except Exception:
                pass

        # Nếu đã extract được flower_name nhưng chưa có ID, gọi search ngay để lấy candidates và lưu vào state
        if flower_name and not flower_id:
            try:
                print(f"  ℹ️ Calling search_flowers for extracted name: {flower_name}")
                sr = search_flowers.invoke({"query": flower_name})
                # search_flowers may return dict with 'results' or 'items'
                results = sr.get("results") or sr.get("items") or sr.get("data") or []
                normalized = []
                for i, it in enumerate(results):
                    nid = it.get("id") or it.get("ma_so") or it.get("maSo") or it.get("id")
                    name = it.get("name") or it.get("ten_hoa") or ""
                    normalized.append({"index": i+1, "id": nid, "name": name, **it})
                if normalized:
                    state["search_results"] = normalized
                    # Try to find exact-name match in returned results
                    for it in normalized:
                        if (flower_name or "").lower() == (it.get("name") or "").lower():
                            try:
                                flower_id = int(it.get("id")) if it.get("id") is not None else None
                            except Exception:
                                flower_id = it.get("id")
                            flower_name = it.get("name")
                            print(f"  ✅ Matched exact name in search_results: {flower_name} (id={flower_id})")
                            return flower_name, flower_id
            except Exception as e:
                print(f"  ⚠️ search_flowers invoke failed: {e}")
        
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

                # b) ⭐ PRIORITY: Inspect items từ tool result - EXACT NAME MATCH TRƯỚC
                if isinstance(msg, dict) and msg.get("role") == "tool":
                    items = msg.get("results") or msg.get("items") or []
                    if isinstance(items, list) and items:
                        # PASS 1: Exact name match (case-insensitive)
                        for it in items:
                            iname = str(it.get("name", "") or "")
                            iid = it.get("id") or it.get("ma_so") or it.get("maSo")
                            if iname and name_lower == iname.lower():
                                try:
                                    flower_id = int(iid) if iid else None
                                    print(f"  ✅ Found ID from search result (EXACT MATCH): {flower_id}")
                                    return iname, flower_id
                                except Exception:
                                    return iname, None
                        
                        # PASS 2: Partial name match (flower_name in item name)
                        for it in items:
                            iname = str(it.get("name", "") or "")
                            iid = it.get("id") or it.get("ma_so") or it.get("maSo")
                            if iname and name_lower in iname.lower():
                                try:
                                    flower_id = int(iid) if iid else None
                                    print(f"  ✅ Found ID from search result (PARTIAL MATCH): {flower_id}")
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
    print("[Checkout Node] Processing...")
    
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
        # PRIORITY: If user explicitly mentioned a sample name, try to resolve it
        try:
            sr = state.get("search_results") or []
            for it in sr:
                iname = str(it.get("name", "") or "")
                iid = it.get("id") or it.get("ma_so") or it.get("maSo")
                if iname and iname.lower() in last_user.lower():
                    customer["loai_hang"] = f"{iname} - {iid}" if iid else iname
                    print(f"✅ Resolved loai_hang from search_results mention: {customer['loai_hang']}")
                    break
        except Exception:
            pass

        # ⭐ TRY EXTRACT COMBINED NGÀY+GIỜ TRƯỚC TIÊN (dạng "17/5 lúc 17h")
        date_raw, time_raw = _extract_date_and_time_combined(last_user)
        if date_raw and time_raw:
            normalized_date, date_error = _normalize_order_date(date_raw)
            norm_time, time_error = _parse_time_vietnamese(time_raw)
            if normalized_date and norm_time:
                customer["ngay_nhan"] = normalized_date
                customer["gio_nhan"] = norm_time
                print(f"✅ Extracted combined date+time: {normalized_date} {norm_time}")
        
        # Fallback: LLM EXTRACTION cho các trường khác
        extract_prompt = (
            "Từ đoạn sau, trích xuất JSON chỉ các trường có thể: "
            r'{"ten_khach":..., "sdt":..., "dia_chi":..., "loai_hang":..., "so_luong":..., "ngay_nhan":..., "gio_nhan":...}. '
            f"Nếu không có trường nào thì không include. Đoạn:\n" + last_user
        )
        try:
            resp = llm.invoke([{"role": "user", "content": extract_prompt}])
            match = re.search(r'\{.*\}', resp.content, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                for k, v in parsed.items():
                    if v not in [None, "", []]:
                        # Đừng overwrite nếu đã extract từ combined date+time
                        if not (k in ("ngay_nhan", "gio_nhan") and customer.get(k)):
                            # Don't allow LLM to overwrite authoritative loai_hang
                            if k == "loai_hang" and customer.get("loai_hang"):
                                continue
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
- Ngày nhận (ví dụ: 25/12 hoặc 25/12/2026; nếu chỉ nhập 25/12 thì hệ thống sẽ tự hiểu là năm hiện tại)
- Giờ nhận (ví dụ: 15:00, 5h, '5 giờ chiều')

💡 **Ví dụ trả lời:**
- Cách 1: "Tôi tên Linh, SĐT 0901234567, địa chỉ 123 Nguyễn Huệ Q1, muốn 2 cái hoa hồng đỏ, nhận ngày 25/12 lúc 15:00"
- Cách 2: "Tôi tên Linh, SĐT 0901234567, địa chỉ 123 Nguyễn Huệ Q1, muốn 2 cái hoa hồng đỏ, nhận 25/12 lúc 3 giờ chiều"
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

    if not tool_result.get("success") and tool_result.get("invalid_field") == "ngay_nhan":
        return {
            "messages": [AIMessage(content=tool_result.get("text", "Ngày nhận không hợp lệ, vui lòng nhập lại."))],
            "customer_info": customer,
            "pending_missing_fields": ["ngay_nhan"]
        }

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
    print("[Smalltalk Node] Processing...")
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