import os
from dotenv import load_dotenv
from google import genai # Lưu ý: từ google import genai chứ không phải google.generativeai

load_dotenv()

# Khởi tạo Client theo chuẩn mới 2026
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

for m in client.models.list():
    print(f"Tên model: {m.name} - Hỗ trợ: {m.supported_actions}")

# def get_search_params(user_query):
#     prompt = f"Trích xuất JSON (search_text, max_price) từ: '{user_query}'"
    
#     try:
#         # Cách gọi mới: client.models.generate_content
#         response = client.models.generate_content(
#             model='gemini-1.5-flash', 
#             contents=prompt
#         )
#         return response.text
#     except Exception as e:
#         print(f"❌ Lỗi kết nối Gemini: {e}")
#         return None

# # Thử nghiệm
# if __name__ == "__main__":
#     print("✅ Đang kết nối với Gemini Client đời mới...")
#     # Không nên print(client) vì nó chứa thông tin nhạy cảm, chỉ test hàm
#     test = get_search_params("Hoa hồng dưới 500k")
#     print(test)