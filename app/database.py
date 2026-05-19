import chromadb
from chromadb.utils import embedding_functions

DB_PATH = "./flower_db_v2"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "flower_catalog"

db_client = chromadb.PersistentClient(path=DB_PATH)
emb_func = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
collection = db_client.get_collection(name=COLLECTION_NAME, embedding_function=emb_func)

def query_flowers(search_text, filter_cond=None, n_results=3):
    return collection.query(
        query_texts=[search_text],
        n_results=n_results,
        where=filter_cond 
    )