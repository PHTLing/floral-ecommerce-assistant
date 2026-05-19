from langgraph.graph import StateGraph, START

from app.agent.state import AgentState
from app.agent.router import intent_classifier, route_by_intent
from app.agent.nodes import (
    search_node,
    detail_node,
    checkout_node,
    smalltalk_node,
    fallback_node,
)

workflow = StateGraph(AgentState)

# Thêm các node
workflow.add_node("intent_classifier", intent_classifier)
workflow.add_node("search_flower", search_node)
workflow.add_node("flower_detail", detail_node)
workflow.add_node("checkout", checkout_node)
workflow.add_node("smalltalk", smalltalk_node)
workflow.add_node("fallback", fallback_node)

# Cạnh từ START
workflow.add_edge(START, "intent_classifier")

# Định tuyến từ intent_classifier
workflow.add_conditional_edges(
    "intent_classifier",
    route_by_intent,
    {
        "search_flower": "search_flower",
        "flower_detail": "flower_detail",
        "checkout": "checkout",
        "smalltalk": "smalltalk",
        "fallback": "fallback"
    }
)

app = workflow.compile()