# 🌸 FloraConsult - AI Flower Assistant (RAG System)

**FloraConsult** là một hệ thống Chatbot tư vấn hoa thông minh sử dụng kỹ thuật **RAG (Retrieval-Augmented Generation)**. Hệ thống giúp người dùng tìm kiếm mẫu hoa phù hợp theo nhu cầu, ngân sách và dịp tặng thông qua ngôn ngữ tự nhiên, kết hợp giữa sức mạnh của LLM và dữ liệu thực tế từ cửa hàng.

---

## ✨ Tính năng nổi bật

- **Tư vấn thông minh:** Sử dụng LLM (Qwen/Gemini) để đưa ra lời khuyên với lời văn mượt mà, cá nhân hóa.
- **Tìm kiếm chính xác:** Truy xuất dữ liệu hoa thời gian thực từ Vector Database (**ChromaDB**).
- **Lọc thông minh:** Tự động trích xuất Intent để lọc hoa theo giá tiền và mục đích (Sinh nhật, Tình yêu...).
- **Giao diện hiện đại:** Xây dựng bằng **React + Tailwind CSS**, hỗ trợ hiển thị danh sách sản phẩm trực quan.
- **Link mua hàng:** Kết nối trực tiếp đến URL sản phẩm thật để khách hàng đặt hàng ngay lập tức.

---

## 🏗️ Kiến trúc hệ thống

Dự án được xây dựng trên mô hình RAG tiêu chuẩn:

1. **Dữ liệu:** File JSON chứa thông tin hoa (Tên, giá, mô tả, thành phần).
2. **Embedding:** Sử dụng `all-MiniLM-L6-v2` để chuyển đổi văn bản thành vector.
3. **Vector DB:** ChromaDB lưu trữ và thực hiện Similarity Search.
4. **Backend:** FastAPI xử lý logic, quản lý hội thoại và kết nối LLM.
5. **Frontend:** React hiển thị giao diện chat sinh động.

---

## 🚀 Hướng dẫn cài đặt

### 1. Yêu cầu hệ thống
- Python 3.9+
- Node.js & npm

### 2. Cài đặt Backend

```bash
# Di chuyển vào thư mục gốc
cd Floral_chatbot

# Tạo môi trường ảo và cài đặt thư viện
python -m venv env
source env/Scripts/activate  # Windows: env\Scripts\activate

pip install -r requirements.txt

# Khởi tạo Vector Database (chỉ cần chạy 1 lần)
python build_db.py

# Chạy server
uvicorn app.main:app --reload
```
### 3. Cài đặt Frontend

```bash
cd floral-frontend
npm install
npm start
```

---

## 🛠️ Công nghệ sử dụng

- **Language:** Python, JavaScript  
- **AI Framework:** ChromaDB, Sentence-Transformers  
- **Backend:** FastAPI, Uvicorn  
- **Frontend:** React, Tailwind CSS, Lucide Icons  
- **Model:** Qwen (Ollama) / Gemini API  

---

## 📂 Cấu trúc thư mục

```plaintext
Floral_chatbot/
├── app/                # Source code Backend
│   ├── main.py         # FastAPI Endpoints
│   └── database.py     # Logic kết nối ChromaDB
├── floral-frontend/    # Source code Frontend (React)
├── build_db.py         # Script nạp dữ liệu vào Vector DB
├── .gitignore          # Cấu hình bỏ qua file rác
└── requirements.txt    # Danh sách thư viện Python
```

---

## ⚖️ Disclaimer 

Dự án này được thực hiện hoàn toàn với mục đích **học tập và nghiên cứu cá nhân (Non-commercial & Educational purposes)**.
- **Dữ liệu:** Toàn bộ thông tin sản phẩm và hình ảnh được thu thập (crawl) từ các nguồn công khai trên Internet. Chúng tôi không sở hữu bản quyền đối với các dữ liệu này.
- **Mục đích:** Minh họa khả năng ứng dụng của hệ thống RAG trong thương mại điện tử.
---

