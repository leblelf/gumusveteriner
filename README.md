# Gümüş Veteriner Klinik Yönetim Sistemi

Bu repo, Gümüş Veteriner için hazırlanan yerel Python prototipidir.

## Python ile çalıştırma

En kolay yol:

1. `start.bat` dosyasına çift tıkla.
2. Terminal penceresi açık kalsın.
3. Tarayıcıdan `http://localhost:8000` adresini aç.

PowerShell ile çalıştırmak istersen:

```powershell
cd "C:\Users\ghost\Documents\New project"
python app.py
```

Sonra:

```text
http://localhost:8000
```

## Şu anki durum

- Modern responsive ana sayfa
- Python localhost sunucusu
- SQLite veritabanı
- Randevu API'si
- Ürün listeleme API'si
- Sipariş API'si
- İletişim API'si
- İstatistik API'si
- Basit yönetim ekranı
- Mevcut Gümüş Veteriner HTML arayüzü
- Randevu, sipariş ve iletişim formlarının backend'e bağlanması

## Klasörler

- `app.py`: Python sunucusu ve API kodları.
- `templates/index.html`: Web sitesi arayüzü.
- `data/gumus_veteriner.db`: SQLite veritabanı.
- `scripts/import_products.py`: Excel stok listesini veritabanına aktarma scripti.
- `static/`: Sonradan CSS, JS ve görseller için kullanılacak klasör.
- `.vscode/`: VS Code çalıştırma ve editör ayarları.

## Ürünleri Excel'den aktarma

Ürünler şu dosyadan içe aktarılabilir:

```text
C:\Users\ghost\Desktop\ürün stok takip.xlsx
```

Aktarım scripti:

```powershell
python scripts\import_products.py "C:\Users\ghost\Desktop\ürün stok takip.xlsx"
```

Not: Bu script `openpyxl` ister. Siteyi çalıştırmak için ekstra paket gerekmez; sadece ürünleri yeniden Excel'den aktarmak istersen `openpyxl` gerekir.

## API adresleri

- `GET /api/products`
- `POST /api/appointments`
- `GET /api/appointments`
- `PATCH /api/appointments/{id}/status?status=confirmed`
- `POST /api/orders`
- `GET /api/orders`
- `POST /api/contact`
- `POST /api/register`
- `POST /api/login`
- `POST /api/admin/login`
- `POST /api/logout`
- `GET /api/stats`

## Admin girişi

Local geliştirme için varsayılan admin hesabı:

```text
admin@gumusveteriner.com
admin123
```

Gerçek yayına çıkmadan önce bu şifre değiştirilmelidir.

## Sonraki teknik adımlar

1. Hayvan ve sahip kayıt modülü
2. Aşı ve tedavi takip modülü
3. Giriş / kayıt ve yetkilendirme
4. Yönetim ekranını ayrı admin girişine taşımak
