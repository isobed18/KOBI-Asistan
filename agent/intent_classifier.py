"""
Intent Classifier + Response Cache
=====================================
Regex tabanlı intent tespiti. Basit sorgularda LLM bypass sağlar.
~%70-80 oranında sıfır LLM maliyeti.
"""

import re
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from difflib import SequenceMatcher

from tools.order_product_tools import (
    siparis_sorgula,
    musteri_siparisleri,
    urun_stok_kontrol,
    kritik_stok_listesi,
    gunluk_ozet,
)
from tools.kargo_tools import kargo_takip
from agent.auth import get_active_scope


# ---------------------------------------------------------------------------
# Intent tanımları
# ---------------------------------------------------------------------------

INTENTS = {
    "siparis_sorgula": [
        r"SIP-([A-Z0-9]{6})",
        r"(?:sipari[sş]|order)\s*(?:no|numara|#|numaras[iı])?\s*[:#]?\s*(\d+)",
        r"(\d+)\s*(?:nolu|numaral[iı]|no'lu)\s*sipari[sş]",
        r"sipari[sş]im\s+(?:nerede|ne\s+zaman|durumu|bilgisi)",
        r"(?:nerede|ne\s+oldu)\s+(?:sipari[sş]im|siparişim)",
        r"takip\s+(?:kodu|numaras[iı])\s*[:#]?\s*(SIP-[A-Z0-9]{6}|\d+)",
    ],
    "musteri_siparisleri": [
        r"(?:t[üu]m|b[üu]t[üu]n|hepsi|liste)\s+sipari[sş]",
        r"sipari[sş]lerim",
        r"ge[çc]mi[sş]\s+sipari[sş]",
        r"sipari[sş]\s+ge[çc]mi[sş]",
        r"sipari[sş]\s+listesi",
        r"ka[çc]\s+sipari[sş]im\s+var",
    ],
    "stok_sorgu": [
        r"([\w\s]+?)\s+(?:var\s+m[iı]|stokta\s+(?:var\s+m[iı]|mevcut)|ka[çc]\s+adet)",
        r"([\w\s]+?)\s+(?:fiyat[iı]|ne\s+kadar|[üu]cret)",
        r"(?:stok|mevcut|ürün)\s+(?:durumu|sorgula|kontrol)[\s:]+(.+)",
        r"([\w\s]+?)\s+ürün[üu]?\s+(?:var|mevcut|stokta)",
    ],
    "kritik_stok": [
        r"kritik\s+stok",
        r"stok\s+uyar[iı]",
        r"hangi\s+[üu]r[üu]nler?\s+azald[iı]",
        r"biten\s+[üu]r[üu]n",
        r"azalan\s+[üu]r[üu]n",
        r"d[üu][sş][üu]k\s+stok",
    ],
    "gunluk_ozet": [
        r"(?:g[üu]nl[üu]k|bug[üu]n[üu]?\s+(?:durumu?|[öo]zet|rapor))",
        r"(?:durumu?|[öo]zet)\s+nedir",
        r"bug[üu]n\s+(?:ne\s+var|ne\s+oldu|nas[iı]l)",
        r"sipari[sş]\s+[öo]zeti",
        r"g[üu]nl[üu]k\s+rapor",
    ],
    "kargo_takip": [
        r"kargo\s+(?:nerede|takip|durumu?|bilgi|kodu)",
        r"teslimat\s+(?:nerede|ne\s+zaman|tahmini|s[üu]resi)",
        r"g[öo]nderildi\s+mi",
        r"kargoya\s+verildi\s+mi",
        r"(?:aras|yurtiçi|mng|ups|fedex|ptt)\s+kargo",
    ],
    "iptal_talebi": [
        r"sipari[sş]\s+iptal",
        r"iptal\s+etmek\s+istiyorum",
        r"iptal\s+talebim",
        r"geri\s+al",
        r"vazge[çc]",
        r"siparişimi\s+iptal",
    ],
}

