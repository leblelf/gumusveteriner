#define MyAppName "Gümüş Veteriner Admin"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Gümüş Veteriner Muayenehanesi"
#define MyAppExeName "gumusvet_admin.exe"

[Setup]
AppId={{D28A70D4-B4D8-4DC8-A912-50B04C230B88}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\GumusVetAdmin
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=GumusVetAdmin-Setup
SetupIconFile=..\gumusvet_admin\windows\runner\resources\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\gumusvet_admin\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\KULLANIM_KILAVUZU.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; GroupDescription: "Ek simgeler:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Gümüş Veteriner Admin uygulamasını çalıştır"; Flags: nowait postinstall skipifsilent

