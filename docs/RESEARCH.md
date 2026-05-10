# Araştırma Raporu — Açık Kaynak Ekosistem & Gelecek Mimari

> **Tarih:** 11 Mayıs 2026
> **Konu:** KOBİ Asistan için en ilgili açık kaynak projeler, NeMo Guardrails entegrasyonu ve maliyet/hız optimizasyon stratejileri

---

## 1. İncelenen Repolar

### ⭐ yerdaulet-damir/langgraph-sales-agent (EN İLGİLİ)

**Repo:** https://github.com/yerdaulet-damir/langgraph-sales-agent

**Ne yapıyor:** Multi-tenant AI satış asistanı framework'ü. Tek codebase ile birden fazla işletmeye (çiçekçi, restoran, e-ticaret) hizmet veriyor.

**Mimari benzerlikler:**

| Özellik | Onların | Bizim |
|---------|---------|-------|
| LangGraph graph | ✅ Shared graph, ~50 satır | ✅ StateGraph + ToolNode |
| Channel adapters | ✅ TG/IG/WA/Web | ✅ TG/Web |
| Tool calling | ✅ search_products, promotions | ✅ siparis, stok, kargo, ozet |
| Multi-tenant | ✅ YAML config per tenant | ❌ Tek tenant |
| Auth/Scope | ❌ Sadece tenant izolasyonu | ✅ Müşteri bazlı scope |
| Guardrails | ❌ Yok | ✅ 3 katman prompt police |
| Order tracking | ❌ Roadmap'te | ✅ Çalışır durumda |
| Image search | ✅ Ürün görseli araması | ❌ |

**Alabileceğimiz fikirler:**
1. **Multi-tenant YAML config** — `tenants/` dizininde her işletme için `config.yaml` + `products.json`. Kodumuza adaptasyonu kolay.
2. **Channel adapter pattern** — WhatsApp ve Instagram eklemek için temiz soyutlama katmanı.
3. **Repository pattern** — DB erişimini soyutlama (şu an direkt SQL yazıyoruz, bu refactor edilmeli).
4. **LLM provider factory** — Tenant başına farklı LLM seçimi (OpenAI/Anthropic/Ollama).

**Entegrasyon önerisi:** Multi-tenant yapıya geçmek istediğimizde direkt bu repo'nun `config/tenant_config.py` + `config.yaml` yapısını adapte edebiliriz. Minimal değişiklikle birden fazla KOBİ'ye hizmet verilir.

---

### francescofano/langgraph-telegram-bot

**Repo:** https://github.com/francescofano/langgraph-telegram-bot

**Ne yapıyor:** Production-ready Telegram bot, long-term memory (pgvector), Redis rate limiting, message aggregation.

**Maliyet düşürme için kritik özellikler:**

| Özellik | Detay | Bizim İçin Değer |
|---------|-------|------------------|
| **Rate limiting** | LLM çağrılarını dakika bazında sınırlar | Maliyet kontrolü |
| **Message aggregation** | Birden fazla hızlı mesajı tek isteğe birleştirir | -30% LLM çağrı |
| **Debounce** | 5 sn bekleme ile ardışık mesajları grupler | Gereksiz çağrı önleme |
| **Long-term memory** | pgvector ile müşteri geçmişini hatırlar | Kişiselleştirme |

**Entegrasyon önerisi:** Rate limiting ve debounce mekanizmalarını `routers/chat.py`'ye eklemek kolay. Redis dependency eklemeden, in-memory token bucket ile başlanabilir.

---

### JoshuaC215/agent-service-toolkit

**Repo:** https://github.com/JoshuaC215/agent-service-toolkit

**Ne yapıyor:** LangGraph + FastAPI + Streamlit tam toolkit. Content moderation, RAG, feedback, Docker.

**İlgili özellikler:**
- **Content moderation (Safeguard)** — Groq API ile content moderation. Bizim prompt police'in LLM-powered versiyonu olabilir.
- **Multi-agent support** — Farklı agent'lar `/agent_name/invoke` endpoint'i ile erişilebilir.
- **RAG agent** — ChromaDB ile RAG implementasyonu var.
- **Feedback mechanism** — Müşteri yanıt memnuniyeti (yıldız sistemi).

**Entegrasyon önerisi:** RAG agent yapısı FAQ sistemi için referans olabilir. Feedback mekanizması chat UI'a eklenebilir.

---

### lucasboscatti/sales-ai-agent-langgraph

**Repo:** https://github.com/lucasboscatti/sales-ai-agent-langgraph

**Ne yapıyor:** Virtual Sales Agent — ürün sorgulama, sipariş oluşturma, sipariş takibi, kişiselleştirilmiş öneriler.

