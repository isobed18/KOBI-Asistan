# Phase 1 Kalan Isler

Bu dosya token/kapsam sinirina gelindigi noktada birakilan islerin net devam planidir. Mevcut commit calisir iskelet olarak tutuldu; asagidaki maddeler sirayla tamamlanmali.

## Bu committe tamamlanan ana parcalar

1. Sales-agent reposu proje disinda `C:\tmp\langgraph-sales-agent` altina clone edilip incelendi.
2. Tenant-aware graph yaklasimi guclendirildi:
   - `agent/graph.py` tenant configten LLM provider/model/temperature okuyor.
   - `tenant_id`, `channel`, `channel_user_id` runtime context olarak tasiniyor.
   - OTP zorunlulugu sistem promptuna eklendi.
3. Repository pattern baslatildi:
   - `repositories/products.py`
   - `repositories/orders.py`
   - `repositories/tickets.py`
   - `repositories/base.py`
4. Admin stock tools repository katmanina tasindi:
   - fuzzy urun arama
   - stok guncelleme
   - toplu stok guncelleme
   - stock_movements logu
5. Siparis durum eventi merkezi repository katmanina alindi:
   - `kargoda`, `teslim_edildi`, `tamamlandi` durumlarinda stok dusme
   - stock_movements logu
   - tekrar stok dusmeyi engelleyen basit dedupe
6. OTP iskeleti eklendi:
   - `agent/otp.py`
   - `otp_challenges` tablosu
   - musteri iptal akisi icin OTP olusturma/dogrulama tool'lari
7. Ticket olusturma repository katmanina baslatildi:
   - yeni ticket olusunca notifier cagrisi
   - basit dedupe opsiyonu
8. Intent classifier embedding similarity icin opsiyonel sentence-transformers destegi kazandi; kutuphane yoksa difflib fallback var.

## Hemen Devam Edilecek Isler

### 1. OTP akisini Telegram bot state machine'e bagla

Durum:
- Backend OTP helper ve tool'lari var.
- Telegram'a musteri mesaj gonderme helper'i var.

Yapilacak:
1. `integrations/telegram_bot.py` icinde iptal seceneginde direkt ticket acma yerine `siparis_iptal_otp_gonder` akisini baslat.
2. Kullanici OTP kodu yazdiginda `siparis_iptal_otp_dogrula_ve_bilet_ac` calissin.
3. Basarisiz OTP denemelerinde kalan hak kullaniciya bildirilsin.
4. OTP dogrulanmadan cancellation_request ticket acilamadigini test et.

### 2. Customer graph OTP davranisini test et

Yapilacak:
1. Web chat veya Telegramdan "siparisimi iptal etmek istiyorum" senaryosu calistir.
2. Agent'in once OTP tool'una gittigini dogrula.
3. OTP dogrulaninca ticket acildigini dogrula.
4. `create_ticket(type="cancellation_request")` direkt cagrilinca hata dondugunu dogrula.

### 3. Router ticket olusturmayi repository katmanina al

Durum:
- Tool tarafinda repository kullaniliyor.
- `routers/tickets.py` hala direkt SQL ile insert yapiyor.

Yapilacak:
1. `routers/tickets.py` POST endpointini `repositories.tickets.create_ticket` kullanacak sekilde sadeleştir.
2. Manuel ticket acilisinda dashboard + Telegram bildirimi gittigini test et.

### 4. Tenant isolation'i routerlara yay

Durum:
- Agent ve admin graph tenant-aware.
- Bazi routerlar hala `tenant_id=1` varsayimi ile calisiyor.

Yapilacak:
1. Auth token icinden tenant_id okuma helper'i yaz.
2. `orders`, `products`, `tickets`, `dashboard`, `reports` endpointlerinde tenant filter zorunlu hale gelsin.
3. Test icin ikinci tenant config ve dummy data ekle.

### 5. Repository pattern'i tamamla

Yapilacak:
1. `repositories/products.py` icine listeleme, detay, hareket gecmisi fonksiyonlari ekle.
2. `repositories/orders.py` icine create/list/detail fonksiyonlari ekle.
3. `repositories/tickets.py` icine list/detail/update_status fonksiyonlari ekle.
4. Router ve tools icindeki tekrar SQL'leri bu repositorylere tası.

### 6. Scheduler job'larini repository + tenant aware yap

Durum:
- Scheduler calisiyor fakat SQL'ler tenant filtresi ve repository pattern acisindan karisik.

Yapilacak:
1. Her scheduler job tenant listesi uzerinden donsun.
2. Her tenant icin ayri daily report uretsin.
3. Deduplication keylerine tenant_id dahil edilsin.
4. AI actionable tasks JSON'u daily report raw_data icine yazilsin.

### 7. Intent classifier production temizligi

Durum:
- Regex + optional embedding eklendi.
- Model lazy load ediliyor; ilk cagri agir olabilir.

Yapilacak:
1. Embedding classifier feature flag ile acilip kapansin.
2. Sentence-transformers yoksa log seviyesi debug olsun, kullanici akisi etkilenmesin.
3. Intent benchmark icin 30-50 ornek cumlelik test dosyasi yaz.
4. Basit sorgularda hedef: %80+ LLM bypass, dusuk false-positive.

### 8. Smoke test listesi

Commit sonrasi sirayla calistir:

```bash
python -m compileall agent tools repositories routers database integrations
python -c "from database.db import init_db; init_db()"
python -c "from agent.graph import agent_graph; from agent.admin_graph import admin_graph; print('graphs ok')"
uvicorn main:app --reload --port 8000
```

Dashboard icin:

```bash
cd dashboard
npm install
npm run build
npm run dev
```

## Risk Notlari

1. `requirements.txt` icine `sentence-transformers` eklendi. Bu paket agir olabilir. Hackathon demosunda sorun yaratirsa feature flag ile opsiyonel hale getirilmeli veya requirements'tan cikarilip "optional" kuruluma alinmali.
2. SQLite migration hafif `ALTER TABLE` mantigi ile gidiyor. Production icin Alembic gerekli.
3. OTP kodu Telegram gonderilemezse tool debug amacli kodu response icinde donduruyor. Bu sadece local/demo icin kabul edilebilir; productionda kesinlikle kaldirilmali.
4. Siparis stok dusme dedupe su an reason text uzerinden yapiliyor. Daha saglam cozum icin `order_stock_events` tablosu eklenmeli.
