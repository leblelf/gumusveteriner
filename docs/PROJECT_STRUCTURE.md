# Proje Yapisi ve Dosyalar Ne Ise Yarar?

Bu dosya VS Code'da projeyi gezerken yol haritasi olsun diye yazildi. Kodlar tek tek ayrildi: backend, web arayuzu, web JavaScript, servisler ve Flutter admin uygulamasi.

```text
New project/
|-- app.py
|-- requirements.txt
|-- Procfile
|-- runtime.txt
|-- start.bat
|-- logo.jpeg
|-- data/
|   `-- gumus_veteriner.db
|-- templates/
|   `-- index.html
|-- static/
|   |-- css/
|   |   `-- style.css
|   `-- js/
|       `-- app.js
|-- services/
|   |-- sms_service.py
|   `-- email_service.py
|-- scripts/
|   `-- import_products.py
|-- docs/
|   `-- PROJECT_STRUCTURE.md
`-- gumusvet_admin/
    |-- pubspec.yaml
    |-- assets/images/logo.jpeg
    `-- lib/main.dart
```

## Backend: `app.py`

`app.py` projenin kalbidir.

- Flask uygulamasini baslatir: `app = Flask(...)`
- SQLite veritabanina baglanir.
- Tablolari olusturur.
- Web sitesini servis eder.
- API endpointlerini tanimlar.
- Render/Railway icin `PORT` ayarini kullanir.
- `robots.txt` ve `sitemap.xml` gibi SEO route'larini verir.

Kod icinde bolumler yorumlarla ayrildi:

- Ayarlar ve sabitler
- Veritabani baglantisi
- Tablo olusturma
- Eski handler uyumlulugu
- Flask route'lari
- Admin API'leri
- Deploy baslatma kodu

## Web Arayuzu: `templates/index.html`

Bu dosya web sitesinin gorunen HTML iskeletidir.

Tek sayfa uygulama gibi calisir. Yani farkli sayfalar ayri HTML dosyalari degil, ayni dosyada bolum bolum durur:

- Ana sayfa
- Hakkimizda
- Hizmetler
- Urunler
- Randevu al
- Giris / uye ol
- Profil
- Sepet / siparis / odeme
- Iletisim
- Tum yorumlar

JavaScript `go("sayfa")` fonksiyonu ile bu bolumleri acip kapatir.

## Tasarim: `static/css/style.css`

Sitenin gorunumu buradadir.

- Renk degiskenleri
- Karanlik mod
- Mobil uyum
- Navbar
- Hero alanlari
- Kartlar
- Giris animasyonlari
- Sepet paneli
- Profil ve siparis ekranlari

Renkleri degistirmek istersen once `:root` ve `[data-theme="dark"]` alanlarina bak.

## Web Etkilesimi: `static/js/app.js`

Sitenin tarayicida calisan mantigi buradadir.

- Sayfa gecisleri
- Urunleri API'den cekme
- Sepet islemleri
- Login / uye ol
- Profil, adres ve hayvan kaydi
- Randevu saatleri
- Siparis ve odeme akisi
- Yorum yapma
- Iletisim formu
- Mobil menu
- Karanlik mod

Bir buton calismiyorsa genelde once `templates/index.html` icindeki `onclick`, sonra `static/js/app.js` icindeki ilgili fonksiyon kontrol edilir.

## Servisler

### `services/sms_service.py`

SMS gonderme isi burada ayrildi. Boylece Netgsm bilgileri `app.py` icine karismaz.

- Telefonu dogrular.
- Mesaji kontrol eder.
- `.env` veya Render ortam degiskenlerini okur.
- Netgsm XML istegini gonderir.

### `services/email_service.py`

Mail gonderme isi burada durur.

- SMTP ayarlarini okur.
- Iletisim cevaplari ve siparis durumu maillerini gonderir.
- Hata olursa kullaniciya teknik traceback gostermeden sonuc dondurur.

## Flutter Admin: `gumusvet_admin/lib/main.dart`

Admin uygulamasi tek ana dosyada toplanmis durumda. Daha sonra istenirse ekranlar klasorlere ayrilabilir.

Ana bolumler:

- Uygulama girisi ve tema
- Login ekrani
- Admin shell ve sol menu
- Dashboard
- Randevular
- Pet listesi
- Yatan hastalar
- Urunler
- Siparisler
- Yorum cevaplama
- Iletisim sorulari
- Site yazilari
- Uyeler
- SMS gonderme
- Randevu saatleri

## Veritabani

Local veritabani:

```text
data/gumus_veteriner.db
```

Kod ilk calistiginda gerekli tablolar yoksa `app.py` tarafindan olusturulur. Render gibi canli ortamlarda SQLite dosyasi kalici disk baglanmadikca sifirlanabilir; uzun vadede PostgreSQL daha dogru olur.

## VS Code'da Nereye Bakmaliyim?

- Site tasarimi: `templates/index.html` + `static/css/style.css`
- Site butonlari ve islemleri: `static/js/app.js`
- API ve veritabani: `app.py`
- SMS / mail: `services/`
- Admin uygulamasi: `gumusvet_admin/lib/main.dart`

## Kisa Gelistirme Akisi

1. `app.py` calistirilir.
2. Web sitesi `http://localhost:5000` adresinden acilir.
3. Admin uygulamasi Flutter ile calistirilir.
4. Web sitesi ve admin uygulamasi ayni API'ye baglanir.
5. Degisiklik bittikten sonra GitHub'a push edilir.
