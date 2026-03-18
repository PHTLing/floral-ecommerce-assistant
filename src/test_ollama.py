import json
import os
import re
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions
import ollama

# Kết nối tới Database đã tạo ở file build_db.py
db_client = chromadb.PersistentClient(path="./flower_optimized_db")
emb_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
collection = db_client.get_collection(name="flower_catalog", embedding_function=emb_func)

chat_history = [] 
current_constraints = {
    "min_price": None,
    "max_price": None,
    "type": None,
    "occasion": None
}
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
        return intent
    else:
        intent = get_search_intent(user_query)

    for key in ['min_price', 'max_price']:
        if intent.get(key) and 0 < intent[key] < 2000:
            intent[key] *= 1000
    return intent


def add_to_history(user_msg, bot_msg):
    # Lưu tối đa 10 lượt gần nhất để tránh tràn bộ nhớ và loãng context
    chat_history.append({"role": "user", "content": user_msg})
    chat_history.append({"role": "assistant", "content": bot_msg})
    
    if len(chat_history) > 20: # 10 cặp
        chat_history.pop(0)
        chat_history.pop(0)

def get_chat_context():
    # Chuyển list thành văn bản để gửi cho AI
    context = ""
    for msg in chat_history:
        role = "Khách" if msg['role'] == "user" else "Bot"
        context += f"{role}: {msg['content']}\n"
    return context

def rewrite_query_with_history(new_query):
    if not chat_history:
        return new_query

    history_str = get_chat_context()
    
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

def ask_ai(query):
    # --- TRONG HÀM TÌM KIẾM ---
    global current_constraints
    # Bước A: AI phân tích yêu cầu
    rewritten_query = rewrite_query_with_history(query)
    rewritten_query = rewritten_query.replace('"', '').replace("'", "") # Loại bỏ dấu ngoặc nếu có
    print(f"🔄 Câu hỏi đã được viết lại: {rewritten_query}")

    intent = get_final_intent(rewritten_query)

    # 3. LOGIC CẬP NHẬT TRẠNG THÁI (Mấu chốt ở đây)
    new_min = intent.get('min_price')
    new_max = intent.get('max_price')

    if new_min is not None and new_max is not None:
        # Nếu khách nhập cả đôi (từ...đến...), cập nhật cả hai
        current_constraints['min_price'] = new_min
        current_constraints['max_price'] = new_max
    elif new_max is not None:
        # Nếu khách chỉ nói "Dưới 300k", thường là họ muốn bỏ cái min_price cũ đi
        current_constraints['max_price'] = new_max
        current_constraints['min_price'] = None
    # Dùng giá trong bộ nhớ bền vững để lọc, thay vì dùng trực tiếp từ intent mới
    max_price_to_use = current_constraints['max_price']
    min_price_to_use = current_constraints['min_price']

    search_text = intent.get('search_text', rewritten_query)
    print(f"🔍 AI phân tích: search_text='{search_text}', min_price='{min_price_to_use}', max_price='{max_price_to_use}'")

    # Bước B: Xây dựng bộ lọc động
    filter_cond = {}
    conditions = []
    if max_price_to_use:
        conditions.append({"gia_so": {"$lte": current_constraints['max_price']}})
    if min_price_to_use:
        conditions.append({"gia_so": {"$gte": current_constraints['min_price']}})

    # Nếu có cả min và max, dùng toán tử $and
    if len(conditions) > 1:
        filter_cond = {"$and": conditions}
    elif len(conditions) == 1:
        filter_cond = conditions[0]

    # Bước C: Truy vấn bộ não ChromaDB
    results = collection.query(
        query_texts=[search_text],
        n_results=3,
        where=filter_cond if filter_cond else None
    )

    # Bước D: Hiển thị kết quả
    if not results['documents'][0]:
        bot_response = "😔 Xin lỗi, tiệm hiện không tìm thấy mẫu hoa nào phù hợp với yêu cầu của bạn."
    else:
        # Chúng ta gom tên các loài hoa tìm được để Bot "ghi nhớ" là đã giới thiệu gì
        flower_names = [meta['ten_hoa'] for meta in results['metadatas'][0]]
        bot_response = f"✨ Tiệm tìm thấy vài mẫu '{search_text}' rất đẹp cho bạn như: {', '.join(flower_names)}."
        
        # In ra màn hình cho người dùng xem chi tiết như cũ
        print(bot_response)
        for i in range(len(results['documents'][0])):
            meta = results['metadatas'][0][i]
            print(f"--- Gợi ý {i+1} ---")
            print(f"🌹 Tên: {meta['ten_hoa']}")
            gia_hien_thi = meta.get('gia_so') 
            print(f"💰 Giá: {gia_hien_thi}")
            print(f"🔗 Xem ảnh và đặt hàng: {meta['url']}")
    
    add_to_history(query, bot_response)
    print(f"Lịch sử chat {chat_history}.")

if __name__ == "__main__":
    while True:
        user_input = input("\nNhập nhu cầu tìm hoa của bạn (hoặc 'exit' để thoát): ")
        if user_input.lower() == 'exit': 
            break
        elif user_input.lower() == 'reset':
            current_constraints = {"max_price": None}
            chat_history.clear()
            print("🧹 Đã xóa bộ nhớ, bạn có thể bắt đầu yêu cầu mới!")
            continue
        ask_ai(user_input)