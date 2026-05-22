from typing import TypedDict, List


class AgentState(TypedDict, total=False):
    messages:  List[dict]
    current_intent: str    

    selected_flower: dict     
    search_results: list
    search_context: dict  
    recommended_results: list  
    last_referenced_flower: dict

    order_draft: dict
    pending_order_confirmation: bool

    customer_info: dict     
    pending_missing_fields: list  

    handoff_requested: bool
    handoff_reason: str

    last_tool: str     
    tool_retry_count: int

def create_initial_state() -> AgentState:
    return {
        "messages": [],
        "current_intent": "",
        "selected_flower": None,
        "search_results": [],
        "search_context": {},
        "order_draft": {},
        "pending_order_confirmation": False,    
        "recommended_results": [],
        "last_referenced_flower": None,
        "customer_info": {},
        "pending_missing_fields": [],
        "handoff_requested": False,
        "handoff_reason": "",
        "last_tool": "",
        "tool_retry_count": 0,
    }