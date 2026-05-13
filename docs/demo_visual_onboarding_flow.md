# Demo Akisi: Gorsel Stok Yukleme ve Telegram Gorsel Arama

Bu akisin amaci KOBI sahibine su hissi vermek:

> Urunleri sisteme yukledim, sistem katalogu anladi; musteri gorsel atinca urunu buluyor ve siparise kadar ilerletiyor.

## 1. KOBI Girisi

1. Dashboard acilir.
2. KOBI sahibi admin hesabi ile giris yapar.
3. Sol menuden `Demo kurulum` acilir.

## 2. Isletme Turu Secimi

Demo icin `Clothing / boutique` secilir.

Bu secim backend tarafinda `business_type=giyim` olarak gider ve visual-stock servisi FashionCLIP modelini kullanir:

```text
FASHION_CLIP_MODEL=hf-hub:Marqo/marqo-fashionCLIP
```

## 3. Demo Fotograflari

Klasor:

```text
D:\projects\kobi_asistan\demo_assets\polyvore
```

Video icin onerilen temiz moda gorselleri:

```text
pieces-leather-boot-102049118_4.jpg
topshop-moto-vintage-boyfriend-jeans-100014086_2.jpg
givenchy-leather-medium-antigona-duffel-black-100002074_3.jpg
vintage-pearl-feather-earrings-100560058_7.jpg
long-sleeve-simple-blouse-100445477_1.jpg
red-tartan-check-skater-skirt-100361260_2.jpg
classic-flat-shoes-100566397_3.jpg
beige-crystal-sandals-100050716_2.jpg
```

Bu dosyalar toplu olarak surukle-birak alana atilir.

Eger klasor yoksa once:

```powershell
python scripts\prepare_polyvore_demo.py --count 15 --business-type giyim
```

## 4. FashionCLIP Siniflandirma

`Classify images` butonuna basilir.

Sistem her gorsel icin:

- urun adi
- kategori
- visual keywords
- confidence skoru
- taslak aciklama

uretir.

## 5. Urun Onayi

Her adayda fiyat, stok ve gerekiyorsa aciklama duzenlenir.

Kiyafet demo icin `Size guide` alanina ornek:

```text
S: 34-36, M: 38-40, L: 42-44. Regular fit. If between sizes, choose one size up.
```

`Approve product` butonu ile urun katalog tablosuna eklenir.

## 6. Telegram Musteri Videosu

Musteri Telegram'a urun gorseli gonderir.

Beklenen cevap:

```text
Gorselden en yakin urunu buldum:
#35 - Beige Crystal Sandals
Kategori: Shoes
Fiyat: 899.00 TL
Stok: 12
Benzerlik: %100

Bunu mu istiyorsunuz?
```

Butonlar:

- Sepete ekle
- Urun Listesi
- Sepetim

Siparis verme akisi LLM kullanmaz; mevcut button/FSM + stok kontrolu ile devam eder.

## 7. Beden Sorusu

Musteri gorsel aramadan sonra sunu yazar:

```text
Which size would fit me?
```

Bot son bulunan urunun `size_guide` alanini kullanarak template cevap verir. Bu hizli cevap LLM maliyeti yaratmaz.

## 8. Videoda Vurgulanacak Nokta

- KOBI sadece fotograflari yukler.
- Sistem katalog adaylarini kendisi olusturur.
- Musteri gorsel ile urun bulur.
- Siparis sepete butonlarla eklenir.
- Beden sorulari urun metadata'sindan yanitlanir.
- Daha yaratici, serbest urun danismanligi gerekiyorsa LLM devreye alinabilir; basit siparis akisi LLM'siz kalir.
