# G0 — Build spike devir notu (yeni oturum burada başlar)

```
DURUM   : Kod hattı bitti (G1–G8, main'de a15721d). EXE HİÇ ÜRETİLMEDİ.
HEDEF   : build\run_web.dist\Aican.exe + dist\Aican-Kurulum-0.9.0.{exe,zip,zip.sha256}
OTURUM  : yeni oturum, ana thread `opus`, bu dosyayla başla. Nuitka logu ağır —
          bağlam 200K'yı geçerse /compact.
KONUM   : v1-kasa deposu altında `01-Projects/aican` (kendi git deposu, submodule).
          Mutlak sürücü yolu varsayma; `git rev-parse --show-toplevel` ile teyit et.
```

## Ne bitti, ne bitmedi

| Faz | Durum |
|---|---|
| G1 Merkez kaydı + Ed25519 anahtar çifti (`~/.luden-lisans/urunler/aican/`) | ✅ |
| G2 `orchestrator/paths.py` + `lisans.py` / `lisans_durum.py` / `parmak_izi.py` | ✅ |
| G3 `web_paket.py` (`AIPAK1`, `web/`+`ai/` → `web.pak`) + bellekten servis | ✅ |
| G4 `lisans_ekrani.py` + `lisans_web/` (pywebview) | ✅ |
| G5 lisans kapısı + demo kilidi + filigran | ✅ |
| G6 `build.py` + `surum.py` + Windows damgası | ✅ *yazıldı, testle kilitli* |
| G7 `installer/Aican.iss` + dist taraması + ZIP/SHA-256 | ✅ *yazıldı, testle kilitli* |
| G8 `docs/KURULUM.md`, `docs/TESLIM.md`, `README.md` | ✅ |
| Tohum config normalizasyonu (`test_mode:false`, `tts_engine:"edge"`) | ✅ |
| **G0 — gerçek Nuitka derlemesi ve kabul testi** | ❌ **hiç çalıştırılmadı** |
| Kurucu (ISCC) üretimi | ❌ EXE olmadan olmaz |
| `git push` (aican + v1-kasa kökü) | ❌ onay bekliyor |

Doğrulama tabanı: `.venv\Scripts\python.exe -m pytest` → **276 passed, 1 failed**.
Tek kırık `orchestrator/test_word_categories.py::test_begin_ai_starter`
(`KeyError: 'ai_word'`) — lisans hattından **önce** kırıktı, dokunulmadı.

## Bu makinede eksik olanlar

Dev venv (`01-Projects/aican/.venv`) yalnız test bağımlılıklarını taşır:
flask, requests, psutil, cryptography, pywebview, pytest. **Yok:** Nuitka,
faster-whisper, ctranslate2, nvidia-cu12 wheel'ları, edge-tts, piper, noisereduce,
onnxruntime, imageio-ffmpeg, Inno Setup, (obfuscation için) Node/npx.

## Adımlar

### 1. Ortam
```powershell
cd 01-Projects\aican
.venv\Scripts\python.exe -m pip install nuitka ordered-set zstandard
.venv\Scripts\python.exe -m pip install -r orchestrator\requirements.txt
node --version      # yoksa: build.py'ye --obfuscate-yok ver (JS ham girer)
```
Piper çevrimdışı TTS yedeği istiyorsan `orchestrator\tts\voices\*.onnx`'i
README'deki komutla indir; yoksa build uyarır ama durmaz (edge/elevenlabs kalır).

### 2. Ön kontrol
```powershell
.venv\Scripts\python.exe build.py --check
```
Kontrol ettiği şeyler: içerik anahtarı (`LUDEN_LISANS` env ya da
`~\.luden-lisans\urunler\aican\icerik.key`) okunuyor mu, `icerik.key`'deki
`paket_no` ile `lisans.PAKET_NO` (=1) eşleşiyor mu, tohum `config.json`'da
`tts_elevenlabs_api_key` boş mu, npx var mı, Piper sesleri var mı.

### 3. Derleme (15+ dk, dist ~2 GB)
```powershell
.venv\Scripts\python.exe build.py --konsol
```
`--konsol` **ilk denemede kalsın**: Whisper/CUDA hataları görünsün. Üretim
build'i konsolsuzdur (`hide`; KimyaLab 50275baa gerekçesi `komutu_olustur`
içinde yorumda). Günlük: `dist\build.log`.

