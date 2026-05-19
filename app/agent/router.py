from langchain_ollama import ChatOllama
from app.agent.message_utils import get_last_user_text
from app.agent.prompts import INTENT_CLASSIFIER_PROMPT

INTENTS = [
    "search_flower",
    "flower_detail",
    "checkout",
    "smalltalk",
    "fallback"
]

llm_router = ChatOllama(model="qwen3:4b", temperature=0)

def rule_route_intent(text: str) -> tuple[str, float]:
    t = (text or "").lower()

    checkout_keywords = ["đặt", "mua", "giao", "ship", "thanh toán", "chốt", "lấy mẫu"]
    detail_keywords = ["chi tiết", "gồm", "thành phần", "mẫu này", "giá bao nhiêu", "mô tả"]
    search_keywords = ["tìm", "kiếm", "có hoa", "giá", "dưới", "trên", "khoảng", "màu"]
    smalltalk_keywords = ["chào", "hello", "hi", "cảm ơn", "thanks"]

    if any(k in t for k in checkout_keywords):
        return "checkout", 0.9

    if any(k in t for k in detail_keywords):
        return "flower_detail", 0.8

    if any(k in t for k in search_keywords):
        return "search_flower", 0.75

    if any(k in t for k in smalltalk_keywords):
        return "smalltalk", 0.8

    return "fallback", 0.0

def classify_intent_with_llm(text: str, state: dict) -> str:
    prompt = INTENT_CLASSIFIER_PROMPT.format(
        user_text=text,
        selected_flower=state.get("selected_flower"),
        customer_info=state.get("customer_info"),
        pending_missing_fields=state.get("pending_missing_fields"),
    )

    result = llm_router.invoke(prompt).content.strip().lower()
    return result if result in INTENTS else "fallback"

def intent_classifier(state: dict): 
    # Tôi muốn print agent state để debug
    print("\n" + "="*30)
    print("🧠 [Agent] Classifying intent ...")
    print("Agent State:", state)

    user_text = get_last_user_text(state)

    intent, confidence = rule_route_intent(user_text)
    if confidence >= 0.75:
        return {"current_intent": intent}

    intent = classify_intent_with_llm(user_text, state)
    return {"current_intent": intent}

def route_by_intent(state: dict):
    intent = state.get("current_intent", "fallback")
    return intent if intent in INTENTS else "fallback"


