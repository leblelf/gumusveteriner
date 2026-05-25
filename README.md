# Gumus Veteriner Klinik Yonetim Sistemi

Bu proje iki parcadan olusur:

1. **Flask web sitesi ve API**  
   Musteri tarafinda randevu, urun, sepet, yorum, iletisim, uye girisi ve profil islemlerini calistirir.

2. **Flutter admin uygulamasi**  
   Klinik yoneticisinin randevu, urun, siparis, kullanici, yorum, SMS ve yatan hasta islemlerini yonetmesi icin hazirlanmistir.

Kodlari VS Code'da okurken once bu dosyaya, sonra `docs/PROJECT_STRUCTURE.md` dosyasina bakman yeterli olur.

## Hizli Calistirma

Web sitesini localde calistirmak icin:

```powershell
cd "C:\Users\ghost\Documents\New project"
python app.py
```

Sonra tarayicidan:

```text
http://localhost:5000
```

Admin uygulamasini calistirmak icin:

```powershell
cd "C:\Users\ghost\Documents\New project\gumusvet_admin"
C:\flutter\flutter\bin\flutter.bat run -d windows
```

## En Onemli Dosyalar

- `app.py`  
  Flask sunucusu, API endpointleri, veritabani tablolari ve deploy ayarlari burada.

- `templates/index.html`  
  Web sitesinin HTML iskeleti. Sayfalar tek dosyada bolum bolum durur.

- `static/css/style.css`  
  Web sitesinin tum tasarimi, renkleri, mobil gorunumu, karanlik modu ve sepet paneli.

- `static/js/app.js`  
  Web sitesinin calisan tarafi: sepet, login, profil, randevu, siparis, yorum, sayfa gecisleri.

- `data/gumus_veteriner.db`  
  SQLite veritabani. Localde kayitlar burada tutulur.

- `services/sms_service.py`  
  Netgsm SMS entegrasyonu.

- `services/email_service.py`  
  SMTP ile mail gonderme islemleri.

- `gumusvet_admin/lib/main.dart`  
  Flutter admin uygulamasinin ana kodu. Ekranlar ve yonetim sayfalari burada.

## Deploy Notlari

Render / Railway gibi ortamlarda baslangic komutu:

```text
gunicorn app:app
```

Gerekli dosyalar:

- `requirements.txt`
- `Procfile`
- `runtime.txt`
- `app.py`
- `templates/`
- `static/`
- `services/`

## Ortam Degiskenleri

Canli ortamda hassas bilgiler koda yazilmaz. Render panelinden girilir.

SMS icin:

```text
SMS_PROVIDER=netgsm
NETGSM_USERCODE=
NETGSM_PASSWORD=
NETGSM_HEADER=
```

Mail icin:

```text
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_TLS=true
```

JWT icin:

```text
JWT_SECRET=
```

## GitHub'a Gonderme

```powershell
git status
git add app.py templates/index.html static/css/style.css static/js/app.js services gumusvet_admin/lib/main.dart README.md docs/PROJECT_STRUCTURE.md
git commit -m "Document project structure and code flow"
git push origin main
```