Adım sırası (build.py `main()`): anahtar → tohum kontrol → npx → `web_hazirla()`
(obfuscate → `dist\web-hazir\`) → `web_paket` → `dist\web.pak` →
`tohum_hazirla()` → `dist\config.json` → `komutu_olustur()` → `derle()` →
`cuda_dll_tamamla()` → `verify_dist()`.

### 4. Derleme sonrası kontroller
1. `build\run_web.dist\` içinde **var:** `Aican.exe`, `web.pak`, `lisans_web\index.html`,
   `assets\emojis\`, `config.json`, `nvidia\cublas\bin\cublas64_12.dll`,
   `nvidia\cudnn\bin\*.dll`. **Yok:** ham `web\`, ham `ai\`, `main.py`.
   (`verify_dist()` bunu basar; "Dagitmayin" satırı görürsen dur.)
2. ```powershell
   (Get-Item build\run_web.dist\Aican.exe).VersionInfo |
     Format-List CompanyName,ProductName,ProductVersion,FileVersion,FileDescription
   ```
   → Luden Studio / Aican / 0.9.0 / 0.9.0.0 / dolu.
3. `dist\config.json` içinde `"test_mode": false` ve `"tts_engine": "edge"`.

### 5. Kabul testi (kullanıcı elle — asıl G0 kabulü)
Merkez'den (`MERKEZ.bat` → Aican) **1 dakikalık TEST anahtarı** üret, sonra:
- Çift tık → pywebview lisans penceresi gelir, tarayıcı **açılmaz**.
- Anahtar girilince `%LOCALAPPDATA%\Aican\{aktivasyon.dat,config.json,logs\}` oluşur,
  iki sekme açılır; `/app.js` → 200, `/yok.js` → 404.
- Konsolda `CUDA DLL yollari eklendi: ...run_web.dist\nvidia\cublas\bin; ...\cudnn\bin`.
- **Mikrofonla "merhaba" → Whisper (cuda) → oyun menüsü → TTS sesi duyulur.**
  Bu döngü çalışmazsa ses hattı kararı yeniden açılır (klavye girişi + piper).
- Demo anahtar: filigran görünür, `g` tuşu/TEST toggle yok, sohbet kapalı,
  Ollama kapalıyken çalışır. Kalıcı anahtar: filigran yok, sohbet açık (Ollama ile).

### 6. Kurucu
```powershell
winget install JRSoftware.InnoSetup
.venv\Scripts\python.exe build.py --kurucu
```
→ `dist\Aican-Kurulum-0.9.0.exe`, `.zip`, `.zip.sha256`. Program Files'a kur →
lisans ekranı gelir → aktivasyon sonrası çalışır → kaldır → yeniden kur →
aktivasyon yerinde (kaldırma `%LOCALAPPDATA%\Aican`'ı silmez).

`docs/TESLIM.md` tam teslim kontrol listesini taşır.

## Beklenen kırılmalar (ilk başvurulacak yerler)

| Belirti | Bak |
|---|---|
| `No module named web_server` | `derle()` içindeki PYTHONPATH (`orchestrator;kök`) — Nuitka `run_web.py`'nin `sys.path.insert`'ini derleme anında çalıştırmaz |
| `Conflict between user and plugin decision` (webview) | `--include-module=webview` satırını kaldırıp yeniden dene; sonucu bu dosyaya yaz |
| İlk transkripsiyonda `cublas64_12.dll not found` | `--include-package-data=nvidia` tutmamış; `dist\build.log`'da "CUDA DLL'i tamamlandi" sayısına bak (`cuda_dll_tamamla` yedeği) |
| `ctranslate2` / `onnxruntime` DLL eksik | SprayTarih `tools/build_exe.py` `copy_missing_natives` desenini `cuda_dll_tamamla`'ya genişlet |
| Konsolsuz EXE sessizce ölüyor | Konsol modu `hide` olmalı (`attach` kısayoldan açılınca öldürüyor, `disable` stderr logging'i patlatıyor) |
| "Şu an düşünemiyorum…" | Ollama çalışmıyor / model inmemiş. EXE Ollama'yı **başlatmaz** (BASLAT.bat işiydi); kalıcı lisansta kurulum adımı: `ollama pull qwen3:4b-instruct-2507-q4_K_M` |

## Bekleyen kararlar / açık uçlar

- **Push onayı:** aican main (`a15721d`) ve v1-kasa kökü henüz push'lanmadı.
  Kök depoda ayrıca commit'lenmemiş duruyor: `LisansMerkezi/urunler.py`
  (`aican: etkin True`) + iki test dosyası, `.claude/agents/aican-gelistirici.md`,
  kök `CLAUDE.md`, aican submodule pointer'ı. (Website vb. değişiklikler ilgisiz.)
- **GPU'suz makinede ne olur bilinmiyor** — KURULUM.md bunu bilerek "bilinmiyor"
  diye yazıyor. Elle test edilip belgeye gerçek davranış yazılmalı.
- Elle test edilecek diğerleri: saat 5 gün geri → "saat" hatası; kurulum
  klasörünü başka makineye kopyala → "başka makine" hatası.
- `web.pak`'a `ai/*.yedek-*.json` dosyaları da giriyor (küçük; istenirse
  `web_paket.HARIC`'e desen eklenir).
- `test_begin_ai_starter` kırığı (lisans hattından önce vardı) hâlâ açık.

## Dokunulmaması gerekenler

- `lisans_bicim.py` — Merkez kopyası; elle düzenleme yok, `LisansMerkezi` içinden
  `urunler.kopyayi_guncelle('aican')` ile yenilenir (`test_urunler.py` denetler).
- `web_server.main()` çağrı sırası testle kilitli: `ensure_seeded` → `load_config`
  → `_port_in_use` → `lisans_kapisi` → `_paketi_yukle` → `create_app` →
  `open_browsers` → `app.run`.
- Sırlar: commit öncesi
  `git status --short | grep -iE "\.key|lisanslar\.json|luden-lisans|web\.pak|aktivasyon"`
  boş olmalı.

İlk plan ve sapma gerekçeleri: `2026-09-11-lisans-ve-kurucu-entegrasyonu.md`.
