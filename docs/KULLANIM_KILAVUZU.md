# Gümüş Veteriner Kullanım Kılavuzu

## Web Sitesi

### Üyelik ve Giriş

1. Üst menüden **Giriş Yap** seçilir.
2. Yeni kullanıcı **Üye Ol** sekmesinden ad, e-posta, telefon ve şifre girer.
3. Kayıt tamamlanınca kullanıcı otomatik olarak giriş yapmış olur.
4. Kullanıcı adına tıklanarak profil açılır.

### Pet ve Sağlık Kaydı

1. Profilde **Hayvan Ekle** formu doldurulur.
2. Kayıtlı hayvan kartındaki **Düzenle** ile bilgiler güncellenir.
3. Sağlık kaydı bölümünden hastalık, aşı, tedavi, alerji veya ilaç eklenir.

### Randevu

1. **Randevu Al** seçilir.
2. Gün, uygun saat, hizmet ve veteriner seçilir.
3. Üye girişi varsa kayıtlı pet kullanılabilir veya yeni pet eklenebilir.
4. Onay durumu profil ve bildirim alanından takip edilir.

### Sipariş

1. Ürünler ekranından stokta bulunan ürün sepete eklenir.
2. Sepette adet artırılır, azaltılır veya ürün silinir.
3. Teslimat ve demo ödeme bilgileri tamamlanır.
4. Sipariş durumu profil içindeki **Siparişlerim** alanından izlenir.

## Admin Uygulaması

### Randevular

- Randevu kartına tıklayarak talep ve pet bilgilerini görüntüleyin.
- Menüden Bekliyor, Onaylandı, Tamamlandı veya İptal durumunu seçin.
- Randevu saatleri ekranından klinik takvimini yönetin.

### Ürün ve Stok

- **Yeni Ekle** ile ad, kategori, fiyat, stok ve fotoğraf adresi girin.
- Hatalı sayı veya boş zorunlu alanlar kaydedilmez.
- Stok filtreleriyle tükenen ve kritik ürünleri bulun.

### Yatan Hastalar

- Kayıtlı pet seçin veya yeni hasta bilgisi girin.
- Tanı, oda, tedavi planı ve veteriner notunu kaydedin.
- Tedavi tamamlanınca **Taburcu Et** işlemini kullanın.

### Siparişler

- Sipariş detayından ürünleri ve teslimat adresini kontrol edin.
- Durumu değiştirdiğinizde kullanıcıya bildirim gönderilir.
- E-posta ayarları hazırsa klinik hesabından durum e-postası gider.

### Yardım

Sol menüdeki **Yardım & Kullanım** ekranı günlük işlemleri ve API/veritabanı
bağlantı durumunu gösterir.

## Sorun Giderme

- Veri görünmüyorsa internet bağlantısını ve Yardım ekranındaki sistem durumunu
  kontrol edin.
- Admin oturumu sona erdiyse tekrar giriş yapın.
- Site sağlığı için `https://wwwgumusvet.com/api/health` adresini açın.
- E-posta gönderilmiyorsa Render SMTP değişkenlerini kontrol edin.

