# Demo: Musteri Tarafi Yaratici LLM Cevaplari

Bu demo frontend tasarimina dokunmadan customer-agent tarafindaki katma degeri gostermek icin hazirlandi.

## Eklenen Ozellik

Customer-agent artik klasik "stok var mi?" cevabinin otesinde urun detay metadatasina gore danismanlik yapabilir:

- Beden / olcu onerisi
- Alerjen / icerik uygunluk degerlendirmesi
- Kullanim amaci ve hediye onerisi
- Urun detaylari eksikse bunu durustce belirtme

Yeni tool:

```text
urun_danismani(urun_adi, soru, musteri_olculeri, alerjiler, kullanim_amaci)
```

Urun tablosuna eklenen opsiyonel alanlar:

- `description`
- `ingredients`
- `allergens`
- `size_guide`
- `advisory_notes`

## Sales Agent Reposundan Ilham

Inceledigimiz `https://github.com/yerdaulet-damir/langgraph-sales-agent` reposunda en yakin pattern sunlardi:

1. `search_products`: Musteri katalogtan urun sordugunda agent once gercek katalog tool'una gider.
2. `search_by_image`: Musterinin tarif ettigi/gosterdigi seye benzer urun bulma fikri.
3. Tenant-specific product catalog: Her isletmenin kendi urun bilgisine dayali cevap.
4. Channel adapter: Telegram/Web/WhatsApp kanallari ayni agent davranisini kullanabilir.

Biz bunu KOBI Asistan'a su sekilde uyarladik:

- Agent urun uygunlugu sorularinda tahminini genel bilgiden degil, isletmenin urun metadata'sindan yapar.
- Metadata yoksa "bu bilgi isletme tarafindan eklenmemis" der.
- Alerjen sorularinda kesin tibbi tavsiye vermez; urun icerigi + etiket/doktor uyarisi ile cevaplar.

## Video Akisi 1: Beden Danismanligi

Amaç: "Klasik chatbot degil, satis danismani gibi davranıyor" hissi.

1. Dashboard veya DB'de urun detayini goster:
   - Urun: `Keten Gomlek`
   - `size_guide`: S/M/L/XL gogus ve omuz olculeri.
   - `advisory_notes`: Keten kumas icin rahat beden onerisi.

2. Telegramda musteri su mesaji yazar:

```text
Keten gomlek hangi bedeni bana olur? Gogsum 101 cm, omuzum 42 cm.
```

3. Beklenen cevap davranisi:
   - Agent `urun_danismani` tool'unu kullanir.
   - M bedenin teknik olarak uyabilecegini, rahat durus icin L bedenin daha guvenli olabilecegini soyler.
   - Cevap kesin degil, olcuye dayali ve satis danismani tonundadir.

4. Videoda vurgulanacak cumle:

```text
Sistem sadece stok soylemiyor; isletmenin girdigi beden tablosuna gore musteriye satis danismanligi yapiyor.
```

## Video Akisi 2: Alerjen / Icerik Danismanligi

Amaç: Gida satan KOBI icin 7/24 dogal dilde guvenli musteri iletisimi.

1. Urun detayini goster:
   - Urun: `Ceviz Ici 500g`
   - `ingredients`: Ceviz ici.
   - `allergens`: Ceviz/agac yemisi, capraz bulasma bilgisi.

2. Telegramda musteri su mesaji yazar:

```text
Cevize alerjim var. Ceviz ici 500g benim icin sorun olur mu?
```

3. Beklenen cevap davranisi:
   - Agent `urun_danismani` tool'unu kullanir.
   - Urunun ceviz/agac yemisi alerjeni icerdiğini net soyler.
   - "Bu urunu onermem, etiket ve doktor tavsiyesi onemli" gibi guvenli cevap verir.
   - Kesin tibbi guvence vermez.

4. Videoda vurgulanacak cumle:

```text
AI, urun icerigini okuyup riskli durumda satisi zorlamiyor; guvenli ve seffaf cevap veriyor.
```

## Video Akisi 3: Eksik Bilgi Varsa Durust Cevap

Amaç: Hallucination yapmadigini gostermek.

Telegram mesaji:

```text
Organik domates glutensiz mi, alerjen var mi?
```

Beklenen davranis:

- Eger urunde `ingredients/allergens` alani yoksa agent bunu belirtir.
- "Bu bilgi isletme tarafindan eklenmemis; kesin cevap icin etiket veya isletme dogrulamasi gerekir" der.

Videoda vurgulanacak cumle:

```text
Bilgi yoksa uydurmuyor; eksik katalog bilgisini isletmeye aksiyon olarak geri dondurebiliriz.
```

## Eklenebilecek Yaratici LLM Cevap Fikirleri

Kisa vadede en iyi demo etkisi verecek fikirler:

1. **Beden / olcu danismani**
   - Giyim, ayakkabi, aksesuar.
   - Musteri olculerini yazar, agent urun beden tablosuna gore onerir.

2. **Alerjen / diyet uygunluk danismani**
   - Gida, kozmetik, bebek urunleri.
   - Vegan, glutensiz, laktozsuz, seker ilavesiz, kuruyemis alerjisi gibi sorular.

3. **Kullanim amaci eslestirme**
   - "Kahvalti icin hangi bal daha iyi?"
   - "Etkinlik icin 30 kisilik atistirmalik ne onerirsiniz?"

4. **Hediye danismani**
   - "Anneme dogum gunu hediyesi ne alayim?"
   - Agent stok, fiyat ve kategoriye gore 2-3 secenek onerir.

5. **Tamamlayici urun onerisi**
   - "Ceviz aliyorum, yanina ne iyi gider?"
   - Sepet buyutme icin dusuk riskli upsell.

6. **Bakim / saklama onerisi**
   - "Bu gomlek nasil yikanir?"
   - "Bal neden kristallesti?"

7. **Riskli durumda ticket**
   - Musteri "alerjim var ama yine de alayim mi?" derse agent satisi zorlamaz.
   - Istenirse `create_ticket` ile insan incelemesine aktarilir.

## Demo Komutlari

DB migration ve demo metadata:

```bash
python -c "from database.db import init_db; init_db()"
```

Backend:

```bash
uvicorn main:app --reload --port 8000
```

Telegram bot aktifse:

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
```

## Not

Bu ozellik urun metadata'sina dayanir. Isletme urun detaylarini ne kadar iyi girerse customer-agent cevabi o kadar etkileyici olur.
