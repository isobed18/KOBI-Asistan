"""
KOBI Asistan — LangGraph Agent (Auth-Aware, Multi-Provider)
=============================================================
Desteklenen LLM'ler:
  - Ollama (local) → langchain-ollama
  - OpenAI         → langchain-openai
  - Google Gemini  → langchain-google-genai
  - Anthropic      → langchain-anthropic
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


def _create_llm():
    """
    LLM_PROVIDER'a gore uygun LLM instance'i olusturur.
    .env dosyasinda LLM_PROVIDER degiskenini ayarlayin:
      - "ollama"  → Local Ollama (varsayilan, API key gereksiz)
      - "openai"  → OpenAI API (OPENAI_API_KEY gerekli)
      - "gemini"  → Google Gemini (GOOGLE_API_KEY gerekli)
      - "claude"  → Anthropic Claude (ANTHROPIC_API_KEY gerekli)
    """
    provider = settings.LLM_PROVIDER.lower().strip()

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY .env dosyasinda tanimli degil!")
        from langchain_openai import ChatOpenAI
        print(f"[LLM] OpenAI: {settings.OPENAI_MODEL}")
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.1,
        )

    elif provider == "gemini":
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY .env dosyasinda tanimli degil!")
        from langchain_google_genai import ChatGoogleGenerativeAI
        print(f"[LLM] Google Gemini: {settings.GEMINI_MODEL}")
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1,
        )

    elif provider == "claude":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY .env dosyasinda tanimli degil!")
        from langchain_anthropic import ChatAnthropic
        print(f"[LLM] Anthropic Claude: {settings.CLAUDE_MODEL}")
        return ChatAnthropic(
            model=settings.CLAUDE_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.1,
        )

    else:
        # Default: Ollama (local, ucretsiz)
        from langchain_ollama import ChatOllama
        print(f"[LLM] Ollama (local): {settings.OLLAMA_MODEL} @ {settings.OLLAMA_BASE_URL}")
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0.1,
        )


# -- LLM --
llm = _create_llm()
llm_with_tools = llm.bind_tools(ALL_TOOLS)


# -- Graph Nodes --
def agent_node(state: MessagesState):
    """LLM'e mesajlari gonderir, tool call veya final yanit doner."""
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
