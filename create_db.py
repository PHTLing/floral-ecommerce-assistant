import json
import re

import chromadb
from chromadb.utils import embedding_functions


DB_PATH = "./new_flower_db"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


FLOWER_TYPE_ALIASES = {
    "hoa hồng": ["hoa hồng", "hồng", "rose", "only rose"],
    "hoa hướng dương": ["hoa hướng dương", "hướng dương", "sunflower"],
    "hoa sen đá": ["hoa sen đá", "sen đá", "succulent"],
    "hoa cúc": ["hoa cúc", "cúc", "daisy"],
    "hoa ly": ["hoa ly", "ly", "lily", "loa kèn"],
    "hoa lan": ["hoa lan", "lan", "orchid"],
    "hoa baby": ["hoa baby", "baby"],
    "hoa tulip": ["hoa tulip", "tulip"],
    "hoa đồng tiền": ["hoa đồng tiền", "đồng tiền"],
    "hoa cẩm chướng": ["hoa cẩm chướng", "cẩm chướng"],
    "hoa cẩm tú cầu": ["hoa cẩm tú cầu", "cẩm tú cầu", "hydrangea"],
    "hoa mẫu đơn": ["hoa mẫu đơn", "mẫu đơn", "peony"],
    "hoa cát tường": ["hoa cát tường", "cát tường", "lisianthus"],
    "hoa lan hồ điệp": ["hoa lan hồ điệp", "lan hồ điệp", "phalaenopsis"],
}

FLOWER_TYPE_WEIGHTS = {
    "ten_hoa": 5,
    "tags": 3,
    "muc_dich": 2,
    "thanh_phan": 1,
    "mo_ta": 1,
}


# =========================
# CLEAN PRICE
# =========================
def clean_price(price_str):
    """
    "650.000đ" -> 650000
    "500k" -> 500000
    """
    if not price_str:
        return 0

    s = str(price_str).lower().strip()

    if "k" in s:
        nums = re.findall(r"\d+", s)
        if nums:
            return int(nums[0]) * 1000

    nums = re.findall(r"\d+", s)
    if nums:
        return int("".join(nums))

    return 0


# =========================
# NORMALIZE TEXT
# =========================
def normalize_text(text):
    if not text:
        return ""
    return str(text).strip().lower()


# =========================
# RULE-BASED TAG EXTRACT
# =========================
COLORS = [
    "đỏ", "trắng", "hồng",
    "vàng", "cam", "tím",
    "xanh lá", "xanh dương", "xanh ngọc"
]

STYLES = [
    "pastel",
    "sang trọng",
    "nhẹ nhàng",
    "hiện đại"
]


def _compose_search_text(item):
    parts = [
        item.get("ten_hoa", ""),
        " ".join(item.get("thanh_phan", []) or []),
        " ".join(item.get("tags", []) or []),
        item.get("mo_ta", ""),
    ]
    return normalize_text(" ".join(str(part) for part in parts if part))


def infer_flower_type(item):
    text = _compose_search_text(item)
    for canonical, aliases in FLOWER_TYPE_ALIASES.items():
        if any(alias in text for alias in aliases):
            return canonical
    return ""


def infer_color(text):
    normalized = normalize_text(text)
    for color in COLORS:
        if color in normalized:
            return color
    return ""


def infer_style(text):
    normalized = normalize_text(text)
    for style in STYLES:
        if style in normalized:
            return style
    return ""


def _collect_flower_type_scores(item):
    scores = {}
    
    tags_list = item.get("tags", []) or []
    sources = {
        "ten_hoa": item.get("ten_hoa", ""),
        "tags": " ".join(tags_list),
        "thanh_phan": " ".join(item.get("thanh_phan", []) or []),
        "mo_ta": item.get("mo_ta", ""),
    }

    for source_name, source_text in sources.items():
        if not source_text:
            continue
        normalized = normalize_text(source_text)
        weight = FLOWER_TYPE_WEIGHTS.get(source_name, 1)
        for canonical, aliases in FLOWER_TYPE_ALIASES.items():
            if any(alias in normalized for alias in aliases):
                scores[canonical] = scores.get(canonical, 0) + weight

    return scores


