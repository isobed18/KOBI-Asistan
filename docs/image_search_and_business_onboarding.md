# Image Search + Isletme Tipi Onboarding Plani

## Zor mu?

Hayir, ama iki seviyeye ayirmak gerekiyor.

### Seviye 1: Dusuk maliyetli demo/MVP

Musteri fotografi veya tarz tarifini metne ceviririz:

```text
"beyaz keten, uzun kollu, rahat kesim gomlek"
```

Sonra katalogdaki `visual_keywords`, `description`, `category`, `advisory_notes` alanlariyla eslestiririz.

Avantaj:
- Vision modeli gerekmez.
- LLM maliyeti yok veya cok dusuk.
- Hackathon videosunda cok net gorunur.
- Sales-agent reposundaki `search_by_image(image_description)` pattern'i ile ayni mantik.

Bu committe eklenen tool:

```text
urun_gorsel_ara(gorsel_aciklamasi, kategori="")
```

### Seviye 2: Gercek image search

Musteri Telegramdan fotograf atar.

Opsiyonlar:
1. Multimodal LLM ile fotografi 1-2 cumleye cevir.
2. CLIP / SigLIP embedding ile fotograf ve urun gorsellerini ayni vektor uzayinda ara.
3. Hazir urun gorselleri icin offline embedding index olustur.

Avantaj:
- Gercek fotografla calisir.

Dezavantaj:
- Daha fazla dependency.
- Daha fazla CPU/GPU/maliyet.
- Demo icin gerekli degil; MVP sonrasi.

## Bu Committe Eklenenler

Urun tablosuna:

- `image_url`
- `visual_keywords`

Tenant feature flag:

- `features.image_search`
- `features.product_advisory`

Business setup preset endpointleri:

```text
GET  /tenant-setup/business-types
POST /tenant-setup/preview
```

Isletme tipi presetleri:

- `giyim`: image search acik, beden/kalip/gorsel arama odakli
- `gida`: alerjen/icerik danismanligi odakli
- `cicek`: fotograf/tarzdan benzer buket bulma
- `genel`: temel urun danismanligi

## Video Demo Akisi

### Sahne 1: Ilk Kayit / Isletme Tipi

Ekranda anlatilacak:

1. Isletme sahibi ilk giriste isletme adini yazar.
2. Isletme tipini secer: `Giyim / Butik`.
3. Sistem sunlari otomatik onerir:
   - image search acik
   - beden rehberi alanlari
   - visual keywords
   - giyim agent kurallari

Backend demo endpoint:

```bash
curl http://localhost:8000/tenant-setup/business-types
```

Preview:

```bash
curl -X POST http://localhost:8000/tenant-setup/preview ^
  -H "Content-Type: application/json" ^
  -d "{\"business_name\":\"Mina Butik\",\"business_type\":\"giyim\",\"owner_notes\":\"Minimal keten ve basic urunler satiyoruz\"}"
```

### Sahne 2: Musteri Telegramdan Tarz Tarifi Yazar

Musteri:

```text
Buna benzer bir gomlek var mi? Beyaz keten, rahat kesim, yazlik bir sey ariyorum.
```

Beklenen davranis:

- Agent `urun_gorsel_ara` tool'unu cagirir.
- `Keten Gomlek` onerilir.
- Stok/fiyat/gorsel linki doner.
- Sonra beden sorarsa `urun_danismani` ile beden onerisi yapilir.

### Sahne 3: Gida Isletmesi

Isletme tipi `gida` secilirse image search cok kritik degil; asistan alerjen/icerik tarafinda guclenir.

Musteri:

```text
Cevize alerjim var, Ceviz Ici 500g sorun olur mu?
```

Beklenen:

- `urun_danismani` calisir.
- Ceviz/agac yemisi riski net soylenir.
- Tibbi kesinlik verilmez.

## LLM Tarafinda Eklenebilecek Yaratici Ozellikler

Maliyeti cok artirmadan:

1. **Gorselden benzer urun**
   - Dusuk maliyet: metin aciklama + visual keywords.
   - Ileri seviye: CLIP/SigLIP.

2. **Beden danismani**
   - Beden tablosu + musteri olculeri.
   - Giyim icin en iyi demo etkisi.

3. **Alerjen / icerik danismani**
   - Gida/kozmetik icin yuksek deger.
   - Guvenli cevap kurallari sart.

4. **Hediye danismani**
   - "Anneme 500 TL alti hediye" gibi.
   - Stok + fiyat + kategori ile LLM iyi calisir.

5. **Tamamlayici urun onerisi**
   - Sepet buyutme.
   - LLM yerine once kategori/tag eslestirme, sonra kisa LLM metni.

6. **Katalog eksigi yakalama**
   - Musteri "alerjen var mi?" sorar, urunde bilgi yoksa ticket/task ac.
   - Isletmeye: "Bu urunun alerjen bilgisi eksik, ekleyin."

7. **Isletme tipi bazli agent**
   - Giyim: beden, kombin, gorsel benzerlik.
   - Gida: alerjen, saklama, tarif/kullanim.
   - Cicek: renk, duygu, etkinlik, fotograf benzerligi.
   - Elektronik: uyumluluk, teknik ihtiyac, garanti.

## Sonraki Teknik Adimlar

1. Frontend ilk kayit ekranina `GET /tenant-setup/business-types` bagla.
2. Secilen isletme tipinden tenant config yazan kalici endpoint ekle.
3. Telegram photo handler:
   - Ilk MVP: fotograf gelirse "Kisaca tarif eder misiniz?" de.
   - Sonra multimodal provider varsa otomatik aciklama uret.
4. Urun gorselleri icin fake dataset:
   - Unsplash/Pexels URL'leri demo icin yeterli.
   - Productionda isletme kendi urun gorsellerini yuklemeli.
5. Daha sonra offline embedding index:
   - `product_image_embeddings` tablosu
   - CLIP/SigLIP encode
   - cosine similarity
