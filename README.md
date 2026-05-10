# KOBİ Asistan — AI-Powered Business Assistant

<div align="center">

**KOBİ'ler için yapay zeka destekli sipariş, stok ve kargo yönetim asistanı**

*LangGraph + Ollama + FastAPI + Telegram*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.1+-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-black?style=flat-square)](https://ollama.ai)

</div>

---

## Demo

### Web Chat UI — Multi-Step Tool Calling

![KOBİ Asistan Chat UI](docs/screenshots/chat_ui_demo.png)

> Agent, müşterinin "2 numaralı siparişim nerede?" sorusuna yanıt verirken önce `siparis_sorgula` tool'unu çağırıyor, kargo kodu bulunca otomatik olarak `kargo_takip` tool'unu da çağırıyor (multi-step reasoning). Tool çağrıları arayüzde şeffaf şekilde gösteriliyor.

---

## Özellikler

### AI Agent Yetenekleri
- **Sipariş sorgulama** — Sipariş no veya takip kodu (SIP-XXXXXX) ile detaylı sipariş bilgisi
- **Stok kontrolü** — Ürün adıyla arama, fiyat ve stok durumu
- **Kargo takibi** — Otomatik kargo kodu algılama ve durum sorgulama
- **Kritik stok uyarısı** — Eşik altındaki ürünlerin listesi
- **Günlük operasyonel özet** — Sipariş, gelir ve stok durumu raporu
- **Müşteri siparişleri** — Telefon numarasına bağlı tüm siparişler

### Güvenlik
- **3 katmanlı Prompt Police** — Injection, yasaklı konu ve konu uygunluğu kontrolü (0 maliyet, 0 latency)
- **Kod seviyesi müşteri auth** — Telefon veya takip kodu ile doğrulama, agent tool kullanımı scope ile kısıtlı
- **contextvars tabanlı scope** — Async-safe, per-request yetki izolasyonu

### Otomasyon (APScheduler)
- **Sabah raporu** — Her gün 08:00'de günlük özet + kritik stok
- **Stok alarmı** — 2 saatte bir kritik stok kontrolü
- **Kargo gecikme kontrolü** — 4 saatte bir kargodaki siparişlerin gecikme tespiti

### Entegrasyonlar
- **Web Chat UI** — Dark mode, SSE streaming, tool call görselleştirme
- **Telegram Bot** — Aynı process içinde async, auth-aware
- **REST API** — FastAPI + Swagger docs

---

## Mimari

```
                    ┌─────────────────────┐
                    │   Müşteri Mesajı     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Prompt Police     │  ← 3 katman (regex, 0 maliyet)
                    │   (guard.py)        │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Auth Middleware   │  ← Telefon / SIP-XXXXXX
                    │   (auth.py)        │
                    └──────────┬──────────┘
                               │
           ┌───────────────────▼───────────────────┐
           │         LangGraph StateGraph          │
           │                                       │
           │   START → [Agent Node] ⇄ [Tools] → END│
           │       ↕                    ↕          │
           │   System Prompt       6 Tool          │
           │   (auth-aware)                        │
           └───────────────────────────────────────┘
                    ↑                        ↑
      ┌─────────────┴──────┐    ┌────────────┴──────────────┐
      │  Channel Layer     │    │       Tool Registry        │
      │  • Web (SSE)       │    │  • siparis_sorgula         │
      │  • Telegram Bot    │    │  • musteri_siparisleri     │
      │  • REST API        │    │  • urun_stok_kontrol      │
      └────────────────────┘    │  • kritik_stok_listesi    │
                                │  • gunluk_ozet            │
      ┌─────────────────────┐   │  • kargo_takip            │
      │  APScheduler        │   └───────────────────────────┘
      │  • Sabah raporu     │            ↓
      │  • Stok alarm       │   ┌────────────────┐
      │  • Kargo kontrol    │   │  SQLite + Scope│
      └─────────────────────┘   └────────────────┘
```

---

## Tech Stack

| Katman | Teknoloji |
|--------|-----------|
| AI Agent | LangGraph (StateGraph + ToolNode) |
| LLM | **Ollama** (local) / **OpenAI** / **Google Gemini** / **Anthropic Claude** |
| Backend | FastAPI + Uvicorn |
| Database | SQLite |
| Auth | contextvars (async-safe per-request scope) |
| Security | 3-layer Prompt Police (regex, 0 cost) |
| Scheduler | APScheduler (AsyncIOScheduler) |
| Telegram | python-telegram-bot (async) |
| Config | Pydantic Settings + python-dotenv |

### Desteklenen LLM Provider'lar

| Provider | Model Örnekleri | API Key Gerekli | Local |
|----------|----------------|-----------------|-------|
| **Ollama** | Qwen3.6:27b, Gemma4:26b, Llama3 | ❌ Hayır | ✅ Tamamen offline |
| **OpenAI** | gpt-4o, gpt-4o-mini, gpt-3.5-turbo | ✅ `OPENAI_API_KEY` | ❌ Cloud |
| **Google Gemini** | gemini-2.0-flash, gemini-pro | ✅ `GOOGLE_API_KEY` | ❌ Cloud |
| **Anthropic Claude** | claude-sonnet-4-20250514, claude-haiku | ✅ `ANTHROPIC_API_KEY` | ❌ Cloud |

---

## Test Sonuçları

Tüm senaryolar başarıyla geçildi:

| # | Senaryo | Sonuç |
|---|---------|-------|
| 1 | Unrestricted sipariş sorgusu + kargo takibi | ✅ 2 tool çağrıldı (multi-step) |
| 2 | Telefon auth + **yetkisiz** başka müşteri siparişi | ✅ Reddedildi |
| 3 | Telefon auth + **yetkili** kendi siparişi | ✅ Gösterildi |
| 4 | Takip kodu auth (SIP-MD3R45) | ✅ Doğrudan erişim |
| 5 | Prompt injection ("Ignore all previous...") | ✅ Bloklandı |
| 6 | Off-topic mesaj (Python yazma isteği) | ✅ Bloklandı |
| 7 | Stok kontrolü ("Zeytinyağı var mı?") | ✅ Tool çağrıldı |
| 8 | Günlük özet + kritik stok (paralel tool) | ✅ 2 tool paralel |

### Örnek: Yetkisiz Erişim Bloklama

```
Mesaj: "2 numaralı siparişim nerede?"
Auth: telefon=05321234567 (Ayşe Kaya)
Sipariş #2: Mehmet Demir'e ait

Agent Yanıt: "2 numaralı siparişe erişim yetkim bulunmuyor,
çünkü bu sipariş doğrulanmış telefon numaranıza ait değil."
```

---

## Kurulum

### Gereksinimler
- Python 3.11+
- Aşağıdaki LLM seçeneklerinden **en az biri:**
  - [Ollama](https://ollama.ai) (local, ücretsiz) + bir model (`ollama pull qwen3.6:27b`)
  - OpenAI API Key
  - Google Gemini API Key
  - Anthropic Claude API Key

### Adımlar

```bash
# 1. Repoyu klonla
git clone https://github.com/Serkan0YLDZ/YZTA_Hackathon.git
cd YZTA_Hackathon
git checkout ai-agent

# 2. Virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

# 3. Bağımlılıklar
pip install -r requirements.txt

# 4. Ortam değişkenleri
cp .env.example .env
```

### LLM Provider Seçimi

`.env` dosyasında `LLM_PROVIDER` değişkenini ayarlayın:

**Seçenek A: Ollama (Local — ücretsiz, internet gereksiz)**
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.6:27b
```
> Ollama'nın çalıştığından emin olun: `ollama serve`

**Seçenek B: OpenAI**
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

**Seçenek C: Google Gemini**
```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=AIza...
GEMINI_MODEL=gemini-2.0-flash
```

**Seçenek D: Anthropic Claude**
```env
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-20250514
```

### Sunucuyu Başlat

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Erişim Noktaları
- **Chat UI:** http://localhost:8000/static/index.html
- **API Docs:** http://localhost:8000/docs
- **Bildirimler:** http://localhost:8000/api/v1/notifications

---

## API

### POST /api/v1/chat
```json
{
  "mesaj": "SIP-MD3R45 kodlu siparişim nerede?",
  "session_id": "optional-session-id",
  "telefon": "05334567890",
  "takip_kodu": "SIP-MD3R45"
}
```

### POST /api/v1/chat/stream
Aynı body, SSE streaming yanıt.

### GET /api/v1/notifications
APScheduler bildirim kuyruğu.

---

## Proje Yapısı

```
kobi_asistan/
├── main.py                     # FastAPI app + lifespan
├── config.py                   # Pydantic Settings
├── .env.example                # Ortam değişkenleri şablonu
├── requirements.txt
│
├── agent/
│   ├── graph.py                # LangGraph agent (auth-aware)
│   ├── prompt.py               # System prompts
│   ├── guard.py                # Prompt Police (3 katman)
│   ├── auth.py                 # Müşteri auth & scope
│   └── scheduler.py            # APScheduler (3 görev)
│
├── tools/
│   ├── order_product_tools.py  # Sipariş/stok/özet tools
│   └── kargo_tools.py          # Kargo takip tool
│
├── routers/
│   ├── chat.py                 # Chat API (auth + police + SSE)
│   ├── orders.py               # Sipariş CRUD
│   └── products.py             # Ürün CRUD
│
├── integrations/
│   └── telegram_bot.py         # Telegram bot
│
├── database/
│   ├── db.py                   # SQLite schema
│   ├── seed.py                 # Demo verisi
│   └── schemas.py              # Pydantic models
│
├── static/
│   └── index.html              # Web Chat UI
│
└── docs/
    ├── screenshots/            # Demo görselleri
    └── RESEARCH.md             # Araştırma raporu
```

---

## Araştırma & Gelecek Planlar

Detaylı araştırma raporu için bkz: [docs/RESEARCH.md](docs/RESEARCH.md)

### Kısa Vadeli
- [ ] Intent classifier ile LLM bypass (basit sorularda ~100ms yanıt)
- [ ] Response cache (aynı sorularda 0 maliyet)
- [ ] NeMo Guardrails entegrasyonu (Ollama ile offline)

### Orta Vadeli
- [ ] FAQ RAG sistemi (vektör DB, sık sorulan sorular)
- [ ] Lightweight model geçişi (Qwen2.5:7B)
- [ ] WhatsApp entegrasyonu

### Uzun Vadeli
- [ ] Fine-tuned intent classifier (BERT/DistilBERT)
- [ ] Multi-tenant YAML config (çoklu işletme desteği)
- [ ] vLLM geçişi (production)
- [ ] Docker Compose deployment

---

## Lisans

MIT
