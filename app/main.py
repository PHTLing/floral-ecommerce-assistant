from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel
# Import từ các file Linh vừa chia
from app.core_ai import get_final_intent, rewrite_query_with_history, generate_sweet_response
from app.database import query_flowers
import logging

app = FastAPI(title="Floral Chatbot API")

# origins = [
#     "http://localhost:3000",
#     "http://127.0.0.1:3000",
# ]
# Thêm middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả các phương thức
    allow_headers=["*"],  # Cho phép tất cả các header
)



# Biến lưu trữ (Sau này thay bằng Redis ở đây)
sessions_data = {}

class ChatRequest(BaseModel):
    user_input: str
    session_id: str
@app.get("/")
async def root():
    return {"message": "Floral Chatbot API is running! Go to /docs to test."}

# Cấu hình Logging: Hiện thời gian, cấp độ lỗi và thông tin
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("chatbot_debug.log", encoding='utf-8'), # Lưu vào file
        logging.StreamHandler() # Hiện ra terminal
    ]
)
logger = logging.getLogger("FloralAPI")

@app.post("/chat")
async def chat(request: ChatRequest):
    query = request.user_input
    sid = request.session_id
    
    # Logic quản lý history theo session_id
    if sid not in sessions_data:
        sessions_data[sid] = {"history": [], "constraints": {"min_price": None, "max_price": None}}
    
    user_session = sessions_data[sid]
    old_constraints = user_session["constraints"]

    # 1. Xử lý logic AI (gọi từ core_ai)
    rewritten_query = rewrite_query_with_history(query, sessions_data[sid]["history"])
    intent = get_final_intent(rewritten_query)
    
    # 2. Query DB (gọi từ database)
    # ... (Linh đưa logic filter_cond vào đây) ...
    # 3. LOGIC CẬP NHẬT TRẠNG THÁI (Mấu chốt ở đây)
    new_min = intent.get('min_price')
    new_max = intent.get('max_price')

    if new_min is not None and new_max is not None:
        # Nếu khách nhập cả đôi (từ...đến...), cập nhật cả hai
        user_session["constraints"]["min_price"] = new_min
        user_session["constraints"]["max_price"] = new_max
    elif new_max is not None:
        # Nếu khách chỉ nói "Dưới 300k", thường là họ muốn bỏ cái min_price cũ đi
        user_session["constraints"]["max_price"] = new_max
        user_session["constraints"]["min_price"] = None
    # Dùng giá trong bộ nhớ bền vững để lọc, thay vì dùng trực tiếp từ intent mới
    max_price_to_use = user_session["constraints"]["max_price"]
    min_price_to_use = user_session["constraints"]["min_price"]

    search_text = intent.get('search_text', rewritten_query)
    print(f"🔍 AI phân tích: search_text='{search_text}', min_price='{min_price_to_use}', max_price='{max_price_to_use}'")
    
    filter_cond = None
    conditions = []
    if max_price_to_use:
        conditions.append({"gia_so": {"$lte": max_price_to_use}})
    if min_price_to_use:
        conditions.append({"gia_so": {"$gte": min_price_to_use}})

    # Nếu có cả min và max, dùng toán tử $and
    if len(conditions) > 1:
        filter_cond = {"$and": conditions}
    elif len(conditions) == 1:
        filter_cond = conditions[0]
    results = query_flowers(intent['search_text'], filter_cond)

    # 1. Chuẩn hóa danh sách hoa (data) theo format mà React cần
    flower_list = []
    if results['metadatas'] and results['metadatas'][0]:
        for meta in results['metadatas'][0]:
            flower_list.append({
                "name": meta.get('ten_hoa', 'Hoa đẹp'),
                "price": f"{meta.get('gia_so', 0):,}đ", # Định dạng 500.000đ
                "image": meta.get('hinh_anh', ''), # Nhớ dùng đúng key url_anh trong DB của bạn
                "url": meta.get('url', '')
            })

    # 6. Tạo câu trả lời và CẬP NHẬT HISTORY
    if not results['documents'][0]:
        bot_reply = f"Tiệm không tìm thấy mẫu hoa nào phù hợp với yêu cầu '{search_text}' của bạn."
    else:
        flower_names = [m['ten_hoa'] for m in results['metadatas'][0]]
        bot_reply = generate_sweet_response(search_text, [{"name": n, "description": "", "price": f"{m['gia_so']:,}đ"} for m, n in zip(results['metadatas'][0], flower_names)])

    # LƯU VÀO BỘ NHỚ CỦA USER
    user_session["history"].append({"role": "user", "content": query})
    user_session["history"].append({"role": "assistant", "content": bot_reply})
    
    # Giới hạn lịch sử (giữ 10 câu gần nhất)
    if len(user_session["history"]) > 10:
        user_session["history"] = user_session["history"][-10:]

    # 4. Trả về đúng Format JSON mà chúng ta đã thống nhất cho React
    return {
        "reply": bot_reply,
        "data": flower_list  # Mảng các object {name, price, image}
    }
    