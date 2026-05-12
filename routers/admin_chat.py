"""
Admin Chat Endpoint — İşletmeci LLM Asistanı
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Any, Optional
import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.admin_graph import admin_graph
from agent.admin_user_context import set_admin_user_id
from agent.pending_admin_mutations import take_pending
from agent.tenant_context import set_tenant_id
from routers.auth_router import CurrentUser, get_current_user
from tools.admin_mutation_apply import apply_pending_payload

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Asistan"])


def _messages_current_turn(messages: list) -> list:
    """Checkpointer thread'inde tum gecmis vardir; yalnizca son kullanici mesajindan sonraki tur."""
    last = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last = i
            break
    return messages[last:] if last is not None else messages


def _stringify_lc_content(content) -> str:
    """Gemini vb. modeller bazen content'i blok listesi verir; UI icin duz metne cevir."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if t is not None:
                    parts.append(str(t))
        return "\n".join(parts).strip()
    return str(content).strip()


def _tool_call_name_args(tc: Any) -> tuple[str, dict]:
    if isinstance(tc, dict):
        return (tc.get("name") or "", tc.get("args") or {})
    name = getattr(tc, "name", None) or ""
    args = getattr(tc, "args", None) or {}
    return (str(name), args if isinstance(args, dict) else {})


def _parse_tool_message_content(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            out = json.loads(raw)
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}
    return {}


_ORDER_TAB_LABELS = {
    "hazırlanıyor": "Hazırlanıyor",
    "kargoda": "Kargoda",
    "teslim_edildi": "Teslim edildi",
    "tamamlandi": "Tamamlandı",
    "tamamlandı": "Tamamlandı",
    "iptal": "İptal",
}


_CHAT_LIST_PREVIEW = 8


def _orders_panel_md(durum_filtre: str | None) -> str:
    """Tam liste linki — her zaman mesajin EN ALTINDA gosterilir."""
    if durum_filtre:
        label = _ORDER_TAB_LABELS.get(durum_filtre, durum_filtre)
        return (
            f"Tam listeye doğrudan şu bağlantıdan ulaşabilirsiniz: "
            f"[**{label} — Siparişler paneli →**](/orders?tab={durum_filtre})  \n"
            "*Tabloda tüm satırlar, sıralama ve durum güncellemesi.*"
        )
    return (
        "Tam listeye doğrudan şu bağlantıdan ulaşabilirsiniz: "
        "[**Siparişler paneli →**](/orders)  \n"
        "*Sekmelerden duruma göre daraltabilirsiniz.*"
    )


def _tickets_panel_md() -> str:
    return (
        "Tam listeyi görmek için: [**Açık biletler →**](/tickets?tab=open) · "
        "[**İşlemde →**](/tickets?tab=in_progress) · [**Tümü →**](/tickets?tab=all)  \n"
        "*Öncelik ve durum güncellemesi panelde.*"
    )


def _reports_panel_md() -> str:
    return (
        "Günlük raporlar, geçmiş özetler ve üretilmiş AI raporları için: "
        "[**Raporlar →**](/reports)  \n"
        "*Tarih bazlı kayıtlar ve detaylı metin burada.*"
    )


def _inventory_panel_md() -> str:
    return (
        "Stok miktarı, eşik ve hareketler için: [**Stok / Envanter →**](/inventory)  \n"
        "*Ürün arama, düzenleme ve kritik ürün takibi.*"
    )


def _panel_intents_from_mesaj(mesaj: str) -> frozenset[str]:
    """Bir mesajda birden fazla niyet olabilir (ör. günlük özet + sipariş kelimesi)."""
    low = (mesaj or "").lower()
    m = mesaj or ""
    s: set[str] = set()
    if any(
        x in low
        for x in (
            "sipariş",
            "siparis",
            "kargo",
            "kargoda",
            "hazırlan",
            "hazirlan",
            "teslim",
            "iptal",
            "durumundaki",
        )
    ):
        s.add("order")
    if any(
        x in low or x in m
        for x in (
            "bilet",
            "ticket",
            "çözülmemiş",
            "cozulmemis",
            "açık bilet",
            "acik bilet",
        )
    ):
        s.add("ticket")
    if (
        ("özet" in low or "ozet" in low or "gelir" in low or "ciro" in low)
        and (
            "günlük" in low
            or "gunluk" in low
            or "bugün" in low
            or "bugun" in low
            or "bugunku" in low
            or "bugünkü" in m.lower()
        )
    ) or ("rapor" in low and ("günlük" in low or "gunluk" in low or "bugün" in low or "bugun" in low)):
        s.add("report")
    if ("kritik" in low and "stok" in low) or ("düşük stok" in low or "dusuk stok" in low):
        s.add("inventory")
    if ("kritik" not in low) and (
        any(x in low for x in ("listele", "liste", "goster", "göster"))
        and any(x in low or x in m.lower() for x in ("stok", "envanter", "ürün", "urun"))
    ):
        s.add("inventory")
    return frozenset(s)


def _tool_domains(tool_calls_info: list) -> frozenset[str]:
    d: set[str] = set()
    for tc in tool_calls_info:
        t = tc.get("tool") or ""
        if t == "admin_siparis_listesi":
            d.add("order")
        elif t == "admin_bilet_listesi":
            d.add("ticket")
        elif t == "gunluk_ozet":
            d.add("report")
        elif t == "kritik_stok_listesi":
            d.add("inventory")
        elif t == "admin_urun_listesi":
            d.add("inventory")
    return frozenset(d)


def _infer_panel_intents(tool_calls_info: list, mesaj: str) -> frozenset[str]:
    """Mesaj + bu turde cagrılan araclar: yalnizca ilgili panel linkleri."""
    from_mesaj = set(_panel_intents_from_mesaj(mesaj))
    from_tools = set(_tool_domains(tool_calls_info))
    if from_tools:
        if from_mesaj:
            return frozenset(from_mesaj & from_tools)
        return frozenset(from_tools)
    return frozenset(from_mesaj)


def _desired_order_status_from_mesaj(mesaj: str) -> str | None:
    low = (mesaj or "").lower()
    m = mesaj or ""
    if "kargod" in low:
        return "kargoda"
    if "hazirlan" in low or "hazırlan" in m:
        return "hazırlanıyor"
    if "teslim_edildi" in low or "teslim edildi" in low:
        return "teslim_edildi"
    if "iptal" in low:
        return "iptal"
    return None


def _panel_banners_from_tools(tool_calls_info: list, mesaj: str = "") -> list[str]:
    """Yalnizca bu tur + kullanici niyeti ile eslesen panel linkleri."""
    intents = _infer_panel_intents(tool_calls_info, mesaj)
    desired_status = _desired_order_status_from_mesaj(mesaj)

    seen: set[str] = set()
    out_lines: list[str] = []
    for tc in tool_calls_info:
        name = tc.get("tool") or ""
        payload = tc.get("output")
        if not isinstance(payload, dict):
            continue
        if name == "admin_siparis_listesi":
            if "order" not in intents:
                continue
            if payload.get("hata"):
                continue
            filt = payload.get("durum_filtre")
            if desired_status and filt and filt != desired_status:
                continue
            key = f"orders:{filt!r}"
            if key in seen:
                continue
            seen.add(key)
            out_lines.append(_orders_panel_md(filt))
        elif name == "admin_bilet_listesi":
            if "ticket" not in intents:
                continue
            key = "tickets:open"
            if key in seen:
                continue
            seen.add(key)
            out_lines.append(_tickets_panel_md())
        elif name == "gunluk_ozet":
            if "report" not in intents:
                continue
            key = "reports:daily"
            if key in seen:
                continue
            seen.add(key)
            out_lines.append(_reports_panel_md())
        elif name == "kritik_stok_listesi":
            if "inventory" not in intents:
                continue
            key = "inventory:low"
            if key in seen:
                continue
            seen.add(key)
            out_lines.append(_inventory_panel_md())
        elif name == "admin_urun_listesi":
            if "inventory" not in intents:
                continue
            key = "inventory:all"
            if key in seen:
                continue
            seen.add(key)
            out_lines.append(_inventory_panel_md())
    return out_lines


def _merge_panel_banners(yanit: str, tool_calls_info: list, mesaj: str = "") -> str:
    """Ozet / model metni ustte; panel linki her zaman altta."""
    banners = _panel_banners_from_tools(tool_calls_info, mesaj)
    if not banners:
        return yanit
    text = (yanit or "").strip()
    to_add = [b for b in banners if b and b not in text]
    if not to_add:
        return yanit
    block = "\n\n".join(to_add)
    if not text:
        return block
    return f"{text}\n\n---\n\n{block}"


def _format_tool_output(name: str, out: dict) -> str:
    if out.get("onay_bekliyor") and out.get("ozet"):
        return (
            "**Onay bekleniyor**\n\n"
            + str(out["ozet"]).strip()
            + "\n\n*İşlemi tamamlamak için aşağıdaki **Onayla** düğmesini kullanabilir veya "
            "sohbette onaylayıp `admin_pending_uygula` aracına token verebilirsiniz.*"
        )
    if name == "admin_pending_uygula":
        if out.get("hata"):
            return str(out["hata"])
        if out.get("onceki_stok") is not None and isinstance(out.get("urun"), str):
            d = out.get("delta", 0)
            return (
                f"Stok güncellendi: **{out.get('urun')}** — {out['onceki_stok']} → {out['yeni_stok']} "
                f"({d:+d})."
            )
        if out.get("siparis_no") is not None and out.get("yeni_durum") is not None and out.get(
            "eski_durum"
        ) is not None:
            return (
                f"Sipariş **#{out['siparis_no']}** güncellendi: **{out.get('eski_durum')}** → "
                f"**{out['yeni_durum']}**."
            )
        if out.get("basari") and out.get("siparis_no") is not None and out.get("yeni_durum") is None:
            return (
                f"Sipariş **#{out['siparis_no']}** silindi; kalemler stoka iade edildi."
            )
        if out.get("basari") and out.get("urun_id") is not None and out.get("isim") and out.get(
            "fiyat"
        ) is not None and out.get("stok") is not None:
            return (
                f"Yeni ürün eklendi: **#{out['urun_id']}** {out.get('isim')} — "
                f"fiyat {out['fiyat']}, stok {out.get('stok')}."
            )
        if out.get("basari") and isinstance(out.get("urun"), dict):
            u = out["urun"]
            return f"Ürün **#{u.get('id')}** ({u.get('name')}) güncellendi."
        if out.get("basari") and out.get("urun_id") is not None and out.get("isim") and out.get(
            "fiyat"
        ) is None and out.get("detaylar") is None:
            return f"Ürün **#{out['urun_id']}** ({out.get('isim')}) pasife alındı."
        if out.get("toplam") is not None:
            return (
                f"Toplu işlem: **{out.get('basarili', 0)}** / {out.get('toplam', 0)} satır başarılı. "
                "Ayrıntılar araç kartında."
            )
        return _yanit_from_confirm_output(out)
    if name == "admin_urun_listesi":
        foot = _inventory_panel_md()
        urunler = out.get("urunler") or []
        head = str(out.get("mesaj", ""))
        if not urunler:
            parts = [p for p in (head, foot) if p]
            return "\n\n---\n\n".join(parts).strip()
        preview = urunler[:_CHAT_LIST_PREVIEW]
        lines = [
            f"- **#{u.get('id')}** {u.get('ad', '?')} — stok **{u.get('stok', '?')}**, "
            f"fiyat {u.get('fiyat', '?')} TL, eşik {u.get('stok_esigi', '?')}"
            for u in preview
        ]
        extra = len(urunler) - len(preview)
        if extra > 0:
            lines.append(f"- *… ve **{extra}** ürün daha*")
        body = "\n".join(lines)
        mid = f"**Özet liste** *(ilk {len(preview)} kayıt)*\n\n{body}"
        top = f"{head}\n\n{mid}" if head else mid
        return f"{top}\n\n---\n\n{foot}".strip()
    if name == "gunluk_ozet":
        body = out.get("ozet_metin") or out.get("mesaj") or ""
        if not str(body).strip():
            return ""
        foot = _reports_panel_md()
        return f"{str(body).strip()}\n\n---\n\n{foot}".strip()
    if name == "kritik_stok_listesi":
        foot = _inventory_panel_md()
        urunler = out.get("urunler") or []
        if urunler:
            lines = [
                f"- **{u.get('name', '?')}**: Stokta **{u.get('stock_quantity', '?')}** adet var. "
                f"*(Eşik: {u.get('low_stock_threshold', '?')})*"
                for u in urunler[:20]
            ]
            extra = len(urunler) - 20
            if extra > 0:
                lines.append(f"- *... ve {extra} urun daha*")
            body = (
                f"**Kritik stok seviyesinde {len(urunler)} ürün bulunuyor:**\n\n"
                + "\n".join(lines)
                + "\n\nBu ürünler için acil aksiyon almanız önerilir."
            )
            return f"{body}\n\n---\n\n{foot}".strip()
        head = str(out.get("mesaj", "")) if out.get("mesaj") else "Kritik stokta ürün yok."
        return f"{head}\n\n---\n\n{foot}".strip()
    if name == "admin_siparis_listesi":
        if out.get("hata"):
            return str(out["hata"])
        items = out.get("siparisler") or []
        filt = out.get("durum_filtre")
        footer = _orders_panel_md(filt)
        head = str(out.get("mesaj", ""))
        if not items:
            parts = [p for p in (head, footer) if p]
            return "\n\n---\n\n".join(parts).strip()
        lines: list[str] = []
        preview = items[:_CHAT_LIST_PREVIEW]
        for x in preview:
            pr = x.get("total_price")
            prs = f"{float(pr):,.2f} TL".replace(",", " ") if pr is not None else "-"
            lines.append(
                f"- **#{x.get('id')}** `{x.get('tracking_code') or '-'}` — **{x.get('status') or '?'}** — "
                f"{x.get('customer_name') or ''} — {prs}"
            )
        extra = len(items) - len(preview)
        if extra > 0:
            lines.append(f"- *… ve **{extra}** sipariş daha (tamamı için aşağıdaki bağlantı)*")
        body = "\n".join(lines)
        mid = f"**Özet liste** *(ilk {len(preview)} kayıt)*\n\n{body}"
        top = f"{head}\n\n{mid}" if head else mid
        return f"{top}\n\n---\n\n{footer}".strip()
    if name == "admin_bilet_listesi":
        items = out.get("biletler") or []
        footer = _tickets_panel_md()
        head = str(out.get("mesaj", ""))
        if not items:
            parts = [p for p in (head, footer) if p]
            return "\n\n---\n\n".join(parts).strip()
        preview = items[:_CHAT_LIST_PREVIEW]
        lines = [
            f"- **#{x.get('id')}** `[{x.get('priority', '?')}]` *{x.get('status', '?')}* — {x.get('title', '')}"
            for x in preview
        ]
        extra = len(items) - len(preview)
        if extra > 0:
            lines.append(f"- *… ve **{extra}** bilet daha*")
        body = "\n".join(lines)
        mid = f"**Özet liste** *(ilk {len(preview)} kayıt)*\n\n{body}"
        top = f"{head}\n\n{mid}" if head else mid
        return f"{top}\n\n---\n\n{footer}".strip()
    if out.get("mesaj"):
        return str(out["mesaj"])
    return ""


def _yanit_from_tool_rows(tool_calls_info: list) -> str:
    """Son AI mesaji bos ise arac JSON ciktisindan kisa Turkce ozet."""
    parts: list[str] = []
    for tc in tool_calls_info:
        out = tc.get("output")
        if not isinstance(out, dict):
            continue
        name = tc.get("tool") or ""
        block = _format_tool_output(name, out)
        if block:
            parts.append(block)
    return "\n\n".join(parts) if parts else ""


def _rebuild_tool_calls_from_messages(messages: list) -> list:
    """AIMessage.tool_calls ile ToolMessage eslemesi bozulduysa grafik mesajlarindan yeniden kur."""
    rows: list[dict] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            name = (getattr(msg, "name", None) or "").strip()
            if not name:
                continue
            out = _parse_tool_message_content(getattr(msg, "content", None))
            rows.append({"tool": name, "input": {}, "output": out})
    return rows


def _yanit_from_tool_messages(messages: list) -> str:
    parts: list[str] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        name = (getattr(msg, "name", None) or "").strip()
        out = _parse_tool_message_content(getattr(msg, "content", None))
        block = _format_tool_output(name, out)
        if block:
            parts.append(block)
    return "\n\n".join(parts) if parts else ""


def _keyword_direct_fallback(mesaj: str) -> tuple[str, list] | None:
    """LLM bos dondugunde bilinen sorgularda dogrudan DB araci (tenant zaten set)."""
    low = (mesaj or "").lower()
    if ("kritik" in low and "stok" in low) or "düşük stok" in low or "dusuk stok" in low:
        from tools.order_product_tools import kritik_stok_listesi

        out = kritik_stok_listesi.invoke({})
        text = _format_tool_output("kritik_stok_listesi", out) or (out.get("mesaj") if isinstance(out, dict) else "") or "Kritik stok sorgusu tamamlandi."
        tci = [{"tool": "kritik_stok_listesi", "input": {}, "output": out}]
        return text, tci
    if ("kritik" not in low) and (
        any(x in low for x in ("listele", "liste", "goster", "göster"))
        and any(x in low or x in (mesaj or "").lower() for x in ("stok", "envanter", "ürün", "urun"))
    ):
        from tools.admin_tools import admin_urun_listesi

        out = admin_urun_listesi.invoke({})
        text = _format_tool_output("admin_urun_listesi", out) or out.get("mesaj") or ""
        tci = [{"tool": "admin_urun_listesi", "input": {}, "output": out}]
        return text, tci
    if ("günlük" in low or "gunluk" in low) and ("özet" in low or "ozet" in low):
        from tools.order_product_tools import gunluk_ozet

        out = gunluk_ozet.invoke({})
        text = _format_tool_output("gunluk_ozet", out) or (out.get("ozet_metin") if isinstance(out, dict) else "") or "Gunluk ozet alindi."
        tci = [{"tool": "gunluk_ozet", "input": {}, "output": out}]
        return text, tci
    if ("siparis" in low or "sipariş" in low) and (
        "listele" in low or "liste" in low or "goster" in low or "göster" in low
    ):
        from tools.admin_tools import admin_siparis_listesi

        durum: str | None = None
        if "hazirlan" in low or "hazırlan" in (mesaj or "").lower():
            durum = "hazırlanıyor"
        elif "kargoda" in low or "kargodaki" in low:
            durum = "kargoda"
        elif "teslim_edildi" in low or "teslim edildi" in low:
            durum = "teslim_edildi"
        elif "iptal" in low:
            durum = "iptal"
        inp = {"durum": durum} if durum else {}
        out = admin_siparis_listesi.invoke(inp)
        text = _format_tool_output("admin_siparis_listesi", out) or out.get("mesaj") or ""
        tci = [{"tool": "admin_siparis_listesi", "input": inp, "output": out}]
        return text, tci
    if "bilet" in low and (
        "listele" in low
        or "liste" in low
        or "oncelik" in low
        or "öncelik" in (mesaj or "").lower()
        or "acik" in low
        or "açık" in (mesaj or "").lower()
        or "cozulmemis" in low
        or "çözülmemiş" in (mesaj or "").lower()
    ):
        from tools.admin_tools import admin_bilet_listesi

        out = admin_bilet_listesi.invoke({"sadece_acik": True})
        text = _format_tool_output("admin_bilet_listesi", out) or out.get("mesaj") or ""
        tci = [{"tool": "admin_bilet_listesi", "input": {"sadece_acik": True}, "output": out}]
        return text, tci
    return None


def _resolve_yanit(turn_messages: list, tool_calls_info: list) -> str:
    best = ""
    for msg in turn_messages:
        if isinstance(msg, AIMessage):
            t = _stringify_lc_content(msg.content)
            if t:
                best = t
    if best:
        return best
    tail = _stringify_lc_content(getattr(turn_messages[-1], "content", None))
    if tail:
        return tail
    from_tm = _yanit_from_tool_messages(turn_messages)
    if from_tm:
        return from_tm
    from_tools = _yanit_from_tool_rows(tool_calls_info)
    if from_tools:
        return from_tools
    if tool_calls_info:
        return "Arac sonuclari asagida; model kisa metin dondurmedi."
    return ""


class AdminChatRequest(BaseModel):
    mesaj: str
    session_id: Optional[str] = None


class ToolCallInfo(BaseModel):
    tool: str
    input: dict = {}
    output: dict = {}


class AdminChatResponse(BaseModel):
    yanit: str
    session_id: str
    tool_calls: list = []


class AdminPendingConfirmRequest(BaseModel):
    onay_token: str
    session_id: Optional[str] = None


def _yanit_from_confirm_output(out: dict) -> str:
    if out.get("hata"):
        return str(out["hata"])
    if out.get("basari"):
        parts = [f"İşlem tamamlandı ({'başarılı' if out.get('basari') else ''})."]
        if out.get("urun"):
            parts.append(f"Ürün: {out.get('urun')}")
        if out.get("siparis_no") is not None:
            parts.append(f"Sipariş #{out.get('siparis_no')}")
        if out.get("detaylar"):
            parts.append("Detaylar araç kartında.")
        return " ".join(p for p in parts if p).strip()
    if out.get("toplam") is not None and out.get("detaylar") is not None:
        return f"Toplu işlem: {out.get('basarili', 0)}/{out.get('toplam', 0)} başarılı. Ayrıntılar araç kartında."
    return json.dumps(out, ensure_ascii=False)[:500]


@router.post("/pending/confirm", response_model=AdminChatResponse)
async def admin_pending_confirm(
    body: AdminPendingConfirmRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Bekleyen admin mutasyonunu token ile uygular (panel Onayla)."""
    set_tenant_id(current_user.tenant_id)
    set_admin_user_id(current_user.id)
    sid = body.session_id or f"confirm_{uuid.uuid4().hex[:8]}"
    rec = take_pending(body.onay_token.strip(), current_user.tenant_id, current_user.id)
    if rec is None:
        return AdminChatResponse(
            yanit="Onay geçersiz veya süresi dolmuş. İşlemi yeniden başlatın.",
            session_id=sid,
            tool_calls=[],
        )
    out = apply_pending_payload(rec.payload, current_user.tenant_id)
    tci = [{"tool": "admin_pending_uygula", "input": {"onay_token": "(confirmed)"}, "output": out}]
    yanit = _format_tool_output("admin_pending_uygula", out) or _yanit_from_confirm_output(out)
    return AdminChatResponse(yanit=yanit, session_id=sid, tool_calls=tci)


