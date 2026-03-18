from fastapi import FastAPI
import redis
import json

app = FastAPI()
# Kết nối Redis để lưu trữ session
r = redis.Redis(host='localhost', port=6379, db=0)

@app.post("/chat/{session_id}")
async def chat_endpoint(session_id: str, message: str):
    # 1. Lấy dữ liệu cũ của người dùng này từ Redis
    user_data = r.get(session_id)
    if user_data:
        context = json.loads(user_data)
    else:
        context = {"history": [], "constraints": {"min_price": None, "max_price": None}}

    # 2. Đưa context vào hàm ask_ai của Linh (cần sửa hàm ask_ai để nhận vào context)
    response, updated_context = ask_ai_logic(message, context)

    # 3. Lưu lại trạng thái mới vào Redis (hết hạn sau 1 tiếng)
    r.setex(session_id, 3600, json.dumps(updated_context))

    return {"reply": response}