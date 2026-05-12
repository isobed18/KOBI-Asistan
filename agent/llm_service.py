"""
LLM Servisi — Rapor ve Bilet Üretimi
======================================
Zamanlayıcı ve router'ların AI içerik üretmesi için kullanılır.
Revive.md kuralına uygun: her zaman _create_llm() factory'si üzerinden çağrılır.
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.messages import HumanMessage
from config import settings, normalize_llm_provider


def _llm_connectivity_hint(exc: Exception) -> str:
    """Connection refused gibi hatalarda yanlış provider (ör. Ollama kapalı) ipucu."""
    msg = str(exc).lower()
    errno = getattr(exc, "errno", None)
    if errno != 61 and "connection refused" not in msg and "failed to establish" not in msg:
        return ""
    prov = normalize_llm_provider(getattr(settings, "LLM_PROVIDER", None))
    if prov == "ollama":
        return (
            "\n\n---\n**İpucu:** `LLM_PROVIDER` şu an **ollama**; istek `OLLAMA_BASE_URL` "
            "(varsayılan `http://localhost:11434`) adresine gidiyor. Ollama kapalıysa bu hata oluşur. "
            "Google Gemini kullanacaksanız `.env` içinde `LLM_PROVIDER=gemini` ve `GOOGLE_API_KEY` "
            "(veya `GEMINI_API_KEY`) tanımlayın, ardından API sunucusunu yeniden başlatın."
        )
    return ""


def _create_llm(temperature: float = 0.3):
    """Provider-bağımsız LLM factory. LLM_PROVIDER env değişkeniyle kontrol edilir."""
    provider = normalize_llm_provider(getattr(settings, "LLM_PROVIDER", "ollama"))

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
            temperature=temperature,
            api_key=getattr(settings, "OPENAI_API_KEY", ""),
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=getattr(settings, "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            temperature=temperature,
            api_key=getattr(settings, "ANTHROPIC_API_KEY", ""),
        )
    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash"),
            temperature=temperature,
            google_api_key=getattr(settings, "GEMINI_API_KEY", ""),
        )
    else:  # ollama (default)
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
        )


def _extract_json(text: str) -> dict:
    """LLM çıktısından JSON bloğunu güvenli şekilde çıkarır."""
    # Önce ```json ... ``` bloğunu dene
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # Direkt JSON dene
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------------------
# Günlük Rapor
# ---------------------------------------------------------------------------

def generate_daily_report(raw_data: dict) -> str:
    """Ham özet veriden kapsamlı Türkçe yönetici raporu üretir."""
    llm = _create_llm(temperature=0.4)

    prompt = f"""Sen deneyimli bir işletme analisti yapay zeka asistanısın.
Küçük ve orta ölçekli bir e-ticaret işletmesi için aşağıdaki günlük operasyonel veriyi analiz et
ve işletme sahibine yönelik kapsamlı, aksiyon odaklı bir sabah raporu hazırla.

Veri:
{json.dumps(raw_data, ensure_ascii=False, indent=2)}

Raporun yapısı:
## 📊 Genel Durum Özeti
(2-3 cümle, genel sağlık durumu)

## 📦 Sipariş Durumu
(durumlara göre dağılım, dikkat edilmesi gerekenler)

## ⚠️ Stok Uyarıları
(kritik ürünler ve önerilen aksiyonlar — yoksa "Tüm ürünler yeterli stok seviyesinde.")

## 🚚 Kargo Durumu
(gecikme veya sorunlar — yoksa "Kargo süreçleri sorunsuz devam ediyor.")

## 🎫 Bekleyen Biletler & Çözülmesi Gerekenler
(açık biletleri öncelik sırasıyla listele; yoksa "İnceleme bekleyen bilet bulunmuyor.")

## ✅ Bugün Yapılması Gerekenler
(öncelik sırasına göre madde madde, bilet aksiyon maddelerini de dahil et)

## 💡 Öneri
(1 adet kısa stratejik öneri)

Raporu Türkçe ve samimi bir yönetici diliyle yaz. Markdown kullan."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content
    except Exception as e:
        hint = _llm_connectivity_hint(e)
        return f"## Rapor Üretim Hatası\n\nLLM servisi yanıt vermedi: {e}{hint}\n\nHam veri:\n```json\n{json.dumps(raw_data, ensure_ascii=False, indent=2)}\n```"


async def agenerate_daily_report(raw_data: dict) -> str:
    """Async versiyon — APScheduler için."""
    llm = _create_llm(temperature=0.4)

    prompt = f"""Sen deneyimli bir işletme analisti yapay zeka asistanısın.
Küçük ve orta ölçekli bir e-ticaret işletmesi için aşağıdaki günlük operasyonel veriyi analiz et
ve işletme sahibine yönelik kapsamlı, aksiyon odaklı bir sabah raporu hazırla.

Veri:
{json.dumps(raw_data, ensure_ascii=False, indent=2)}

Raporun yapısı:
## 📊 Genel Durum Özeti
## 📦 Sipariş Durumu
## ⚠️ Stok Uyarıları
## 🚚 Kargo Durumu
## 🎫 Bekleyen Biletler & Çözülmesi Gerekenler
## ✅ Bugün Yapılması Gerekenler
## 💡 Öneri

Raporu Türkçe ve samimi bir yönetici diliyle yaz. Markdown kullan."""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
    except Exception as e:
        hint = _llm_connectivity_hint(e)
        return f"## Rapor Üretim Hatası\n\nLLM servisi yanıt vermedi: {e}{hint}"