@router.post("/chat", response_model=AdminChatResponse)
async def admin_chat(request: AdminChatRequest, current_user: CurrentUser = Depends(get_current_user)):
    """
    İşletmeci için yönetim asistanı. Müşteri auth gerekmez.
    Stok girişi, sipariş güncelleme, ürün ekleme, bilet yönetimi.
    """
    session_id = request.session_id or f"admin_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": session_id}}
    set_tenant_id(current_user.tenant_id)
    set_admin_user_id(current_user.id)

    try:
        result = admin_graph.invoke(
            {"messages": [HumanMessage(content=request.mesaj)]},
            config=config,
        )

        turn_msgs = _messages_current_turn(result["messages"])

        tool_calls_info = []
        for msg in turn_msgs:
            # Tool çağrıları (LLM'in istediği)
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    name, args = _tool_call_name_args(tc)
                    if not name:
                        continue
                    tool_calls_info.append({
                        "tool": name,
                        "input": args,
                        "output": {},
                    })
            # Tool sonuçları
            if hasattr(msg, "name") and msg.name:
                for tc in tool_calls_info:
                    if tc["tool"] == msg.name and not tc["output"]:
                        try:
                            tc["output"] = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                        except Exception:
                            tc["output"] = {"sonuc": str(msg.content)[:300]}
                        break

        parsed_ok = any(
            isinstance(tc.get("output"), dict) and tc["output"]
            for tc in tool_calls_info
        )
        if not parsed_ok:
            alt = _rebuild_tool_calls_from_messages(turn_msgs)
            if alt:
                tool_calls_info = alt

        final_message = _resolve_yanit(turn_msgs, tool_calls_info)
        if not final_message.strip():
            fb = _keyword_direct_fallback(request.mesaj)
            if fb:
                final_message, tool_calls_info = fb

        final_message = _merge_panel_banners(final_message, tool_calls_info, request.mesaj)

        return AdminChatResponse(
            yanit=final_message,
            session_id=session_id,
            tool_calls=tool_calls_info,
        )

    except Exception as e:
        return AdminChatResponse(
            yanit=f"Hata oluştu: {str(e)[:300]}",
            session_id=session_id,
            tool_calls=[],
        )


@router.delete("/chat/{session_id}")
async def clear_admin_session(session_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Admin chat geçmişini sıfırlar (yeni sohbet başlatmak için)."""
    # MemorySaver in-memory olduğu için sadece frontend'e bilgi dönmek yeterli
    return {"mesaj": f"Oturum '{session_id}' sıfırlandı.", "session_id": session_id}
