"""
Admin LangGraph agent for the business owner.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent.graph import _create_llm
from agent.tenant_config import get_tenant_by_id, tenant_prompt_block
from agent.tenant_context import get_tenant_id
from tools.admin_tools import ADMIN_TOOLS
from tools.kargo_tools import kargo_takip
from tools.order_product_tools import (
    create_ticket,
    gunluk_ozet,
    kritik_stok_listesi,
    siparis_sorgula,
    urun_stok_kontrol,
)


ADMIN_SYSTEM_PROMPT = """Sen KOBI Asistan'in isletme yonetim asistanisin.

Amacin klasik panel gibi davranmak degil; isletmeciye sadece kritik kararlari
net, sakin ve aksiyon odakli sunmak.

Yapabileceklerin:
- **Tum urun/stok listesi** (admin_urun_listesi): filtre veya arama ile aktif urunler
- Stok degisikligi: **once** admin_stok_onay_iste veya admin_stok_toplu_onay_iste; kullanici onayladiktan sonra admin_pending_uygula(onay_token)
- Siparis/kargo: listeleme admin_siparis_listesi; guncelleme **once** admin_siparis_onay_iste / admin_siparis_toplu_onay_iste, sonra admin_pending_uygula
- Siparis silme (hazirlaniyor/kargoda): admin_siparis_sil_onay_iste, sonra admin_pending_uygula
- Urun ekleme/duzenleme/silme: admin_urun_ekle_onay_iste, admin_urun_duzenle_onay_iste, admin_urun_sil_onay_iste; sonra admin_pending_uygula
- Kritik stok, gunluk ozet, kargo ve tekil siparis sorgulama (siparis_sorgula)
- Acik biletleri listeleme (admin_bilet_listesi) ve bilet guncelleme (admin_bilet_guncelle)

Kurallar:
- Veritabanina yazan hicbir islemi **dogrudan** uygulama; mutlaka ilgili *_onay_iste aracini cagir. Onay ciktisindaki ozeti kullaniciya goster.
- Kullanici sozlu onay verirse (evet/onayliyorum) **ayni oturumda** admin_pending_uygula ile tokeni uygula; tokeni onceki arac ciktisindan al.
- Listeleme isteklerinde ilgili listeleme aracini cagir; reddetme.
- Stok guncellemede urun adini fuzzy arama ile bul; emin degilsen onerileri listele.
- Sonuclari kisa, guven veren ve karar odakli ozetle.
- Turkce yanit ver.
"""


ALL_ADMIN_TOOLS = [
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
    siparis_sorgula,
    kargo_takip,
    create_ticket,
    *ADMIN_TOOLS,
]


def _admin_agent_node(state: MessagesState):
    tenant_id = int(get_tenant_id() or 1)
    tenant_cfg = get_tenant_by_id(tenant_id)
    model = _create_llm(
        temperature=tenant_cfg.llm.temperature,
        provider=tenant_cfg.llm.provider,
        model=tenant_cfg.llm.model,
    ).bind_tools(ALL_ADMIN_TOOLS)
    system = SystemMessage(
        content=f"{ADMIN_SYSTEM_PROMPT}\n\nTENANT CONFIG:\n{tenant_prompt_block(tenant_id)}"
    )
    response = model.invoke([system] + state["messages"])
    return {"messages": [response]}


def build_admin_graph():
    graph = StateGraph(MessagesState)
    graph.add_node("agent", _admin_agent_node)
    graph.add_node("tools", ToolNode(ALL_ADMIN_TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


admin_graph = build_admin_graph()