# ---------------------------------------------------------------------------
# Kargo Gecikme Bileti
# ---------------------------------------------------------------------------

async def agenerate_cargo_delay_content(order_info: dict) -> dict:
    """Kargo gecikmesi için müşteri mesajı ve iç not üretir. Async."""
    llm = _create_llm(temperature=0.3)

    prompt = f"""Sen bir müşteri hizmetleri uzmanı yapay zeka asistanısın.
Aşağıdaki kargo gecikmesi durumu için iki metin üret:
1. Müşteriye gönderilecek kısa bilgilendirme mesajı (max 2 cümle, özür ve durum bilgisi içermeli)
2. Operasyon ekibine iç not (durum tespiti + önerilen aksiyon)

Sipariş Bilgisi:
{json.dumps(order_info, ensure_ascii=False, indent=2)}

Yanıtı SADECE şu JSON formatında ver:
{{"musteri_mesaji": "...", "ic_not": "..."}}"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = _extract_json(response.content)
        if not result:
            return {
                "musteri_mesaji": f"Sayın müşterimiz, {order_info.get('customer_name', '')} kargonuzda bir gecikme yaşanmaktadır. En kısa sürede çözüme kavuşturacağız.",
                "ic_not": f"Sipariş #{order_info.get('id')} kargo gecikmesi tespit edildi. Kargo firmasıyla iletişime geçilmeli."
            }
        return result
    except Exception as e:
        return {
            "musteri_mesaji": "Kargonuzda geçici bir gecikme yaşanmaktadır. Ekibimiz durumu takip etmektedir.",
            "ic_not": f"LLM hatası: {e}"
        }


# ---------------------------------------------------------------------------
# Kritik Stok Bileti
# ---------------------------------------------------------------------------

async def agenerate_stock_alert_content(product_info: dict) -> dict:
    """Kritik stok için yenileme önerisi ve tedarikçi e-postası üretir. Async."""
    llm = _create_llm(temperature=0.3)

    threshold = product_info.get("low_stock_threshold", 10)
    recommended_qty = max(threshold * 3, 30)

    prompt = f"""Sen bir tedarik zinciri uzmanı yapay zeka asistanısın.
Küçük bir işletmede kritik stok uyarısı oluştu. Şunları üret:
1. Önerilen sipariş miktarı (stok eşiğinin 3 katı = {recommended_qty} birim öner)
2. Tedarikçiye gönderilecek kısa ve profesyonel Türkçe e-posta taslağı

Ürün Bilgisi:
{json.dumps(product_info, ensure_ascii=False, indent=2)}

Yanıtı SADECE şu JSON formatında ver:
{{"onerilen_miktar": {recommended_qty}, "tedarikci_emaili": "..."}}"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = _extract_json(response.content)
        if not result:
            return {
                "onerilen_miktar": recommended_qty,
                "tedarikci_emaili": f"Konu: Acil Stok Siparişi - {product_info.get('name', 'Ürün')}\n\nSayın Tedarikçi,\n\n{product_info.get('name', 'Ürün')} ürününden {recommended_qty} adet acil sipariş vermek istiyoruz. Uygunluğunuzu ve fiyat teklifinizi en kısa sürede iletmenizi rica ederiz.\n\nSaygılarımızla"
            }
        return result
    except Exception as e:
        return {
            "onerilen_miktar": recommended_qty,
            "tedarikci_emaili": f"LLM hatası nedeniyle e-posta taslağı oluşturulamadı: {e}"
        }


# ---------------------------------------------------------------------------
# AI Görev Listesi (Dashboard proaktif görevler)
# ---------------------------------------------------------------------------

async def agenerate_ai_tasks(data: dict) -> dict:
    """
    İşletme verisine bakarak bugünkü proaktif görev listesini üretir.
    Döndürülen format:
    {
      "briefing": "Kısa özet",
      "tasks": [{"id","icon","title","body","priority","link","action"}, ...],
      "generated_at": "HH:MM",
      "source": "llm"
    }
    """
    import time as _time
    llm = _create_llm(temperature=0.5)

    low_stock_names = ", ".join(r["name"] for r in data.get("low_stock", []))
    prompt = f"""Sen bir KOBİ yönetim asistanısın. Aşağıdaki verilere göre işletme sahibine bugün yapması gereken öncelikli görevleri listele.

Veri:
- Kritik stokta ürün sayısı: {len(data.get('low_stock', []))} ({low_stock_names or 'yok'})
- Açık bilet sayısı: {data.get('open_tickets', 0)}
- Bekleyen sipariş sayısı: {data.get('pending_orders', 0)}
- Geciken kargo sayısı: {data.get('delayed_cargo', 0)}

SADECE JSON döndür, başka metin yok:
{{
  "briefing": "Tek cümle özetle bugünkü durum",
  "tasks": [
    {{
      "id": "benzersiz_id",
      "icon": "emoji",
      "title": "Görev başlığı",
      "body": "Kısa açıklama",
      "priority": "high|normal|low",
      "link": "/inventory|/tickets|/orders|/cargo",
      "action": "inventory|tickets|orders|cargo"
    }}
  ]
}}"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = _extract_json(response.content)
        if result and "tasks" in result:
            result["generated_at"] = _time.strftime("%H:%M")
            result["source"] = "llm"
            return result
    except Exception:
        pass

    # Fallback — template (import'tan kaçın, dashboard.py'deki _build_template_tasks kullanacak)
    raise RuntimeError("LLM AI tasks failed — caller should use template fallback")
