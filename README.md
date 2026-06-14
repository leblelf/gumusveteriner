# Gümüş Veteriner Klinik Yönetim Sistemi

Gümüş Veteriner için geliştirilen sistem iki parçadan oluşur:

1. Flask tabanlı müşteri web sitesi ve REST API
2. Flutter tabanlı Windows, Android ve iOS admin uygulaması

Web sitesi; üyelik, Google ile giriş, profil, pet sağlık dosyası, randevu, ürün,
sepet, sipariş, yorum, bildirim ve iletişim işlemlerini sunar. Admin uygulaması;
pet, yatış, randevu, stok, sipariş, müşteri, yorum, soru, SMS ve site içeriği
yönetimini aynı PostgreSQL veritabanı üzerinden gerçekleştirir.

## Hızlı Başlangıç

Web sitesini yerelde çalıştırmak:

```powershell
cd "C:\Users\ghost\Documents\New project"
python -m pip install -r requirements.txt
python app.py
```

Adres: `http://localhost:5000`

Admin uygulamasını çalıştırmak:

```powershell
cd "C:\Users\ghost\Documents\New project\gumusvet_admin"
C:\flutter\flutter\bin\flutter.bat pub get
C:\flutter\flutter\bin\flutter.bat run -d windows
```

Windows release ve taşınabilir ZIP paketi:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_windows.ps1
```

Paket `dist\GumusVetAdmin-Windows.zip` konumunda oluşur.

## Proje Belgeleri

- [İhtiyaç Analizi](docs/IHTIYAC_ANALIZI.md)
- [Kullanım Kılavuzu](docs/KULLANIM_KILAVUZU.md)
- [Değerlendirme Kriterleri Raporu](docs/DEGERLENDIRME_RAPORU.md)
- [Proje Yapısı](docs/PROJECT_STRUCTURE.md)
- [Production Güvenliği](docs/production_security.md)

Admin uygulamasında ayrıca sol menüde **Yardım & Kullanım** ekranı bulunur.
Müşteri sitesindeki **Yardım Merkezi** temel işlemleri açıklar.

## Production

Render Build Command:

```text
pip install -r requirements.txt
```

Render Start Command:

```text
gunicorn --workers 2 --threads 4 --bind 0.0.0.0:$PORT app:app
```

Health Check: `/health`

Production ortamında `DATABASE_URL` tanımlanmalı ve PostgreSQL kullanılmalıdır.
Gizli bilgiler `.env` dosyasına veya Render Environment alanına yazılır; kaynak
koda eklenmez.

## Environment Variables

Production değerleri yalnızca Render Dashboard > Environment bölümünde
tanımlanmalıdır. `.env` dosyası ve gerçek değerler GitHub'a gönderilmez.
`.env.example` yalnız değişken adlarını gösterir.

```text
SECRET_KEY=
JWT_SECRET=
DATABASE_URL=
MIGRATION_DATABASE_URL=
SITE_URL=
CORS_ORIGIN=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GMAIL_REFRESH_TOKEN=
GOOGLE_REDIRECT_URI=
MAIL_PROVIDER=
SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_TLS=
SMTP_TEST_RECIPIENT=
DEBUG_MAIL_TEST=
SMS_PROVIDER=
NETGSM_USERCODE=
NETGSM_PASSWORD=
NETGSM_HEADER=
INITIAL_ADMIN_EMAIL=
INITIAL_ADMIN_PASSWORD=
RATELIMIT_STORAGE_URI=
```

Gmail gönderimi için `SMTP_PASSWORD` alanına normal Gmail şifresi değil,
Google hesabından üretilen App Password yazılmalıdır. Bu değer README,
ekran görüntüsü, test dosyası veya commit mesajında paylaşılmamalıdır.

Mail sistemi `services/mail_service.py` içindedir. Şifre sıfırlama, randevu
durumu ve sipariş/kargo durumu e-postaları aynı Gmail SMTP bağlantısını
kullanır. SMTP hataları ana işlemi geri almaz; ayrıntı Render loglarına yazılır.

## Test ve Kontrol

```powershell
python -m py_compile app.py services\postgres_adapter.py
python -m unittest tests.test_backend -v
C:\flutter\flutter\bin\dart.bat analyze gumusvet_admin\lib
cd gumusvet_admin
C:\flutter\flutter\bin\flutter.bat test
```

Canlı kontroller:

- `https://wwwgumusvet.com/health`
- `https://wwwgumusvet.com/api/health`

## Güvenlik Özeti

- Şifreler hash olarak saklanır.
- Admin API, JWT ile korunur.
- Tarayıcı formlarında CSRF doğrulaması vardır.
- Login ve API endpointlerinde rate limit uygulanır.
- SQL sorguları parametreli çalışır.
- Session cookie ayarları Secure, HttpOnly ve SameSite=Lax kullanır.
- Hassas anahtarlar GitHub’a gönderilmez.
- Kritik admin işlemleri audit log tablosuna yazılır.
