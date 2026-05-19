from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel


from app.agent.graph import app as agent_graph
from app.agent.message_utils import append_user_message
from app.agent.response_builder import extract_frontend_data, get_last_ai_text

import logging
import json

app = FastAPI(title="FloraConsult Agentic API")

# Middleware CORS giữ nguyên
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bộ nhớ session (Sẽ lưu trữ State của LangGraph)
sessions_data = {}

class ChatRequest(BaseModel):
    user_input: str
    session_id: str


@app.post("/chat")
async def chat(request: ChatRequest):
    query = request.user_input
    sid = request.session_id
    
    # 1. Khởi tạo session nếu chưa có
    if sid not in sessions_data:
        sessions_data[sid] = {
            "messages": [],
            "search_context": {},
            "search_results": [],
            "selected_flower": None,
            "customer_info": {},
            "pending_missing_fields": [],
        }
    
    current_state = sessions_data[sid]
    current_state = append_user_message(current_state, query)
    
    final_state = agent_graph.invoke(current_state)

    # 4. Cập nhật lại bộ nhớ session
    sessions_data[sid] = final_state

    return {
        "reply": get_last_ai_text(final_state),
        "data": extract_frontend_data(final_state),
    }

    