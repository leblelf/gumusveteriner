# İhtiyaç Analizi

## Müşteri

Gümüş Veteriner Muayenehanesi, Canik/Samsun.

## Temel Sorunlar

- Randevuların aynı saat için çakışmadan yönetilmesi
- Pet ve hasta geçmişinin tek noktada tutulması
- Ürün stoklarının ve sipariş durumlarının izlenmesi
- Müşterilere randevu, sipariş ve yorum yanıtı bildirimi gönderilmesi
- Klinik personelinin teknik bilgi gerektirmeden sistemi kullanabilmesi
- Web sitesi ve admin uygulamasının aynı güncel veriyi kullanması

## Kullanıcı Rolleri

### Ziyaretçi

- Klinik bilgilerini, hizmetleri, ürünleri ve yorumları görür.
- Randevu alabilir ve genel klinik yorumu yapabilir.
- İletişim formunu ve WhatsApp hattını kullanabilir.

### Üye

- Profil, adres ve pet bilgilerini yönetir.
- Pet sağlık geçmişine hastalık, aşı, tedavi, alerji ve ilaç kaydı ekler.
- Kayıtlı pet ile randevu alır ve randevu durumunu takip eder.
- Siparişlerini ve bildirimlerini görüntüler.
- Satın aldığı ürünlere yorum yapar.

### Admin

- Pet, yatış, randevu, ürün, stok, sipariş ve üye kayıtlarını yönetir.
- Randevu saatlerini açar veya kapatır.
- Yorum ve iletişim mesajlarını yanıtlar.
- Site metinlerini günceller.
- SMS gönderir ve düşük stok bildirimlerini takip eder.

## İş Kuralları

- Aynı gün ve saat için ikinci aktif randevu oluşturulamaz.
- Stok sıfırsa ürün sepete eklenemez.
- Sipariş oluşturulurken stok miktarı kontrol edilir ve düşürülür.
- Ürün yorumu yalnızca ürünü satın alan üyeler tarafından yapılabilir.
- Admin listesinden kaldırılan pet ve randevu, kullanıcının kendi geçmişinden
  otomatik olarak silinmez.
- Aynı e-posta veya telefonla mükerrer üyelik oluşturulamaz.
- Admin dışındaki kullanıcılar admin API endpointlerine erişemez.

## Başarı Ölçütleri

- Kritik işlemler kullanıcıya Türkçe başarı veya hata mesajı gösterir.
- Web sitesi mobil ve masaüstünde kullanılabilir.
- Admin uygulaması Windows’ta release olarak kurulabilir.
- Production verileri PostgreSQL’de kalıcı tutulur.
- `/health` ve `/api/health` endpointleri servis durumunu gösterir.

