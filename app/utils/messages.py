# app/utils/messages.py

from __future__ import annotations

from typing import Any


def get_message_role(message: Any) -> str:
    """
    Lấy role/type từ message dict hoặc LangChain message.
    """
    if isinstance(message, dict):
        return message.get("role", "unknown")

    return getattr(message, "type", "unknown")


def get_message_content(message: Any) -> str:
    """
    Lấy content từ message dict hoặc LangChain message.
    """
    if isinstance(message, dict):
        return str(message.get("content", "") or "")

    return str(getattr(message, "content", "") or "")


def is_user_message(message: Any) -> bool:
    role = get_message_role(message)
    return role in ["user", "human"]


def get_last_user_text(state: dict[str, Any]) -> str:
    """
    Lấy nội dung tin nhắn user gần nhất từ state.
    """
    for message in reversed(state.get("messages", [])):
        if is_user_message(message):
            return get_message_content(message)

    return ""


def format_recent_history(
    messages: list[Any],
    max_messages: int = 6,
    max_tool_chars: int = 500,
) -> str:
    """
    Format một phần lịch sử gần nhất cho prompt.
    Không nhét toàn bộ history để tránh quá context.
    """
    recent = messages[-max_messages:]
    lines: list[str] = []

    for message in recent:
        role = get_message_role(message)
        content = get_message_content(message)

        if role == "tool" and len(content) > max_tool_chars:
            content = content[:max_tool_chars] + "\n... [KẾT QUẢ TOOL ĐÃ RÚT GỌN]"

        lines.append(f"[{role.upper()}]: {content}")

    return "\n".join(lines)