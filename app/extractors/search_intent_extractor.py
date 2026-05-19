import json
import re
import ollama

from app.utils.constants import FLOWER_TYPE_ALIASES, COLOR_ALIASES, STYLE_ALIASES

def canonical_from_alias(value, alias_dict):
    text = (value or "").strip().lower()
    if not text:
        return ""
    for canonical, aliases in alias_dict.items():
        if any(alias in text for alias in aliases):
            return canonical
    return value

def find_canonical_in_text(text, alias_dict):
    normalized = (text or "").strip().lower()
    if not normalized:
        return None
    for canonical, aliases in alias_dict.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None

def extract_price_range(query):
    query = query.lower().replace(',', '.')
    found_prices = []

    patterns = [
        (r'(\d+(?:\.\d+)?)\s*(?:triệu|tr|m)', 1000000),
        (r'(\d+(?:\.\d+)?)\s*(?:ngàn|nghìn|k|n)', 1000),
        (r'(\d+(?:\.\d+){1,})', 1)
        # (r'\b(\d+)\b', 1) # Bắt mọi số thuần túy
    ]

    for pattern, multiplier in patterns:
        matches = re.findall(pattern, query)
        for m in matches:
            val = float(m) * multiplier
            if val < 2000 and val > 0: val *= 1000 # Logic 500 -> 500k
            found_prices.append(int(val))

    if not found_prices:
        return None, None
    
    found_prices.sort()
    # Nếu chỉ có 1 số: mặc định là max_price (như cũ)
    if len(found_prices) == 1:
        return None, found_prices[0]
    
    # Nếu có từ 2 số trở lên: lấy min và max
    return found_prices[0], found_prices[-1]

def extract_by_rules(user_query: str) -> dict:
    min_price, max_price = extract_price_range(user_query)

    return {
        "flower": find_canonical_in_text(user_query, FLOWER_TYPE_ALIASES) or "",
        "color": find_canonical_in_text(user_query, COLOR_ALIASES) or "",
        "style": find_canonical_in_text(user_query, STYLE_ALIASES) or "",
        "min_price": min_price,
        "max_price": max_price,
    }

def intent_has_enough_signal(intent: dict) -> bool:
    return any([
        intent.get("flower"),
        intent.get("color"),
        intent.get("style"),
        intent.get("min_price"),
        intent.get("max_price"),
    ])

def normalize_intent_fields(intent: dict):
    intent = dict(intent or {})
    intent["flower"] = canonical_from_alias(intent.get("flower", ""), FLOWER_TYPE_ALIASES)
    intent["color"] = canonical_from_alias(intent.get("color", ""), COLOR_ALIASES)
    intent["style"] = canonical_from_alias(intent.get("style", ""), STYLE_ALIASES)

    for key in ["min_price", "max_price"]:
        value = intent.get(key)
        if value and 0 < int(value) < 2000:
            intent[key] = int(value) * 1000

    return intent

def clean_search_text(text):
    if not text:
        return ""

    text = str(text)

    unwanted_patterns = [
        r"dưới\s+\d+[\d\.\,]*\s*(triệu|tr|m|ngàn|nghìn|k|n|đ|vnđ)?",
        r"khoảng\s+\d+[\d\.\,]*\s*(triệu|tr|m|ngàn|nghìn|k|n|đ|vnđ)?",
        r"từ\s+\d+.*đến\s+\d+.*",
        r" giá\s+.*",
        r"[\"\'\?\!]",
    ]

    for pattern in unwanted_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return " ".join(text.split()).strip()

def get_search_intent_with_llm(user_query: str) -> dict:
    prompt = f"""
        Bạn là trợ lý bán hoa.
        Trích xuất JSON từ câu: "{user_query}"

        Chỉ trả về JSON:
        {{"flower": "...", "min_price": null, "max_price": null, "color": "...", "style": "..."}}

        Giữ giá trị bằng tiếng Việt, không dịch sang tiếng Anh.
        """

    try:
        response = ollama.chat(
            model="qwen3:4b",
            messages=[{"role": "user", "content": prompt}],
        )
        content = response["message"]["content"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return {}
        return json.loads(match.group())
    except Exception as exc:
        print(f"[search_intent_extractor] LLM extraction failed: {exc}")
        return {}

def merge_rule_and_llm(rule_intent: dict, llm_intent: dict) -> dict:
    merged = dict(llm_intent or {})

    for key, value in rule_intent.items():
        if value not in [None, "", []]:
            merged[key] = value

    return merged

def get_query_intent(user_query):
    rule_intent = extract_by_rules(user_query)

    if intent_has_enough_signal(rule_intent):
        return normalize_intent_fields(rule_intent)

    llm_intent = get_search_intent_with_llm(user_query)
    merged = merge_rule_and_llm(rule_intent, llm_intent)

    for key in ["flower", "color", "style"]:
        merged[key] = clean_search_text(merged.get(key, ""))

    return normalize_intent_fields(merged)