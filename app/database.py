import chromadb
from chromadb.utils import embedding_functions

# Kết nối tới Database đã tạo ở file build_db.py
db_client = chromadb.PersistentClient(path="./flower_optimized_db")
emb_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
collection = db_client.get_collection(name="flower_catalog", embedding_function=emb_func)

def query_flowers(search_text, filter_cond=None, n_results=3):
    return collection.query(
        query_texts=[search_text],
        n_results=n_results,
        where=filter_cond # Nếu filter_cond là None, ChromaDB sẽ lấy tất cả
    )