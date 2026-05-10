"""
KOBI Asistan — LangGraph Agent (Auth-Aware)
=============================================
"""

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage

from agent.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_AUTHENTICATED
from agent.auth import get_active_scope
from tools.order_product_tools import (
    siparis_sorgula,
    musteri_siparisleri,
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
)
from tools.kargo_tools import kargo_takip
from config import settings

# -- Tool listesi --
ALL_TOOLS = [
    siparis_sorgula,
    musteri_siparisleri,
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
    kargo_takip,
]

# -- LLM --
llm = ChatOllama(
    model=settings.OLLAMA_MODEL,
    base_url=settings.OLLAMA_BASE_URL,
    temperature=0.1,
)
llm_with_tools = llm.bind_tools(ALL_TOOLS)


# -- Graph Nodes --
def agent_node(state: MessagesState):
    """LLM'e mesajlari gonderir, tool call veya final yanit doner."""
    # Scope'a gore system prompt sec
    scope = get_active_scope()

    if scope and (scope.get("telefon") or scope.get("takip_kodu")):
        auth_info = ""
        if scope.get("telefon"):
            auth_info = f"Musteri telefonu {scope['telefon']} ile dogrulandi. Sadece bu numaraya ait siparisler sorgulanabilir."
        elif scope.get("takip_kodu"):
            auth_info = f"Takip kodu {scope['takip_kodu']} ile dogrulandi. Sadece bu siparise erisim var."
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
