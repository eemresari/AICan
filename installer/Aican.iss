; Aican kurucu tanimi (Inno Setup 6).
;
; ELLE CALISTIRMA: bu dosyayi dogrudan ISCC'ye vermek yerine
;     python build.py --kurucu
; kullan. Surum numarasi ve urun adi surum.py'de tek yerde durur ve oradan
; /D ile gecer; burada elle yazilirsa iki kaynak olur ve ayrisirlar.
;
; PAKETE NE GIRER: build\run_web.dist\* (standalone Nuitka klasoru — EXE +
; yuzlerce DLL/.pyd + web.pak + lisans_web + assets + tohum config.json +
; nvidia\{cublas,cudnn}\bin CUDA DLL'leri, ~2 GB). KimyaLab'daki "yalniz EXE"
; kurali burada uygulanamaz; onun yerine build.kurucu_uret() ISCC'den ONCE
; dist'i tarar: aktivasyon.dat, *.key, lisanslar.json, logs\,
; .tarayici_profili\, ham web\ ya da ai\, main.py ya da icinde dolu
; tts_elevenlabs_api_key olan config.json bulunursa build DURUR.
; tests/test_kurucu.py bunu kilitler.

#ifndef SURUM
  #define SURUM "0.0.0-elle"
#endif
#ifndef URUN
  #define URUN "Aican"
#endif
#ifndef KURUCU_ADI
  #define KURUCU_ADI "Aican-Kurulum-elle"
#endif

#define SIRKET   "Luden Studio"

[Setup]
; KimyaLab ve SprayTarih'ten FARKLI GUID: ayni olsaydi Windows iki oyunu
; ayni program sayar, biri digerini kaldirirdi.
AppId={{B67B885F-B93E-4847-BC93-8A066D7741CC}
AppName={#URUN}
AppVersion={#SURUM}
AppVerName={#URUN} {#SURUM}
AppPublisher={#SIRKET}
VersionInfoVersion={#SURUM}
DefaultDirName={autopf}\{#SIRKET}\{#URUN}
DefaultGroupName={#SIRKET}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename={#KURUCU_ADI}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; 64-bit Python'dan derleniyor; CUDA DLL'leri de 64-bit. 32-bit Windows'ta calismaz.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Program Files'a yaziyoruz -> yonetici gerekir. Kullanici basina kurulum
; secenegi bilerek yok: sergi PC'sinde uygulama ortak bir hesaptan acilir,
; kurulumun tek yerde durmasi destek vermeyi kolaylastirir.
PrivilegesRequired=admin
UninstallDisplayName={#URUN} {#SURUM}
UninstallDisplayIcon={app}\{#URUN}.exe

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaustune kisayol olustur"; GroupDescription: "Ek kisayollar:"

[Files]
Source: "..\build\run_web.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#URUN}"; Filename: "{app}\{#URUN}.exe"
Name: "{autodesktop}\{#URUN}"; Filename: "{app}\{#URUN}.exe"; Tasks: masaustu

[Run]
Filename: "{app}\{#URUN}.exe"; Description: "{#URUN} uygulamasini simdi ac"; Flags: nowait postinstall skipifsilent

; KALDIRMA NOTU: kullanicinin config.json'u, loglari, TTS onbellegi ve
; aktivasyonu %LOCALAPPDATA%\Aican altinda durur ve kaldirmada SILINMEZ.
; Surum yukseltmesinde lisansi yeniden girmek gerekmesin diye boyle;
; tamamen temizlemek isteyen o klasoru elle siler (docs/KURULUM.md).
