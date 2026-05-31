# Gümüş Veteriner Klinik Yönetim Sistemi

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

## Ortam Değişkenleri

Canlı ortamda hassas bilgiler koda yazılmaz. Render panelinden girilir.

Temel production ayarları:

```text
SECRET_KEY=
JWT_SECRET=
SITE_URL=https://wwwgumusvet.com
CORS_ORIGIN=https://wwwgumusvet.com
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=https://wwwgumusvet.com/login/google/authorized
```

İlk admin hesabı yalnızca ilk kurulumda Environment üzerinden oluşturulur:

```text
INITIAL_ADMIN_EMAIL=gumusveterinermuayenehanesi@gmail.com
INITIAL_ADMIN_PASSWORD=
```

İlk başarılı deploy sonrasında `INITIAL_ADMIN_PASSWORD` kaldırılabilir. Admin
şifresi kaynak kodda tutulmaz.

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

PostgreSQL ve bağlantı havuzu hazırlığı için:

```text
DATABASE_URL=
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

Tüm örnek değerler [`.env.example`](.env.example) dosyasında bulunur. Gerçek
`.env` dosyası GitHub'a gönderilmez.

## Güvenlik Kontrol Listesi

- `SECRET_KEY`, OAuth, SMTP ve SMS bilgileri Render Environment üzerinden okunur.
- Session cookie ayarları `Secure`, `HttpOnly` ve `SameSite=Lax` olarak çalışır.
- Login, Google OAuth, şifre sıfırlama ve admin API isteklerinde rate limit vardır.
- CSRF token kontrolü browser üzerinden gelen veri değiştiren API isteklerinde uygulanır.
- Güvenlik başlıkları Flask-Talisman ve ortak response katmanı tarafından eklenir.
- Admin dışındaki kullanıcılar JWT korumalı admin endpointlerine erişemez.
- Şifreler Werkzeug hash olarak, şifre sıfırlama tokenları SHA-256 olarak saklanır.
- Reset bağlantıları tek kullanımlıktır ve 30 dakika içinde geçerliliğini kaybeder.
- Upload doğrulaması yalnızca `jpg`, `jpeg`, `png`, `webp` ve `pdf` dosyalarına izin verir.
- Kaynak kod, `.env` ve SQLite dosyası web üzerinden servis edilmez.
- Kritik admin hareketleri `admin_audit_logs` tablosuna yazılır.

## Render Production Ayarları

Build Command:

```text
pip install -r requirements.txt
```

Start Command:

```text
gunicorn --workers 2 --threads 4 --bind 0.0.0.0:$PORT app:app
```

Health Check Path:

```text
/health
```

SQLite local geliştirme için çalışmaya devam eder. PostgreSQL bağlantı adresi
`DATABASE_URL` üzerinden okunur ve SQLAlchemy connection pool altyapısı hazırdır.
Mevcut eski SQLite handler sorgularının PostgreSQL'e tamamen taşınması ayrı bir
migration adımıdır. Bu migration tamamlanana kadar Render persistent disk ile
`data/gumus_veteriner.db` dosyasını kalıcı tutun.

## Cloudflare Güvenlik Ayarları

- SSL/TLS encryption mode: `Full`
- Bot Fight Mode: açık
- Security Level: `Medium`
- WAF ile `/api/admin/*` ve login endpointlerinde ek rate limit kuralı tanımlayın.
- Development Mode kapalı olsun.
- Cache Rule ile `/static/*` dosyalarını uzun süre cache'leyin.

## Görsel Optimizasyonu

- Büyük görselleri yüklemeden önce WebP formatına çevirin.
- Ana sayfa görsellerini mümkünse 300 KB altında tutun.
- Liste kartlarında tam boyutlu görsel yerine thumbnail kullanın.
- Cloudflare cache ve image optimization özelliklerini etkinleştirin.

## Veritabanı Yedekleme Planı

- SQLite kullanılırken Render persistent disk bağlayın ve `data/gumus_veteriner.db`
  dosyasını günlük olarak şifreli bir yedek alana kopyalayın.
- PostgreSQL migration sonrasında Render PostgreSQL backup özelliğini açın.
- Haftada bir kez yedekten geri yükleme testi yapın.
- Yedek dosyalarını GitHub'a eklemeyin.

## GitHub'a Gonderme

```powershell
git status
git add app.py templates/index.html static/css/style.css static/js/app.js services gumusvet_admin/lib/main.dart README.md docs/PROJECT_STRUCTURE.md
git commit -m "Document project structure and code flow"
git push origin main
```