**İlgili özellikler:**
- **Human-in-the-loop** — Kritik işlemler (sipariş oluşturma) için insan onayı mekanizması.
- **Safe/Sensitive tool ayrımı** — Read-only (güvenli) vs mutating (hassas) tool kategorileri.
- **LangGraph interrupt()** — Hassas tool çağrısından önce kullanıcı onayı.

**Entegrasyon önerisi:** Sipariş oluşturma veya iptal gibi mutating işlemler eklendiğinde, LangGraph'ın `interrupt()` özelliği ile human-in-the-loop eklenebilir.

---

## 2. NVIDIA NeMo Guardrails — Detaylı Analiz

### Genel Bakış

NeMo Guardrails, LLM tabanlı uygulamalara **programlanabilir koruma katmanları** ekleyen açık kaynak bir toolkit. 5 tip guardrail sunar:

1. **Input rails** — Kullanıcı girdisini filtreler (injection, hassas veri maskeleme)
2. **Dialog rails** — Konuşma akışını kontrol eder (Colang DSL ile)
3. **Retrieval rails** — RAG senaryolarında chunk filtreleme
4. **Execution rails** — Tool giriş/çıkış kontrolü
5. **Output rails** — LLM çıktısını filtreler (hallucination, fact-check)

### Offline / Local Çalışma

**Evet, NeMo Guardrails Ollama ile offline çalışabilir.**

#### Konfigürasyon (config.yml):
```yaml
models:
  - type: main
    engine: ollama
    model: qwen3.6:27b    # veya herhangi bir lokal model
    parameters:
      base_url: http://localhost:11434
```

#### LangGraph Entegrasyonu:
```python
from langchain_ollama import ChatOllama
from nemoguardrails import RailsConfig
from nemoguardrails.integrations.langchain.runnable_rails import RunnableRails

# Local LLM
llm = ChatOllama(model="qwen3.6:27b", base_url="http://localhost:11434")

# Guardrails config
config = RailsConfig.from_path("./guardrails_config")

# RunnableRails — LangChain Runnable olarak kullanılabilir
guardrails = RunnableRails(config=config, llm=llm)
```

#### Colang ile Dialog Kontrolü:
```colang
define user ask about order
  "Siparişim nerede?"
  "Kargo durumu ne?"
  "Takip kodum SIP-..."

define user ask off topic
  "Python kodu yaz"
  "Hava durumu ne?"

define flow
  user ask off topic
  bot refuse off topic

define bot refuse off topic
  "Bu konuda size yardımcı olamıyorum. Sipariş, stok veya kargo ile ilgili sorular sorabilirsiniz."
```

### Bizim Sisteme Entegrasyon Planı

#### Seçenek A: RunnableRails ile Agent Wrapping
```python
# agent/graph.py içinde
from nemoguardrails.integrations.langchain.runnable_rails import RunnableRails

def agent_node(state):
    # Guardrails LLM'i wrap eder
    guarded_llm = RunnableRails(config=rails_config, llm=llm_with_tools)
    response = guarded_llm.invoke(state["messages"])
    return {"messages": [response]}
```