SEMANTIC_EXAMPLES = {
    "siparis_sorgula": [
        "siparisim nerede",
        "siparis durumunu ogrenmek istiyorum",
        "order status",
    ],
    "stok_sorgu": [
        "bu urunden var mi",
        "stokta kac tane var",
        "urun fiyati nedir",
    ],
    "kritik_stok": [
        "azalan urunleri goster",
        "hangi urunler bitmek uzere",
    ],
    "gunluk_ozet": [
        "bugun isler nasil",
        "gunluk durum nedir",
    ],
    "kargo_takip": [
        "kargom nerede",
        "teslimat ne zaman",
    ],
    "iptal_talebi": [
        "siparisi iptal etmek istiyorum",
        "vazgectim iptal olsun",
    ],
}

_embedding_model = None
_example_embeddings = None

# Feature flag: USE_EMBEDDING_CLASSIFIER=true → sentence-transformers yükle
# False ise sadece difflib fallback kullanılır (hafif, sıfır bağımlılık).
import os as _os
_USE_EMBEDDING = _os.environ.get("USE_EMBEDDING_CLASSIFIER", "false").lower() == "true"


def _semantic_intent(text: str) -> tuple[str, float] | None:
    """
    Semantic intent: sentence-transformers (USE_EMBEDDING_CLASSIFIER=true) veya
    difflib fallback. Embedding kapalıysa sadece difflib çalışır.
    """
    global _embedding_model, _example_embeddings

    if _USE_EMBEDDING:
        try:
            if _embedding_model is None:
                import logging
                logging.getLogger(__name__).debug("Loading sentence-transformers model...")
                from sentence_transformers import SentenceTransformer
                _embedding_model = SentenceTransformer(
                    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                )
                flat = [(intent, phrase) for intent, phrases in SEMANTIC_EXAMPLES.items() for phrase in phrases]
                _example_embeddings = (
                    flat,
                    _embedding_model.encode([phrase for _, phrase in flat], normalize_embeddings=True),
                )
            flat, embeddings = _example_embeddings
            query_emb = _embedding_model.encode([text], normalize_embeddings=True)[0]
            scores = embeddings @ query_emb
            best_idx = int(scores.argmax())
            best_score = float(scores[best_idx])
            if best_score >= 0.68:
                return flat[best_idx][0], best_score
            return None
        except Exception:
            pass  # embedding hatası → difflib'e düş

    # difflib fallback (her zaman çalışır)
    best_intent, best_score = None, 0.0
    for intent, phrases in SEMANTIC_EXAMPLES.items():
        for phrase in phrases:
            score = SequenceMatcher(None, text.lower(), phrase.lower()).ratio()
            if score > best_score:
                best_intent, best_score = intent, score
    if best_intent and best_score >= 0.72:
        return best_intent, best_score
    return None

# ---------------------------------------------------------------------------
# Response Cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple] = {}  # key → (response, expires_at)
CACHE_TTL = 300  # 5 dakika


def _cache_key(intent: str, params: dict, scope: dict) -> str:
    scope_str = scope.get("telefon") or scope.get("takip_kodu") or "admin"
    params_str = str(sorted(params.items()))
    raw = f"{intent}:{params_str}:{scope_str}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    entry = _cache.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None


def _cache_set(key: str, value: str, ttl: int = CACHE_TTL):
    _cache[key] = (value, time.time() + ttl)
    # Bellek temizliği: 1000'den fazla entry varsa eskilerini sil
    if len(_cache) > 1000:
        now = time.time()
        expired = [k for k, (_, exp) in _cache.items() if exp < now]
        for k in expired:
            del _cache[k]


def invalidate_order_cache(order_id: int = None):
    """Sipariş durumu güncellendiğinde cache'i temizle."""
    global _cache
    _cache = {k: v for k, v in _cache.items() if "siparis_sorgula" not in k}


# ---------------------------------------------------------------------------
# Intent Detection
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    intent: str
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    bypass_llm: bool = False


