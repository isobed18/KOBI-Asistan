# AI Agent Onboarding Guide — revive.md

**Welcome, AI Code Agent.**  
Bu dokümanı ilk olarak oku. Projenin mevcut durumunu, mimarisini ve öncelikli hedefleri hızla kavramanı sağlar.

---

## Proje Amacı

KOBİ Asistan — küçük e-ticaret işletmeleri için sipariş, stok ve kargo yönetimini otomatize eden AI asistan. Hackathon prototipi olarak geliştirildi; gerçek dünya kullanımına göre tasarlandı.

**Temel tasarım prensibi:** LLM yalnızca "düşünme / özetleme / yaratıcılık" gerektiren yerlerde çağrılır. Basit sorgular (~%70-80) Intent Classifier ile LLM'siz, ~100ms yanıt süresinde halledilir.

---

## Mevcut Durum — v4.0

### Çalışan Bileşenler

| Bileşen | Durum | Notlar |
|---|---|---|
| FastAPI backend | ✅ | `uvicorn main:app --port 8000` |
| LangGraph ReAct agent | ✅ | Ollama (default) / OpenAI / Anthropic / Gemini |
| Prompt Police | ✅ | 3 katman regex, `agent/guard.py` |
| Auth (contextvars) | ✅ | `agent/auth.py` — telefon veya SIP-XXXXXX |
| Intent Classifier | ✅ | `agent/intent_classifier.py` — regex + 5dk cache |
| APScheduler | ✅ | sabah raporu, stok alarm, kargo gecikme |
| Telegram Bot | ✅ | `integrations/telegram_bot.py` — state machine, InlineKeyboard |
| React Dashboard | ✅ | `dashboard/` — 6 sayfa, 30s polling |
| Tickets sistemi | ✅ | `routers/tickets.py` + `tools/order_product_tools.py:create_ticket` |
| Reports sistemi | ✅ | `routers/reports.py` + `agent/llm_service.py` |
| Stock movements log | ✅ | `stock_movements` tablosu, `GET /products/{id}/movements` |

### Henüz Yapılmayan (Kritik)

1. **OTP doğrulaması** — İptal gibi geri dönüşü olmayan aksiyonlar için telefon/telegram/SMS kodu
2. **Ticket → yönetici Telegram bildirimi** — Bilet açılınca admin chat'e mesaj atılmıyor
3. **Sipariş tamamlanınca stok düşürmesi** — Şu an manuel `PATCH /products/{id}/stock` gerekiyor

---

## Kritik Dosyalar

### Başlamadan Önce Oku

```
agent/graph.py          — LangGraph state graph, tool bağlantıları, LLM factory
agent/auth.py           — contextvars scoping (set_session_scope, activate_scope, get_active_scope)
agent/guard.py          — Prompt Police, 3 katman
agent/intent_classifier.py — Classifier + cache + fast_response()
agent/scheduler.py      — APScheduler görevleri; sabah raporu raw_data içinde acik_biletler var
agent/llm_service.py    — _create_llm() factory, raporlama ve bilet LLM içeriği
tools/order_product_tools.py — Tüm DB-touching tools (siparis, stok, create_ticket)
tools/kargo_tools.py    — Kargo takip
integrations/telegram_bot.py — State machine (S_MENU, S_WAITING_PHONE, S_WAITING_ORDER, vb.)
```

---

## Mimari Kurallar

### 1. Auth Scope — Her Zaman Koru

DB'ye dokunan her yeni tool:
```python
from agent.auth import get_active_scope, check_order_access, get_customer_orders_filter
scope = get_active_scope()
```
- `scope.get("telefon")` veya `scope.get("takip_kodu")` varsa müşteri kimliği doğrulanmış.
- `scope` boşsa admin veya doğrulanmamış istek — hangi veriyi göstereceğine dikkat et.
- `check_order_access(order_dict)` → `(bool, reason)` döner.

### 2. LLM Factory — Her Zaman `_create_llm()` Kullan

`agent/graph.py` ve `agent/llm_service.py` içindeki `_create_llm()` factory'si `LLM_PROVIDER` env değişkenini okur. Doğrudan `ChatOllama()` veya `ChatOpenAI()` instantiate etme.

### 3. Intent Classifier Bypass

Yeni bir basit query tipi ekleyeceksen `INTENTS` dict'ine regex ekle, `fast_response()` içinde tool çağrısı ve format ekle. Bypass için `bypass_llm=True` döndür.

### 4. Scheduler — Dedup Kontrolü

Her scheduler görevi, aynı ürün/sipariş için bugün zaten açık bilet var mı kontrol eder:
```sql
WHERE type = 'stock_alert' AND related_product_id = ?
  AND status != 'resolved' AND DATE(created_at) = DATE('now', 'localtime')
```
Bu kontrolü koruyarak yeni scheduler görevleri yaz.

### 5. Kargo Gecikme — Template Kullan

`kargo_gecikme_kontrol()` → `_cargo_delay_template()` çağırır. LLM **değil**. Müşteri mesajı için boilerplate template yeterli; LLM'i boşa harcama.

