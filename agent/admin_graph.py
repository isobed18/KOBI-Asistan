"""
Admin Agent Graph — İşletmeci için LLM ajanı
=============================================
Müşteri scope kısıtlaması yok. Stok, sipariş, ürün, bilet yazma araçları var.
"""

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage

from agent.graph import _create_llm
from agent.tenant_context import get_tenant_id
from agent.tenant_config import tenant_prompt_block
from tools.order_product_tools import (
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
    siparis_sorgula,
    create_ticket,
)
from tools.kargo_tools import kargo_takip
from tools.admin_tools import ADMIN_TOOLS

ADMIN_SYSTEM_PROMPT = """Sen KOBİ Asistan'ın işletme yönetim asistanısın. İşletme sahibi seninle konuşuyor.

Yapabileceklerin:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 STOK
• admin_stok_guncelle       — tek ürün stok girişi/çıkışı
• admin_toplu_stok_guncelle — birden fazla ürünü tek seferde güncelle
• admin_urun_ekle           — sisteme yeni ürün ekle
• urun_stok_kontrol         — stok durumu sorgula
• kritik_stok_listesi       — kritik stokta olan ürünler

🚚 SİPARİŞ & KARGO
• admin_siparis_guncelle        — sipariş durumu güncelle, kargo kodu ata
• admin_toplu_siparis_guncelle  — toplu sipariş güncelleme
• siparis_sorgula               — sipariş detayı sorgula
• kargo_takip                   — kargo durumu sorgula

🎫 BİLET
• admin_bilet_guncelle — bilet durumu güncelle, çözüm notu ekle
• create_ticket        — yeni bilet aç

📊 RAPORLAMA
• gunluk_ozet — günlük iş özeti
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Çalışma kuralları:
- Doğal dil komutlarını anlayıp hemen uygun tool'u çağır
- Toplu işlem istendiğinde toplu tool kullan (admin_toplu_*)
- 'zeytinyağı 50, domates 30 girişi yap' → admin_toplu_stok_guncelle
- '5, 7, 12. siparişleri kargoya verdim, hepsi Aras' → admin_toplu_siparis_guncelle
- Sonuçları kısa, madde madde özetle
- Hata durumunda açıklayıcı mesaj ver
- Türkçe yanıt ver
"""

# Tüm tool listesi: read-only customer tools + admin write tools
ALL_ADMIN_TOOLS = [
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
    siparis_sorgula,
    kargo_takip,
    create_ticket,
    *ADMIN_TOOLS,
]

# -- LLM & Graph Build --
_admin_llm = _create_llm(temperature=0.1)
_admin_llm_with_tools = _admin_llm.bind_tools(ALL_ADMIN_TOOLS)


def _admin_agent_node(state: MessagesState):
    tenant_block = tenant_prompt_block(get_tenant_id())
    system = SystemMessage(content=f"{ADMIN_SYSTEM_PROMPT}\n\nTENANT CONFIG:\n{tenant_block}")
    messages = [system] + state["messages"]
    response = _admin_llm_with_tools.invoke(messages)
    return {"messages": [response]}


def build_admin_graph():
    graph = StateGraph(MessagesState)
    graph.add_node("agent", _admin_agent_node)
    graph.add_node("tools", ToolNode(ALL_ADMIN_TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


admin_graph = build_admin_graph()
