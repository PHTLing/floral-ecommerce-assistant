import json
import uuid
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def append_user_message(state: dict, text: str) -> dict:
    new_state = dict(state)
    messages = list(new_state.get("messages", []))
    messages.append({"role": "user", "content": text})
    new_state["messages"] = messages
    return new_state


def get_message_role(msg) -> str:
    if isinstance(msg, dict):
        return msg.get("role", "unknown")
    return getattr(msg, "type", "unknown")


def get_message_content(msg) -> str:
    if isinstance(msg, dict):
        return msg.get("content", "") or ""
    return getattr(msg, "content", "") or ""


def get_last_user_text(state: dict) -> str:
    for msg in reversed(state.get("messages", [])):
        role = get_message_role(msg)
        if role in ("user", "human"):
            return get_message_content(msg)
    return ""


def make_tool_message(name: str, result: dict) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(result, ensure_ascii=False, default=str),
        name=name,
        tool_call_id=str(uuid.uuid4()),
    )


def make_ai_message(text: str) -> AIMessage:
    return AIMessage(content=text)