# Gümüş Veteriner Admin

Flask API ve PostgreSQL veritabanına bağlanan Flutter yönetim uygulamasıdır.

## Çalıştırma

```powershell
C:\flutter\flutter\bin\flutter.bat pub get
C:\flutter\flutter\bin\flutter.bat run -d windows
```

## Release

```powershell
C:\flutter\flutter\bin\flutter.bat build windows --release
```

Çıktı:

```text
build\windows\x64\runner\Release\gumusvet_admin.exe
```

Proje kökündeki `scripts\package_windows.ps1` release dosyalarını ve kullanım
kılavuzunu taşınabilir ZIP paketine dönüştürür.

## API

Varsayılan adres: `https://wwwgumusvet.com`

Farklı ortam:

```powershell
C:\flutter\flutter\bin\flutter.bat run -d windows --dart-define=API_BASE_URL=http://localhost:5000
```
