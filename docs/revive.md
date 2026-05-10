# AI Agent Onboarding Guide (Revive.md)

**Welcome, AI Code Agent.** 
This document is designed to rapidly onboard you into the "KOBI Asistan" (SME Assistant) project. Read this first to understand the context, architecture, current state, and immediate goals.

---

## 1. Project Objective
The core objective is to transition from a manual, spreadsheet-based process to an **automated, AI-first architecture** using LangGraph and FastAPI. 
We are building an agentic management system for SMEs (KOBIs) to handle order tracking, stock control, and daily summaries automatically. The priority is **agent autonomy, tool usage accuracy, and deep automation**, rather than building complex underlying mock data systems.

## 2. Current State (v3.0)
The project has moved past the prototype phase and currently features a functional, secure, and scheduled agent system.

*   **Multi-Provider LLM Support**: Supports Ollama (local), OpenAI, Gemini, and Claude via lazy loading in a factory function. Controlled by `LLM_PROVIDER` in `.env`.
*   **Code-Level Authentication**: Secure, `contextvars`-based async-safe session scoping. 
    *   Auth happens at the router level (Phone Number or Tracking Code).
    *   Tools read this scope and enforce SQL filters. **The LLM cannot bypass data access restrictions.**
*   **Prompt Police (Guardrails)**: A 3-layer, zero-latency regex-based guard mechanism (`guard.py`) preventing prompt injection, blocking technical/off-topic requests, and enforcing domain relevance.
*   **Background Jobs**: APScheduler runs 3 tasks: Morning reports (08:00), stock alarms (every 2h), and cargo delay checks (every 4h).
*   **Interfaces**: Web Chat UI (SSE streaming) and Telegram Bot. Both are auth-aware.

## 3. Key Files to Review (Start Here)
To understand the system quickly, inspect these files in order:

1.  `agent/graph.py`: The core LangGraph state machine. Shows the system prompt binding and the multi-provider LLM factory.
2.  `agent/auth.py`: The `contextvars` implementation for session scoping. Crucial for understanding how we isolate customer data.
3.  `agent/guard.py`: The 3-layer Prompt Police implementation.
4.  `tools/order_product_tools.py`: Observe how tools utilize `get_active_scope()` from `auth.py` to filter database queries securely.
5.  `config.py` & `.env.example`: Configuration and supported environment variables.
6.  `docs/RESEARCH.md`: Contains our analysis on NeMo Guardrails and open-source architecture inspirations (highly recommended for future architectural decisions).

## 4. Current Concerns & Next Priorities

As you begin your tasks, keep these primary concerns in mind. Our next major phase focuses on **Cost Reduction and Latency Optimization**.

*   **Concern 1: High Latency / Cost on Simple Queries**
    *   *Issue*: Currently, every message goes through the full LangGraph/LLM flow. A simple "Where is my order?" takes too long and costs too much.
    *   *Target*: Implement an **Intent Classifier** (regex or lightweight model) before the LLM. If the intent is clear (e.g., `siparis_durumu`), bypass the LLM, call the tool directly, and format the output via a template.
*   **Concern 2: Handling FAQ / RAG**
    *   *Issue*: General questions consume expensive LLM tokens.
    *   *Target*: Integrate a RAG system or a local lightweight model (e.g., Qwen 1.5B/7B) to answer FAQs instantly without invoking the heavy LangGraph reasoning loop.
*   **Concern 3: Multi-Tenant Architecture**
    *   *Issue*: The current SQLite DB and configuration are for a single business.
    *   *Target*: Refactor towards a multi-tenant setup (YAML configs per tenant) as researched in `yerdaulet-damir/langgraph-sales-agent`.
*   **Concern 4: Advanced Guardrails**
    *   *Issue*: Regex Prompt Police is fast but limited.
    *   *Target*: We evaluated NVIDIA NeMo Guardrails. It works offline with Ollama but adds ~500ms latency per check. We decided to defer it. Future tasks might involve adding it *only* as an Output Rail (hallucination check).

## 5. Development Guidelines
*   **Preserve the Scope**: When adding new tools that touch the DB, you MUST implement `get_active_scope()` checks to maintain security.
*   **No Generic LLMs**: Do not hardcode OpenAI or Ollama. Always use the `_create_llm()` factory in `agent/graph.py`.
*   **Focus on the Agent**: Don't spend time building complex mock APIs for shipping/stock. Keep them simple SQLite queries. Focus on *how the agent interacts* with them.

---
*End of Onboarding. Acknowledge this context before starting new development tasks.*
