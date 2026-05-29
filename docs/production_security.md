# Gümüş Veteriner Production Güvenlik Notları

Bu dosya Render üzerinde canlı çalışan site için kısa kontrol listesidir.

## Veritabanı ve yedek

- Kısa vadede SQLite dosyası `data/gumus_veteriner.db` kullanılır.
- Render yüksek trafik için PostgreSQL servisinin `DATABASE_URL` değerini verir.
- PostgreSQL geçişinde bağlantı havuzu ayarları `services/database.py` içindedir.
- SQLite kullanıldığı sürece günlük yedek alın:
  - Render Shell veya lokalden `data/gumus_veteriner.db` dosyasını indirin.
  - Yedekleri GitHub'a yüklemeyin.
  - Önerilen klasör: `backups/YYYY-MM-DD/gumus_veteriner.db`
- PostgreSQL'e geçince Render'ın managed backup/snapshot özelliğini açın.

## Dosya ve görsel

- Yükleme açılırsa sadece `jpg`, `jpeg`, `png`, `webp`, `pdf` kabul edin.
- Maksimum dosya boyutu varsayılan olarak 5 MB'dır: `MAX_UPLOAD_BYTES`.
- Büyük görselleri siteye koymadan önce WebP'ye çevirin ve 1600px genişliği geçirmeyin.

## Render ölçekleme

- Başlangıç için `WEB_CONCURRENCY=2`, `GUNICORN_THREADS=4` yeterlidir.
- Trafik artarsa önce PostgreSQL'e geçin, sonra worker sayısını planınıza göre artırın.
- Rate limit için production'da Redis tabanlı `RATELIMIT_STORAGE_URI` kullanın.
