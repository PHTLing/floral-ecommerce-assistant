import ollama
import re
import json

def extract_price_range(query):
    query = query.lower().replace(',', '.')
    found_prices = []

    patterns = [
        (r'(\d+(?:\.\d+)?)\s*(?:triệu|tr|m)', 1000000),
        (r'(\d+(?:\.\d+)?)\s*(?:ngàn|nghìn|k|n)', 1000),
        (r'(\d+(?:\.\d+){1,})', 1)
        # (r'\b(\d+)\b', 1) # Bắt mọi số thuần túy
    ]

    for pattern, multiplier in patterns:
        matches = re.findall(pattern, query)
        for m in matches:
            val = float(m) * multiplier
            if val < 2000 and val > 0: val *= 1000 # Logic 500 -> 500k
            found_prices.append(int(val))

    if not found_prices:
        return None, None
    
    # Nếu chỉ có 1 số: mặc định là max_price (như cũ)
    if len(found_prices) == 1:
        return None, found_prices[0]
    
    # Nếu có từ 2 số trở lên: lấy min và max
    found_prices.sort()
    min_price = found_prices[0]
    max_price = found_prices[-1]
    return min_price, max_price


def get_search_intent(user_query):
    prompt = f"""
    Bạn là trợ lý bán hoa. Trích xuất JSON từ câu: "{user_query}"
    Chỉ trả về JSON định dạng: {{"search_text": "...", "min_price": ..., "max_price": ...}}
    """
    try:
        # Gọi model chạy trên máy Linh
        response = ollama.chat(
            model='qwen3:4b',
            messages=[{'role': 'user', 'content': prompt}]
        )
        
        # Lấy nội dung văn bản trả về
        content = response['message']['content']
        
        # Dùng regex để trích xuất JSON từ văn bản trả về
        match = re.search(r'\{.*\}', content, re.DOTALL)
        return json.loads(match.group())
    except Exception as e:
        print(f"⚠️ Lỗi Local Model: {e}")
        return {"search_text": user_query, "min_price": None, "max_price": None}

def clean_search_text(text):
    # Loại bỏ các từ khóa về giá tiền và dấu ngoặc kép
    unwanted_patterns = [
        r'dưới\s+\d+[\d\.\,]*\s*(triệu|tr|m|ngàn|nghìn|k|n|đ|vnđ)?',
        r'khoảng\s+\d+[\d\.\,]*\s*(triệu|tr|m|ngàn|nghìn|k|n|đ|vnđ)?',
        r'từ\s+\d+.*đến\s+\d+.*',
        r' giá\s+.*',
        r'[\"\'\?\!]'
    ]
    for pattern in unwanted_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Xóa khoảng trắng thừa
    return " ".join(text.split()).strip()

 
# Việc sử dụng Hybrid Extraction (Regex + LLM) giúp giảm tải cho API, tăng tốc độ phản hồi (Latency) và đảm bảo độ chính xác tuyệt đối với các con số cụ thể.
def get_final_intent(user_query):
    # Ưu tiên dùng Regex vì nó nhanh và chính xác với số
    min_price, max_price = extract_price_range(user_query)
    
    
    if min_price is not None or max_price is not None:
        intent = get_search_intent(user_query)
        if min_price is not None:
            intent['min_price'] = min_price
        if max_price is not None:
            intent['max_price'] = max_price
        intent['search_text'] = clean_search_text(intent['search_text'])
        return intent
    else:
        intent = get_search_intent(user_query)

    for key in ['min_price', 'max_price']:
        if intent.get(key) and 0 < intent[key] < 2000:
            intent[key] *= 1000

    intent['search_text'] = clean_search_text(intent['search_text'])
    return intent

def get_chat_context(chat_history):
    # Chuyển list thành văn bản để gửi cho AI
    context = ""
    for msg in chat_history:
        role = "Khách" if msg['role'] == "user" else "Bot"
        context += f"{role}: {msg['content']}\n"
    return context

def rewrite_query_with_history(new_query, chat_history):
    if not chat_history:
        return new_query

    history_str = get_chat_context(chat_history)
    
    # Prompt để AI viết lại câu hỏi dựa trên ngữ cảnh
    prompt = f"""
    Dựa trên lịch sử chat, hãy viết lại câu hỏi mới nhất thành một câu tìm kiếm đầy đủ.
    Lịch sử:
    {history_str}
    Câu hỏi mới: "{new_query}"
    Câu hỏi đầy đủ (chỉ trả về 1 câu):"""

    # Gọi Ollama (Qwen 2.5:1.5b)
    response = ollama.chat(model='qwen3:4b', messages=[{'role': 'user', 'content': prompt}])
    rewritten = response['message']['content'].strip().replace('"', '').replace("'", "")
    return rewritten

def generate_sweet_response(user_query, flowers_data):
    # Tạo danh sách thông tin chi tiết để AI "đọc"
    flower_info = ""
    for f in flowers_data:
        flower_info += f"- {f['name']}: {f['description']} (Giá: {f['price']})\n"

    prompt = f"""
    Bạn là một chuyên gia tư vấn hoa nhiệt tình của tiệm 'FloraConsult'.
    Khách hàng hỏi: "{user_query}"
    Dựa trên các mẫu hoa sau đây, hãy viết một lời tư vấn mượt mà, ngọt ngào để gợi ý cho khách:
    {flower_info}
    
    Yêu cầu:
    - Câu trả lời tự nhiên, có cảm xúc.
    - Nhắc tên được các mẫu hoa tiêu biểu.
    - Kết thúc bằng một câu mời gọi khách xem chi tiết.
    - Không viết quá dài dòng.
    """
    
    # Gọi model (Ollama hoặc Gemini)
    response = ollama.chat(model='qwen3:4b', messages=[{'role': 'user', 'content': prompt}])
    return response['message']['content']
