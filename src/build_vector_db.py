import chromadb
from chromadb.utils import embedding_functions
import json
import os

# Cấu hình lưu trữ local
DB_PATH = "./flower_db"
COLLECTION_NAME = "flower_catalog"

def build():
    client = chromadb.PersistentClient(path=DB_PATH)
    # Model này sẽ được tải về máy bạn ở lần đầu tiên chạy
    emb_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=emb_func)

    with open('database_hoa.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    documents = []
    metadatas = []
    ids = []

    for item in data:
        content = f"Tên: {item['ten_hoa']}. Mô tả: {item['mo_ta']}. Thành phần: {', '.join(item['thanh_phan'])}. Tags: {', '.join(item['tags'])}"
        documents.append(content)
        ids.append(item['id'])
        metadatas.append({
            "ten_hoa": item['ten_hoa'],
            "gia": item['gia_moi'],
            "url": item['url']
        })

    print(f"⏳ Đang nạp {len(documents)} sản phẩm vào ChromaDB...")
    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print("✅ Đã xây dựng xong bộ não hoa tươi!")

if __name__ == "__main__":
    build()