### 6. Frontend Error Boundary

Her route `<ErrorBoundary>` ile sarılı (`App.jsx`). Yeni sayfa eklersen aynı kalıbı uygula. Overview'ın 30s polling'i backend down olduğunda error banner gösterir ama sayfayı patlatmaz.

---

## Veritabanı

```sql
products       (id, tenant_id, name, category, price, stock_quantity, low_stock_threshold, is_active)
orders         (id, tenant_id, tracking_code, customer_name, customer_phone, status, cargo_tracking_code, cargo_company, total_price)
order_items    (id, order_id, product_id, quantity, unit_price)
cargo_tracking (id, tracking_code, company, current_status, estimated_delivery, last_update)
tickets        (id, tenant_id, type, priority, status, title, description, llm_content, related_order_id, related_product_id, created_at, resolved_at)
daily_reports  (id, date, report_text, raw_data, created_at)
stock_movements (id, product_id, delta, reason, note, before_qty, after_qty, created_at)
```

`tenant_id DEFAULT 1` — tüm kritik tablolarda hazır, multi-tenant için kolon var ama şu an kullanılmıyor.

`llm_content` — JSON string. Cargo delay ticketlarında `{musteri_mesaji, ic_not}`, stock alert ticketlarında `{onerilen_miktar, tedarikci_emaili}`.

---

## Öncelikli Geliştirme Hedefleri

### Şimdi Yapılmalı

**1. OTP Auth — Sipariş İptal Doğrulaması**

`handle_message()` içinde `S_WAITING_CANCEL` state'inde, kullanıcı iptal talebini girdikten sonra:
1. Sistemin siparişteki `customer_phone`'a Telegram bot üzerinden 6 haneli rastgele kod göndermesi
2. Yeni state: `S_WAITING_OTP`
3. Kod eşleşirse `_llm()` çağrısıyla ticket oluştur

SMS seçeneği için Twilio veya Netgsm; E-posta için smtplib.

**2. Ticket → Telegram Bildirim**

`scheduler.py:_create_ticket_in_db()` sonrasında (ve `tools/order_product_tools.py:create_ticket` sonrasında):
```python
if telegram_app:
    await telegram_app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"🎫 Yeni Bilet #{ticket_id}: {title}")
```
`config.py`'a `TELEGRAM_ADMIN_CHAT_ID` ekle.

**3. Stok → Otomatik Düşürme**

`siparis_sorgula` veya sipariş durumu güncelleme akışında `stock_movements` tablosuna log yaz.

### Yakın Vadeli

- Analitik sayfası (Recharts, Task 6)
- FAQ/RAG (ChromaDB + statik fallback)
- Tedarikçi email gerçek gönderimi (SMTP)
- Rapor export (PDF/Excel)

### Uzun Vadeli

- WhatsApp Business API (bilet → WhatsApp thread)
- Multi-tenant (YAML config, row-level security)
- vLLM (Ollama yerine batched inference)
- NeMo Guardrails output rails

---

## Geliştirme Rehberi

### Backend Başlatma

```bash
cd D:\projects\kobi_asistan
uvicorn main:app --reload --port 8000
```

### Dashboard Başlatma

```bash
cd dashboard
npm run dev   # http://localhost:5173
```

Vite proxy `/dashboard`, `/tickets`, `/reports`, `/orders`, `/products`, `/api` → `localhost:8000` yönlendirir. Backend çalışmıyorsa ECONNREFUSED normal.

### Test Etme

```bash
# Sipariş sorgusu (LLM bypass test)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"mesaj": "2 numarali siparisim nerede?"}'
# tool_calls içinde siparis_sorgula görünmeli, LLM çağrılmamalı

# Dashboard stats
curl http://localhost:8000/dashboard/stats

# Ticket oluştur
curl -X POST http://localhost:8000/tickets/ \
  -H "Content-Type: application/json" \
  -d '{"type": "cancellation_request", "title": "Test", "description": "Test bilet"}'
```

### Yeni Tool Ekleme Kontrol Listesi

1. `tools/` altında `@tool` decorator ile fonksiyon yaz
2. `agent/auth.py`'den `get_active_scope()` çağır ve scope kontrolü yap
3. `agent/graph.py`'deki `ALL_TOOLS` listesine ekle
4. Basit bir query tipi ise `agent/intent_classifier.py`'e INTENTS + fast_response() ekle
5. Dashboard'da görünmesi gerekiyorsa ilgili router'a endpoint ekle

---

## Bilinen Sorunlar / Dikkat Edilecekler

- **SQLite concurrency** — APScheduler + FastAPI aynı anda yazıyorsa `get_connection()` her seferinde yeni connection açar; WAL mode düşünülmeli (yük artarsa).
- **Telegram state** — `context.user_data` in-memory; bot restart'ta state sıfırlanır. Redis backend eklenebilir.
- **Intent Classifier cache** — `_cache` dict in-memory; restart'ta sıfırlanır. Kabul edilebilir (5dk TTL zaten var).
- **LLM timeout** — Ollama lokal model yavaş başlayabilir. `llm_service.py` hata durumunda fallback metin döner.
