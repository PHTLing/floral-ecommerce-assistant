import json
import re
import chromadb
from chromadb.utils import embedding_functions

# Hàm xử lý giá: "1.200.000 đ" -> 1200000
def clean_price(price_str):
    if not price_str: return 0
    # Xóa tất cả ký tự không phải số
    price_number = re.sub(r'\D', '', price_str)
    return int(price_number) if price_number else 0

def build_optimized_db():
    client = chromadb.PersistentClient(path="./flower_optimized_db")
    emb_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    # Xóa collection cũ để nạp lại từ đầu cho sạch
    try:
        client.delete_collection("flower_catalog")
    except:
        pass
        
    collection = client.create_collection(name="flower_catalog", embedding_function=emb_func)

    with open('database_hoa.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    documents = []
    metadatas = []
    ids = []

    for item in data:
        # 1. Xử lý giá số để lọc
        gia_so = clean_price(item.get('gia_moi', '0'))
        
        # 2. Cấu trúc lại nội dung để Embedding "hiểu" sâu hơn
        # Gộp các tags và thành phần thành chuỗi
        # CHỖ CẦN SỬA: Chuyển list thành string ngay từ đây
        thanh_phan_list = item.get('thanh_phan', [])
        # Nếu list rỗng thì để chuỗi là "Nhiều loại hoa", nếu có thì nối lại bằng dấu phẩy
        thanh_phan_str = ", ".join(thanh_phan_list) if thanh_phan_list else "Hoa tươi hỗn hợp"
        dip_tang = ", ".join(item.get('tags', []))
        
        content = (
            f"SẢN PHẨM: {item['ten_hoa']}. "
            f"LOẠI HOA: {thanh_phan_str}. "
            f"MỤC ĐÍCH: {dip_tang}. "
            f"MÔ TẢ: {item.get('mo_ta', '')}"
        )
        
        documents.append(content)
        ids.append(item['id'])
        
        # 3. Lưu Metadata phong phú để phục vụ Query Filtering
        metadatas.append({
            "ten_hoa": item['ten_hoa'],
            "gia_so": gia_so, # Lưu dạng số để lọc giá
            "url": item['url'],
            "hinh_anh": item['hinh_anh'],
            "mo_ta": item.get('mo_ta', ''),
            "thanh_phan": thanh_phan_str,
        })

    print(f"⏳ Đang nạp {len(documents)} sản phẩm đã tối ưu...")
    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print("✅ Hệ thống đã sẵn sàng với dữ liệu chuẩn RAG!")

build_optimized_db()