def _extract_order_ref(text: str) -> dict:
    """Metinden sipariş no veya takip kodu çıkarır."""
    code = re.search(r"SIP-([A-Z0-9]{6})", text, re.IGNORECASE)
    if code:
        return {"takip_kodu": code.group(0).upper()}
    num = re.search(r"\b(\d{1,6})\b", text)
    if num:
        return {"siparis_no": int(num.group(1))}
    return {}


def _extract_product_name(text: str) -> str:
    """Metinden ürün adı çıkarır."""
    patterns = [
        r"([\w\s]+?)\s+(?:var\s+m[iı]|stokta|ka[çc]\s+adet|fiyat[iı]|ne\s+kadar)",
        r"(?:stok|mevcut|[üu]r[üu]n)[\s:]+(.+?)(?:\s+var|\s+mevcut|$)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if 2 <= len(name) <= 40:
                return name
    return ""


def classify(text: str) -> IntentResult:
    """
    Metni sınıflandırır. bypass_llm=True ise LangGraph atlanabilir.
    """
    text_lower = text.lower()

    for intent, patterns in INTENTS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                params = {}

                if intent == "siparis_sorgula":
                    params = _extract_order_ref(text)
                    # Sadece referans varsa bypass et
                    bypass = bool(params)

                elif intent == "musteri_siparisleri":
                    scope = get_active_scope()
                    bypass = bool(scope.get("telefon") or scope.get("takip_kodu"))

                elif intent == "stok_sorgu":
                    params["urun_adi"] = _extract_product_name(text) or ""
                    bypass = bool(params["urun_adi"])

                elif intent in ("kritik_stok", "gunluk_ozet"):
                    bypass = True  # Parametre gerekmez

                elif intent == "kargo_takip":
                    params = _extract_order_ref(text)
                    bypass = False  # Kargo takip LLM'e bırak (order→cargo chain)

                elif intent == "iptal_talebi":
                    params = _extract_order_ref(text)
                    bypass = False  # İptal talebi her zaman LLM'e gider (ticket creation)

                else:
                    bypass = False

                return IntentResult(
                    intent=intent,
                    params=params,
                    confidence=0.9,
                    bypass_llm=bypass,
                )

    semantic = _semantic_intent(text)
    if semantic:
        intent, score = semantic
        params = {}
        if intent == "stok_sorgu":
            params["urun_adi"] = _extract_product_name(text) or text
        elif intent in ("siparis_sorgula", "kargo_takip", "iptal_talebi"):
            params = _extract_order_ref(text)
        scope = get_active_scope()
        bypass = intent in ("kritik_stok", "gunluk_ozet")
        if intent == "stok_sorgu":
            bypass = bool(params.get("urun_adi"))
        if intent == "siparis_sorgula":
            bypass = bool(params)
        if intent == "musteri_siparisleri":
            bypass = bool(scope.get("telefon") or scope.get("takip_kodu"))
        return IntentResult(intent=intent, params=params, confidence=score, bypass_llm=bypass)

    return IntentResult(intent="genel", confidence=0.0, bypass_llm=False)


# ---------------------------------------------------------------------------
# Fast Path: Tool'u direkt çağır + template response
# ---------------------------------------------------------------------------

def _fmt_order(data: dict) -> str:
    if "hata" in data:
        return f"❌ {data['hata']}"
    lines = [
        f"📦 *Sipariş #{data.get('siparis_no')}*",
        f"Durum: {data.get('durum_aciklamasi', data.get('durum', '?'))}",
    ]
    if data.get("kargo_kodu"):
        lines.append(f"🚚 Kargo: {data['kargo_kodu']} ({data.get('kargo_firmasi', '')})")
    if data.get("urunler"):
        lines.append("Ürünler:")
        for u in data["urunler"]:
            lines.append(f"  • {u['urun']} x{u['adet']} — ₺{u['fiyat']}")
    if data.get("toplam"):
        lines.append(f"Toplam: ₺{data['toplam']:.2f}")
    return "\n".join(lines)


def _fmt_orders_list(data: dict) -> str:
    if "hata" in data:
        return f"❌ {data['hata']}"
    if "mesaj" in data and not data.get("siparisler"):
        return data["mesaj"]
    lines = [f"📋 *{data['siparis_sayisi']} Sipariş Bulundu:*"]
    for s in data["siparisler"]:
        lines.append(
            f"• #{s['siparis_no']} ({s['takip_kodu']}) — {s['durum']} — ₺{s.get('toplam', 0):.2f}"
        )
    return "\n".join(lines)


def _fmt_stock(data: dict) -> str:
    if data.get("sonuc") == "bulunamadi":
        return f"❌ {data['mesaj']}"
    lines = ["🗂️ *Stok Bilgisi:*"]
    for u in data.get("urunler", []):
        icon = "✅" if u["stok_durumu"] == "mevcut" else "⚠️" if u["stok_durumu"] == "sinirli stok" else "❌"
        lines.append(f"{icon} {u['ad']} — {u['stok_durumu']} ({u['adet']} adet) — ₺{u['fiyat']:.2f}")
    return "\n".join(lines)


def _fmt_critical_stock(data: dict) -> str:
    if not data.get("urunler"):
        return "✅ Tüm ürünler yeterli stok seviyesinde."
    lines = [f"⚠️ *{len(data['urunler'])} Ürün Kritik Stokta:*"]
    for u in data["urunler"]:
        lines.append(f"• {u['name']}: {u['stock_quantity']} adet (eşik: {u['low_stock_threshold']})")
    return "\n".join(lines)


def _fmt_daily_summary(data: dict) -> str:
    dist = data.get("durum_dagilimi", {})
    bugun = data.get("bugun_tarihi") or ""
    lines = [
        f"📊 *Günlük özet*" + (f" — *{bugun}*" if bugun else ""),
        f"Bugün oluşturulan sipariş: {data.get('toplam_siparis', 0)}",
    ]
    for durum, adet in dist.items():
        icons = {"hazırlanıyor": "⏳", "kargoda": "🚚", "teslim_edildi": "✅", "iptal": "❌"}
        lines.append(f"  {icons.get(durum, '•')} {durum}: {adet}")
    lines.append(f"Bugünkü ciro (iptaller hariç): ₺{data.get('toplam_gelir', 0):,.2f}")
    if data.get("kritik_stok_sayisi", 0) > 0:
        lines.append(f"⚠️ Kritik stok: {data['kritik_stok_sayisi']} ürün")
        for u in data.get("kritik_urunler", []):
            lines.append(f"  • {u}")
    return "\n".join(lines)


def fast_response(result: IntentResult) -> Optional[str]:
    """
    Bypass LLM → tool'u direkt çağır → formatlanmış yanıt döner.
    Hata durumunda None döner (LangGraph'a düş).
    """
    try:
        scope = get_active_scope()
        cache_k = _cache_key(result.intent, result.params, scope)

        # Cache kontrolü
        cached = _cache_get(cache_k)
        if cached:
            return cached + "\n\n_⚡ Önbellekten_"

        # Tool çağrısı
        if result.intent == "siparis_sorgula" and result.params:
            data = siparis_sorgula.invoke(result.params)
            response = _fmt_order(data)

        elif result.intent == "musteri_siparisleri":
            data = musteri_siparisleri.invoke({})
            response = _fmt_orders_list(data)

        elif result.intent == "stok_sorgu" and result.params.get("urun_adi"):
            data = urun_stok_kontrol.invoke({"urun_adi": result.params["urun_adi"]})
            response = _fmt_stock(data)

        elif result.intent == "kritik_stok":
            data = kritik_stok_listesi.invoke({})
            response = _fmt_critical_stock(data)

        elif result.intent == "gunluk_ozet":
            data = gunluk_ozet.invoke({})
            response = _fmt_daily_summary(data)

        else:
            return None  # LangGraph'a düş

        # Cache'e kaydet (hata mesajlarını cache'leme)
        if not response.startswith("❌"):
            _cache_set(cache_k, response)

        return response

    except Exception:
        return None  # Hata durumunda LangGraph'a düş