**Avantaj:** En temiz entegrasyon.
**Dezavantaj:** Her mesajda ek LLM çağrısı (guardrails kendi jailbreak check'i için).

#### Seçenek B: Hybrid (Önerilen)
```
Mesaj → Bizim Prompt Police (regex, 0ms, 0 maliyet)
     → NeMo Input Rail (Colang dialog kontrolü)
     → LangGraph Agent
     → NeMo Output Rail (hallucination check)
     → Yanıt
```

**Avantaj:** Regex ile ucuz ön filtreleme, NeMo ile sofistike kontrol.
**Dezavantaj:** NeMo'nun output rail'i ek latency ekler.

#### Seçenek C: NeMo Sadece Output Rail
```
Mesaj → Bizim Prompt Police (input)
     → LangGraph Agent
     → NeMo Output Rail (hallucination + fact check)
     → Yanıt
```

**Avantaj:** Input tarafında 0 ek maliyet, çıkışta kalite kontrolü.

### Kritik Uyarılar

| Konu | Detay |
|------|-------|
| **Beta durumu** | NeMo Guardrails hâlâ beta, production için önerilmiyor |
| **C++ bağımlılığı** | `annoy` kütüphanesi C++ derleyici gerektiriyor |
| **Prompt uyumu** | Varsayılan promptlar OpenAI için optimize, local modeller için override gerekli |
| **Latency** | Her guardrail check ~500ms+ ek latency (LLM call) |
| **Kaynak çekişmesi** | Aynı GPU'da hem agent hem guardrails LLM çalıştırmak VRAM sorununa yol açar |
| **Küçük model önerisi** | Guardrails için ayrı küçük model (qwen2.5:1.5b) kullanılması tavsiye edilir |

### Sonuç: NeMo Entegre Etmeli miyiz?

| Senaryo | Karar | Neden |
|---------|-------|-------|
| Hackathon demo | ❌ Hayır | Mevcut prompt police yeterli, ek complexity gereksiz |
| Production MVP | ⚠️ Belki | Output hallucination check değerli, ama beta riski var |
| Production v2+ | ✅ Evet | Colang ile dialog kontrolü + output rail çok güçlü |

**Pragmatik yaklaşım:** Şu an mevcut 3 katmanlı prompt police ile devam et. NeMo'yu output rail olarak eklemeyi production MVP'den sonra planla. Guardrails için küçük bir model (1.5B) ayır.

---

## 3. Maliyet Düşürme & Hız Artırma Stratejileri

### Mevcut Durum
- Her mesaj → LLM çağrısı → ~30-60 saniye (27B model, CPU/GPU)
- Her tool call → ek LLM çağrısı (tool result → final response)
- Prompt police: 0ms (regex)
- Auth check: 0ms (DB query)

### Strateji 1: Intent Classifier + Direct Tool Call (EN YÜKSEK ETKİ)

```
Müşteri: "2 numaralı siparişim nerede?"
         ↓
Intent Classifier (regex/keyword, ~1ms):
   intent = "siparis_durumu"
   entities = {siparis_no: 2}
         ↓
Direct Tool Call (LLM bypass, ~10ms):
   result = siparis_sorgula(siparis_no=2)
         ↓
Template Formatter (~0ms):
   "2 numaralı siparişiniz kargoda. Kargo: MNG-44512 (MNG Kargo)"
```

**Kazanım:** 30 saniye → 100ms. LLM çağrısı 0.

**Uygulama:**
```python
# agent/intent_classifier.py
import re

INTENT_PATTERNS = {
    "siparis_durumu": [
        r"(\d+)\s*(?:numaralı|nolu|no)\s*sipari[sş]",
        r"sipari[sş]i?m?\s*(?:nerede|durumu|ne\s*oldu)",
        r"(SIP-[A-Z0-9]{6})",
    ],
    "stok_kontrol": [
        r"(.+?)\s*(?:var\s*m[ıi]|stok|mevcut|kald[ıi]|fiyat)",
    ],
    "gunluk_ozet": [
        r"(?:bugün|günlük|durum|özet|rapor)",
    ],
    "kritik_stok": [
        r"(?:kritik|düşük|alarm|uyarı)\s*stok",
    ],
}
```

### Strateji 2: Response Cache

Aynı veya çok benzer sorulara cached yanıt dön.

```python
# Basit cache (TTL: 5 dakika)
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def cached_tool_response(tool_name, args_hash, ttl_bucket):
    return tool.invoke(args)
```

**Kazanım:** Tekrarlayan sorularda LLM çağrısı 0.

### Strateji 3: Lightweight Model

| Model | Boyut | Hız (token/s) | Kalite |
|-------|-------|---------------|--------|
| Qwen3.6:27B | 16GB | ~5-10 | ⭐⭐⭐⭐⭐ |
| Qwen2.5:7B | 4.5GB | ~30-50 | ⭐⭐⭐⭐ |
| Phi-3-mini:3.8B | 2.3GB | ~60-80 | ⭐⭐⭐ |
| Qwen2.5:1.5B | 1GB | ~100+ | ⭐⭐ (guardrails için) |

### Strateji 4: Hybrid Routing (Nihai Mimari)

```
Mesaj → Prompt Police (0ms)
     → Intent Classifier (1ms)
     ├── Basit sorgu → Direct Tool + Template (100ms) ← %70 trafik
     ├── SSS → FAQ Cache/RAG (50ms) ← %15 trafik
     └── Karmaşık → LangGraph Agent (30s) ← %15 trafik
```

**Toplam maliyet düşüşü:** ~%80 LLM çağrı azalması.

---

## 4. Özet & Öncelik Sırası

| Öncelik | Görev | Etki | Süre |
|---------|-------|------|------|
| 1 | Intent classifier + direct tool call | 🔥🔥🔥 Hız + maliyet | 1 gün |
| 2 | Response cache | 🔥🔥 Maliyet | 2 saat |
| 3 | Lightweight model testi (7B) | 🔥🔥 Hız | 1 saat |
| 4 | FAQ RAG sistemi | 🔥🔥 Hız + kalite | 2 gün |
| 5 | NeMo output rail (opsiyonel) | 🔥 Güvenlik | 1 gün |
| 6 | Multi-tenant config | 🔥 Ölçeklenme | 2 gün |
| 7 | WhatsApp entegrasyonu | 🔥 Kanal | 1 gün |
