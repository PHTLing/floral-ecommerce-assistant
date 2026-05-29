# 🌸 FloraConsult - Hybrid Agentic RAG Flower Assistant

**FloraConsult** is an AI-powered flower consultation assistant for e-commerce. The system combines **RAG**, **LangGraph-based workflow orchestration**, and structured business logic to support product search, product Q&A, recommendations, and order-oriented user flows.

The project focuses on building a practical conversational AI system that can understand customer needs, retrieve relevant flower products, answer product-specific questions, and guide users through a controlled checkout flow.

---

## ✨ Key Features

- **Context-aware flower consultation** based on occasion, recipient, color, style, and budget.
- **Semantic product retrieval** using vector search over metadata-rich flower documents.
- **Product detail Q&A** with support for follow-up references such as “this product”, “that one”, or “the second item”.
- **Stateful checkout flow** for collecting customer information, delivery details, quantity, and selected products.
- **Multi-item order handling** using a unified `items[]` structure.
- **Order review and confirmation flow** before saving the final order.
- **Fallback and handoff response** for unsupported requests or issues requiring human support.
- **React chat UI** with product cards, Markdown rendering, new-tab product links, and chat reset support.

---

## 🧠 System Architecture

FloraConsult is designed as a **Hybrid Agentic RAG System** rather than a simple chatbot.

The assistant uses **LangGraph** to manage a stateful workflow across different nodes:

- `search_node` - retrieves and recommends relevant flower products.
- `detail_node` - answers product-specific questions and resolves product references.
- `checkout_node` - manages order extraction, multi-item order drafts, confirmation, and correction.
- `smalltalk_node` - handles greetings, shop introduction, and common FAQ-style questions.
- `fallback_node` - handles unsupported requests and suggests human support.

This design separates **LLM reasoning**, **retrieval**, and **business rules**, making the system easier to debug, extend, and control.

---

## 🔍 RAG & Retrieval Pipeline

Product data is scraped, cleaned, transformed, and stored as structured JSON documents. Each document contains product attributes such as name, price, image, URL, description, flower components, style, color, and use case.

The retrieval pipeline includes:

- Text preprocessing and product metadata normalization.
- Sentence embedding generation with **Sentence-Transformers**.
- Vector storage and semantic search with **ChromaDB**.
- Rule-based filters for price, color, style, and flower type.
- LLM-assisted result selection to recommend the most relevant products.

---

## 🛒 Checkout Flow

The checkout flow is implemented as a controlled stateful workflow instead of directly relying on free-form LLM output.

Main capabilities:

- Extract customer name, phone number, address, delivery date, delivery time, quantity, and selected products.
- Normalize Vietnamese date and time expressions.
- Support references such as “I want this one” or “add one more of this product”.
- Maintain orders using a unified multi-item structure:

```json
{
  "items": [
    { "loai_hang": "Dreaming - 12595", "so_luong": "1" },
    { "loai_hang": "Just for you - 15278", "so_luong": "1" }
  ]
}
```

- Ask for missing information before order confirmation.
- Show an order review message before saving the final order.
- Allow users to correct information before confirming.

---

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | React, Tailwind CSS, ReactMarkdown, Framer Motion, Lucide Icons |
| Backend | FastAPI, Python, LangGraph |
| LLM | Qwen via Ollama, Gemini-ready prompt layer |
| Retrieval | ChromaDB, Sentence-Transformers |
| Data Processing | Python scraping, cleaning, JSON transformation |
| Storage | JSON-based product and order storage for MVP |

---

## 📂 Project Structure

```plaintext
Floral_chatbot/
├── app/
│   ├── agent/              # LangGraph workflow, nodes, router, response builders
│   ├── extractors/         # Intent, order, confirmation, and product reference extraction
│   ├── services/           # Search, detail, and order business services
│   ├── repositories/       # JSON-based product/order persistence
│   ├── utils/              # Date-time, text, message, and order item utilities
│   └── main.py             # FastAPI entrypoint
├── floral-frontend/        # React chat interface
├── build_db.py             # Vector database build script
├── requirements.txt
└── README.md
```

---

## 🚀 Getting Started

### Backend

```bash
cd Floral_chatbot
python -m venv env
source env/Scripts/activate   # Windows: env\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload #You must have data folder
```

### Frontend

```bash
cd floral-frontend
npm install
npm start
```

---

## ✨ Demo
[📄 File demo ](./docs/Demo.pdf)
---

## 🎯 Project Highlights

- Built a **LangGraph-based Hybrid Agentic RAG assistant** for e-commerce flower consultation and transaction-oriented flows.
- Designed a **stateful intent routing workflow** across search, product detail, checkout, smalltalk, and fallback nodes.
- Implemented a **semantic retrieval engine** using Sentence-Transformers and ChromaDB over metadata-rich product documents.
- Developed **context-aware product reference resolution** for follow-up questions like “this product” or “the second item”.
- Built a **controlled multi-item checkout pipeline** with information extraction, validation, order review, correction, and confirmation.
- Created a React-based chat interface with product cards, Markdown responses, and new-tab product navigation.

---

## ⚖️ Disclaimer

This project is developed for **educational and personal research purposes only**. Product data and images are collected from publicly available sources for demonstration of RAG and conversational AI in an e-commerce setting.
