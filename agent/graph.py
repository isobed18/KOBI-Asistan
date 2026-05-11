"""
KOBI Asistan — LangGraph Agent (Auth-Aware)
=============================================
"""

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage

from agent.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_AUTHENTICATED
from agent.auth import get_active_scope
from tools.order_product_tools import (
    siparis_sorgula,
    musteri_siparisleri,
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
    create_ticket,
)
from tools.kargo_tools import kargo_takip
from config import settings


def _create_llm(temperature: float = 0.1):
    """Provider-bağımsız LLM factory. LLM_PROVIDER env değişkeniyle kontrol edilir."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=temperature,
            api_key=settings.OPENAI_API_KEY,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.ANTHROPIC_MODEL,
            temperature=temperature,
            api_key=settings.ANTHROPIC_API_KEY,
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            temperature=temperature,
            google_api_key=settings.GEMINI_API_KEY,
        )
    else:  # ollama (default)
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
        )


# -- Tool listesi --
ALL_TOOLS = [
    siparis_sorgula,
    musteri_siparisleri,
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
    kargo_takip,
    create_ticket,
]

# -- LLM --
llm = _create_llm()
llm_with_tools = llm.bind_tools(ALL_TOOLS)


# -- Graph Nodes --
def agent_node(state: MessagesState):
    """LLM'e mesajları gönderir, tool call veya final yanıt döner."""
    scope = get_active_scope()

    if scope and (scope.get("telefon") or scope.get("takip_kodu")):
        auth_info = ""
        if scope.get("telefon"):
            auth_info = f"Müşteri telefonu {scope['telefon']} ile doğrulandı. Sadece bu numaraya ait siparişler sorgulanabilir."
        elif scope.get("takip_kodu"):
            auth_info = f"Takip kodu {scope['takip_kodu']} ile doğrulandı. Sadece bu siparişe erişim var."
        system_content = SYSTEM_PROMPT_AUTHENTICATED.format(auth_info=auth_info)
    else:
        system_content = SYSTEM_PROMPT

    system = SystemMessage(content=system_content)
    messages = [system] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# -- Graph Build --
def build_agent_graph():
    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


agent_graph = build_agent_graph()
