import json
import os
import re
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions
from google import genai
from google.genai import types

load_dotenv() # Nạp các biến từ file .env vào hệ thống
api_key = os.getenv("GEMINI_API_KEY")

# Kết nối tới Database đã tạo ở file build_db.py
db_client = chromadb.PersistentClient(path="./flower_optimized_db")
emb_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
collection = db_client.get_collection(name="flower_catalog", embedding_function=emb_func)


# Cấu hình Gemini (Bạn thay API Key của bạn vào nhé)
ai_client = genai.Client(
    api_key=api_key
)

def extract_max_price(query):
    query = query.lower().replace(',', '.')
    prices = []

    # Định nghĩa các mẫu tìm kiếm (Triệu và Ngàn)
    patterns = [
        (r'(\d+(?:\.\d+)?)\s*(?:triệu|tr|m)', 1000000),
        (r'(\d+(?:\.\d+)?)\s*(?:ngàn|nghìn|k|n)', 1000),
        (r'(\d+(?:\.\d+){1,})', 1) # Số thuần có dấu chấm như 800.000
    ]

    for pattern, multiplier in patterns:
        matches = re.findall(pattern, query)
        for m in matches:
            # Xử lý trường hợp số thuần có dấu chấm (800.000 -> 800000)
            clean_num = m.replace('.', '') if multiplier == 1 else m
            try:
                val = int(float(clean_num) * multiplier)
                prices.append(val)
            except:
                continue

    # Nếu tìm thấy nhiều số, lấy số lớn nhất làm trần chi phí (max_price)
    if prices:
        return max(prices)
    
    return None

def get_search_intent(user_query):
    # CHỈNH SỬA: Dùng types.Schema để định nghĩa cấu trúc
    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "search_text": types.Schema(type=types.Type.STRING),
            "max_price": types.Schema(
                any_of=[
                    types.Schema(type=types.Type.INTEGER),
                    types.Schema(type=types.Type.NULL)
                ]
            ),
        },
        required=["search_text"] # Chỉ bắt buộc search_text, max_price có thể null
    )

    config = types.GenerateContentConfig(
        response_mime_type='application/json',
        response_schema=schema, # Gán schema đã tạo ở trên
    )
    
    prompt = f"Bạn là nhân viên bán hoa. Hãy trích xuất search_text và max_price (nếu có) từ câu: '{user_query}'"
    
    try:
        # CHỈNH SỬA: Thêm 'models/' vào trước tên model
        response = ai_client.models.generate_content(
            model='models/gemini-2.5-flash',  
            contents=prompt,
            config=config
        )
        
        # In ra để kiểm tra
        print(f"🔍 AI phân tích: {response.text}")
        return json.loads(response.text)
        
    except Exception as e:
        print(f"⚠️ Lỗi kết nối AI: {e}")
        # Trả về giá trị an toàn nếu AI lỗi
        return {"search_text": user_query, "max_price": None}

# Việc sử dụng Hybrid Extraction (Regex + LLM) giúp giảm tải cho API, tăng tốc độ phản hồi (Latency) và đảm bảo độ chính xác tuyệt đối với các con số cụ thể.
def get_final_intent(user_query):
    # Ưu tiên dùng Regex vì nó nhanh và chính xác với số
    price_from_regex = extract_max_price(user_query)
    
    if price_from_regex:
        # Nếu đã có giá từ Regex, chỉ cần nhờ Gemini lấy search_text
        intent = get_search_intent(user_query) # Hàm bóc tách JSON cũ của bạn
        intent['max_price'] = price_from_regex
        return intent
    else:
        # Nếu Regex chịu thua, để Gemini lo hoàn toàn
        return get_search_intent(user_query)

def ask_ai(query):
    # --- TRONG HÀM TÌM KIẾM ---
    # Bước A: AI phân tích yêu cầu
    intent = get_final_intent(query)
    search_text = intent.get('search_text', query)
    max_price = intent.get('max_price')

    # Bước B: Xây dựng bộ lọc động
    filter_cond = {}
    if max_price:
        filter_cond["gia_so"] = {"$lte": max_price}
    
    # Bước C: Truy vấn bộ não ChromaDB
    results = collection.query(
        query_texts=[search_text],
        n_results=3,
        where=filter_cond if filter_cond else None
    )

    # Bước D: Hiển thị kết quả
    if not results['documents'][0]:
        print("😔 Xin lỗi, tiệm không tìm thấy mẫu hoa nào phù hợp với ngân sách của bạn.")
    else:
        print(f"\n✨ Đây là 3 gợi ý tốt nhất cho '{search_text}'" + (f" giá dưới {max_price:,}đ:" if max_price else ":"))
        for i in range(len(results['documents'][0])):
            meta = results['metadatas'][0][i]
            print(f"--- Gợi ý {i+1} ---")
            print(f"🌹 Tên: {meta['ten_hoa']}")
            gia_hien_thi = meta.get('gia_so') 
            print(f"💰 Giá: {gia_hien_thi}")
            print(f"🔗 Xem ảnh và đặt hàng: {meta['url']}")

if __name__ == "__main__":
    while True:
        user_input = input("\nNhập nhu cầu tìm hoa của bạn (hoặc 'exit' để thoát): ")
        if user_input.lower() == 'exit': break
        ask_ai(user_input)