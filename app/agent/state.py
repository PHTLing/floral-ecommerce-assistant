from typing import TypedDict, List


class AgentState(TypedDict, total=False):
    messages:  List[dict]
    current_intent: str      
    selected_flower: dict     
    search_results: list
    search_context: dict  
    recommended_results: list  
    customer_info: dict     
    pending_missing_fields: list  
    last_tool: str     
    tool_retry_count: int

def create_initial_state() -> AgentState:
    return {
        "messages": [],
        "current_intent": "",
        "selected_flower": None,
        "search_results": [],
        "search_context": {},
        "recommended_results": [],
        "customer_info": {},
        "pending_missing_fields": [],
        "last_tool": "",
        "tool_retry_count": 0,
    }