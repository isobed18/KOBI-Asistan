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
from config import settings


def _create_llm(temperature: float = 0.3):
    """Provider-bağımsız LLM factory. LLM_PROVIDER env değişkeniyle kontrol edilir."""
    provider = getattr(settings, "LLM_PROVIDER", "ollama").lower()

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
        return f"## Rapor Üretim Hatası\n\nLLM servisi yanıt vermedi: {e}\n\nHam veri:\n```json\n{json.dumps(raw_data, ensure_ascii=False, indent=2)}\n```"


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
        return f"## Rapor Üretim Hatası\n\nLLM servisi yanıt vermedi: {e}"


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
