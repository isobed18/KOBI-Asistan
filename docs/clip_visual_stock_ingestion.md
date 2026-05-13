# CLIP Tabanli Gorsel Stok Ekleme ve Gorsel Arama

Bu branch yeni buyuk ozelligin ilk calisir cekirdegini ekler.

## Hedef

KOBI kayit/onboarding sirasinda veya daha sonra toplu urun gorselleri yukler.
Sistem:

1. Isletme tipine gore uygun classifier modunu secer.
2. Gorselleri tek tek taslak urun adayina cevirir.
3. Isim, kategori, keyword, aciklama ve stok icin oneri uretir.
4. KOBI sahibi her adayi duzenler, onaylar veya reddeder.
5. Onaylanan aday `products` tablosuna eklenir.
6. Gorsel embedding/keyword bilgisi kaydedilir.
7. Musterinin attigi gorsel veya gorsel tarifiyle benzer urun aranabilir.

## Maliyet Stratejisi

Ozellik iki katmanli tasarlandi:

### 1. Fallback / demo modu

- Model yuklenmez.
- Dosya adi + isletme tipi + keyword presetleri kullanilir.
- Maliyet sifir.
- Her makinede calisir.

Ornek dosya adlari:

```text
beyaz-keten-gomlek.jpg
siyah-oversize-tshirt.png
kirmizi-gul-buket.jpeg
```

### 2. CLIP modu

`sentence-transformers` ve `Pillow` kuruluysa servis otomatik model yuklemeyi dener.

Giyim / butik icin once:

```text
FASHION_CLIP_MODEL=Marqo/marqo-fashionCLIP
```

denenir. Yuklenemezse genel CLIP'e duser:

```text
GENERAL_CLIP_MODEL=sentence-transformers/clip-ViT-B-32
```

modelini yuklemeyi dener. Basarirsa image embedding uretir ve SQLite icinde
`product_image_embeddings.embedding_json` alanina yazar.

Not:
- FashionCLIP sadece `business_type=giyim` icin denenir.
- Model indirilemez/yuklenemezse sistem demo fallback moduna duser ve akisi bozmaz.

## Eklenen DB Tablolari

```text
visual_stock_batches
visual_stock_candidates
product_image_embeddings
```

## Eklenen Endpointler

Tum endpointler admin JWT ister.

### Capabilities

```http
GET /visual-stock/capabilities
```

### Batch upload

```http
POST /visual-stock/batches
Content-Type: multipart/form-data

business_type=giyim
files=@beyaz-keten-gomlek.jpg
files=@siyah-oversize-tshirt.png
```

Donus:

```json
{
  "batch_id": 1,
  "status": "pending_review",
  "candidate_count": 2,
  "candidates": []
}
```

### Batch adaylarini getir

```http
GET /visual-stock/batches/{batch_id}
```

### Aday onayla

```http
POST /visual-stock/candidates/{candidate_id}/approve
Content-Type: application/json

{
  "name": "Keten Gomlek",
  "category": "Giyim",
  "price": 890,
  "stock_quantity": 12,
  "low_stock_threshold": 4,
  "visual_keywords": "beyaz keten yazlik rahat gomlek",
  "description": "Yazlik keten gomlek"
}
```

### Aday reddet

```http
POST /visual-stock/candidates/{candidate_id}/reject
Content-Type: application/json

{
  "reason": "Urun fotografi net degil"
}
```

### Musteri gorsel arama

```http
POST /visual-stock/search
Content-Type: multipart/form-data

business_type=giyim
file=@musteri-gorseli.jpg
```

Eger embedding varsa `clip_embedding`, yoksa `keyword_fallback` modunda sonuc doner.

## Demo Video Akisi

1. KOBI ilk kurulumda isletme tipini secer: `Giyim / Butik`.
2. "Urun fotograflarini yukle" ekrani acilir.
3. 3-5 kiyafet fotografi surukle-birak yapilir.
4. Sistem her fotograf icin taslak uretir:
   - isim
   - kategori
   - visual keywords
   - stok varsayimi
   - aciklama
5. KOBI sahibi fiyat/stok bilgisini girer.
6. Onayla der.
7. Urun katalogda gorunur.
8. Musteri Telegramdan benzer bir gorsel atar veya tarif eder.
9. Sistem katalogdaki benzer urunu bulur ve gorseliyle onerir.

## Sonraki Adimlar

1. Frontend onboarding ekranina `/tenant-setup/business-types` ve `/visual-stock/batches` bagla.
2. Batch adaylari icin approve/reject UI ekle.
3. Telegram photo handler:
   - once `visual-stock/search` altyapisina baglanacak.
   - multimodal LLM varsa fotograf aciklamasi uretilecek.
4. FashionCLIP modeli icin opsiyonel model preset:
   - giyim tenantlari icin FashionCLIP
   - cicek/gida/genel icin CLIP/SigLIP
5. SQLite embedding yerine ileride ChromaDB/Faiss/pgvector.
