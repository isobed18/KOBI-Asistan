# Demo Hesapları

Bu hesaplar demo videosunda boş ekran göstermemek için hazırlanır.

Önce seed:

```powershell
python scripts\seed_demo_tenants.py
```

## Varsayılan Admin

- Kullanıcı adı: `admin`
- Şifre: `admin123`
- Tenant: `1`
- Not: Silinmedi, geliştirme hesabı olarak duruyor.

## Giyim / Butik

- İşletme: `Mina Butik`
- Kullanıcı adı: `mina_butik`
- Şifre: `demo1234`
- Tenant: `2`
- İçerik: Polyvore kaynaklı 10 moda ürünü, görseller, stoklar, siparişler, kargolar, müdahale kayıtları.

## Gıda / Paketli Ürün

- İşletme: `Doğal Lezzetler`
- Kullanıcı adı: `dogal_lezzetler`
- Şifre: `demo1234`
- Tenant: `3`
- İçerik: Paketli gıda ürünleri, içerik/alerjen alanları, stoklar, siparişler, kargolar, müdahale kayıtları.

## Çiçek / Hediye

- İşletme: `Laluna Çiçek`
- Kullanıcı adı: `laluna_cicek`
- Şifre: `demo1234`
- Tenant: `4`
- İçerik: Çiçek ve hediye ürünleri, görseller, stoklar, siparişler, kargolar, müdahale kayıtları.

## Video Akışı Notu

1. İlk sahnede `/register` açılır.
2. KOBİ işletme türünü ve müşteri iletişim kurallarını yazar.
3. Ürün fotoğrafı yükleme adımı gösterilir.
4. Video kesilir.
5. Hazır veri dolu `mina_butik / demo1234` hesabına geçilir.
6. Günün özeti, stoklar, siparişler, kargolar, raporlar ve müdahale sayfaları gezdirilir.
7. Telegram tarafında müşteri görsel gönderir, ürün bulunur, beden sorar, sepete ekler.
8. İptal talebi müdahale kaydına düşürülür.