def _serialize_flower_type_scores(scores):
    if not scores:
        return ""
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return "|".join(f"{name}:{score}" for name, score in ordered)


def _pick_primary_flower_type(scores):
    if not scores:
        return ""
    return max(scores.items(), key=lambda x: x[1])[0]


def extract_search_params(item):
    text = _compose_search_text(item)
    flower_type_scores = _collect_flower_type_scores(item)
    return {
        "color": infer_color(text),
        "style": infer_style(text),
        "primary_flower_type": _pick_primary_flower_type(flower_type_scores),
        "flower_types_text": _serialize_flower_type_scores(flower_type_scores),
        "flower_type_scores": flower_type_scores,
    }

# =========================
# BUILD DB
# =========================
def build_optimized_db():

    print("🚀 Building optimized flower DB...")

    client = chromadb.PersistentClient(path=DB_PATH)

    emb_func = (
        embedding_functions
        .SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
    )

    # xóa cũ
    try:
        client.delete_collection("flower_catalog")
        print("🗑️ Old collection deleted")
    except:
        pass

    collection = client.create_collection(
        name="flower_catalog",
        embedding_function=emb_func
    )

    # load data
    with open(
        "database_hoa_v2.json",
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    documents = []
    metadatas = []
    ids = []

    for item in data:

        # -------------------
        # price
        # -------------------
        gia_so = clean_price(
            item.get("gia_moi", "0")
        )

        # -------------------
        # components
        # -------------------
        thanh_phan_list = item.get(
            "thanh_phan", []
        )

        thanh_phan_str = (
            ", ".join(thanh_phan_list)
            if thanh_phan_list
            else "Hoa tươi hỗn hợp"
        )

        tags_list = item.get("tags", [])
        dip_tang = ", ".join(tags_list)

        extracted = extract_search_params(item)
        primary_flower_type = extracted.get("primary_flower_type", "")
        flower_types_text = extracted.get("flower_types_text", "")
        flower_type_scores = extracted.get("flower_type_scores", {})

        if not primary_flower_type:
            primary_flower_type = infer_flower_type(item)

        content = (
            f"MÃ SỐ: {item['id']}. "
            f"SẢN PHẨM: {item['ten_hoa']}. "
            f"LOẠI HOA CHÍNH: {primary_flower_type}. "
            f"LOẠI HOA PHỤ: {flower_types_text}. "
            f"THÀNH PHẦN: {thanh_phan_str}. "
            f"MỤC ĐÍCH: {dip_tang}. "
            f"MÀU: {extracted['color']}. "
            f"PHONG CÁCH: {extracted['style']}. "
            f"MÔ TẢ: {item.get('mo_ta', '')}"
        )

        documents.append(content)

        ids.append(
            str(item["id"])
        )

        # -------------------
        # metadata
        # cái này dùng filter
        # -------------------
        metadatas.append({
            "id": item["id"],
            "ten_hoa": item["ten_hoa"],
            "gia_so": gia_so,

            "url": item["url"],
            "hinh_anh": item["hinh_anh"],

            "mo_ta": item.get("mo_ta", ""),
            "thanh_phan": thanh_phan_str,
            "muc_dich": dip_tang,

            "primary_flower_type": primary_flower_type,
            "flower_types_text": flower_types_text,
            "flower_type_scores": json.dumps(flower_type_scores, ensure_ascii=False),
            "color": extracted["color"],
            "style": extracted["style"]
        })

        print("Processed item:", item["id"], end="\r")
        print("Metadata:", metadatas[-1])

    print(
        f"⏳ Đang nạp {len(documents)} sản phẩm..."
    )

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )
    
    print("✅ Build DB thành công!")
    print("📦 Collection: flower_catalog")


if __name__ == "__main__":
    build_optimized_db()