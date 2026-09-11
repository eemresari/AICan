# Aican → demo + EXE + lisans hattı (OYUN-ENTEGRASYON-PLANI uygulaması)

```
HEDEF ÜRÜN     : Aican
ÜRÜN KODU      : aican
```

## Context

`LisansMerkezi/docs/OYUN-ENTEGRASYON-PLANI.md` KimyaLab'da ve SprayTarih'te uygulandı; sıradaki
ürün Aican (`01-Projects/aican`, submodule). Tarama sonucu: **lisans hattının hiçbir parçası
yok** (0/10 faz) ve ürün tarafı iki kardeşten daha az hazır — `paths.py` yok, `surum.py` yok,
build betiği yok, runtime yazımları (`config.json`, `logs/`, `tts/cache/`) kurulum dizinine
gidiyor (Program Files'ta kırılır), `donmus_mu()`/`sys.frozen` kontrolü yok.

**En yakın referans SprayTarih, KimyaLab değil:** ikisi de tarayıcı-kiosk (pywebview değil),
statik/HTTP sunucudan servis, standalone Nuitka build. SprayTarih'in dosyaları (`lisans*.py`,
`parmak_izi.py`, `web_paket.py`, `surum.py`, `lisans_web/`, `installer/*.iss`, `tests/test_*`)
kopya kaynağıdır; `lisans_bicim.py` **yalnız** Merkez'den (`urunler.kopyayi_guncelle`).

Kullanıcı kararları (2026-09-11):
- **Demo lisans = sohbet kapalı, yalnız oyunlar.** Mevcut `test_mode` altyapısı
  (`web_server.py:217-242`, `TEST_OYUNLAR=("eszit","atasozu")`, `GameEngine(bridge=None)`)
  demo lisansta **zorla açık ve kilitli** tutulur. Ollama demo'da hiç gerekmez.
- **Ses hattı demo'da da tam:** Whisper large-v3-turbo CUDA + edge/ElevenLabs TTS. Demo ön koşulu
  **NVIDIA GPU + ilk açılışta internet** (Whisper modeli HF'den iner; edge-tts internet ister).
  KURULUM.md bunu açıkça yazar. CUDA kütüphaneleri (nvidia-cublas/cudnn ~1 GB) dist'e girer.
- Kalıcı lisans = tam ürün; **Ollama + model kurulum kılavuzunda ön koşul** (kurucuya girmez).

## Faz 0 cevapları (teyit edildi)

- **S1:** Python (Flask, `orchestrator/`) + JS/HTML (`web/` 5 dosya, ES module değil, `?v=` yok,
  vendor yok) + **oyun veri tabloları `ai/*.json`** (atasözü, eş/zıt, doğru/yanlış, kategoriler,
  gestures, system_prompt). → **İçerik paketi ZORUNLU**; pakete `web/` + `ai/` girer.
  `assets/emojis/` (16 MB PNG kare) ham kalır — kaynak değil, görsel.
- **S2:** Chrome/Edge ayrı süreç, iki sekme (`/` sergi, `/control` panel), `BroadcastChannel` +
  `fetch('/api/…')`. → Lisans ekranı **pywebview** (SprayTarih deseni: yalnız o pencere için,
  HTTP sunucusu kalkmadan). Yeni bağımlılık `pywebview>=5,<6`.
- **S3:** Kamera/seri port yok. Ama **mikrofon + GPU (Whisper) + Ollama warmup thread'leri**
  `create_app` içinde başlıyor (`web_server.py:670-702`). → Kapı `main()` içinde
  `create_app`'ten ve `app.run`'dan **önce**. Masaüstü mod seçimi (§10) **gerekmez**.

## Aican'a özgü sapmalar

1. **`paths.py` sıfırdan** (`orchestrator/paths.py`, SprayTarih `backend/paths.py` deseni):
   `FROZEN`, `resource_root()`, `data_root()` = `%LOCALAPPDATA%\Aican` (frozen) / repo (kaynak),
   `ensure_seeded()` yalnız `config.json` tohumlar (`aktivasyon.dat` **tohumlanmaz**).
   Runtime yazan 5 nokta buraya bağlanır: `config.json` (`web_server.py:39-40,258`),
   `logs/session.log` (`session_logger.py`), `logs/stt_debug`, `tts/cache/`, `.tarayici_profili`.
   `elevenlabs_usage.json` de `data_root`'a.
2. **`ai/*.json` yükleyicileri bellekten okur:** `game_engine.py:134,168,208,209`,
   `llm_bridge.py:199-201`, `/api/gestures` (`web_server.py`) → `paths.kaynak_oku(rel)` şimi:
   frozen'da çözülmüş paket dict'inden, kaynakta diskten. Tek şim, 6 çağrı noktası.
3. **Demo kilidi:** `lisans_kapisi` `(icerik_anahtari, yuk)` döner; `main()` → `create_app(config,
   demo=yuk["tip"]=="demo")`. Demo'da: `test_mode["on"]=True` zorla; `POST /api/test_mode` → 403
   `{"error":"demo_kilidi"}`; `GET /api/test_mode` → `kilitli:true` (frontend `g` tuşunu ve
   toggle'ı gizler); LLM warmup thread'i **başlatılmaz**; `/api/pull`, `/api/model` → 403.
   Kaynaktan çalıştırmada (`FROZEN` False) kilit yok, `config.json`'daki `test_mode` geçerli.
4. **Filigran:** yeni `GET /api/filigran` → `{"metin": ...}` (modül değişkeni `FILIGRAN`).
   `app.js` açılışta bir kez okur, boş değilse `AI_Body_v2.html`'de sabit köşe `<div>` (inline
   stil, mevcut HTML deseni). Kalıcıda boş.
5. **Standalone build** (SprayTarih gerekçesi: onefile'da native DLL tamamlaması yapılamaz,
   burada CUDA/ctranslate2 DLL'leri var). Kurucu "yalnız EXE" kuralı → **dist taraması**
   (yasak: `aktivasyon.dat`, `config.json`'da dolu `tts_elevenlabs_api_key`, `*.key`,
   `lisanslar.json`, `logs/`, `.tarayici_profili/`, ham `web/`, ham `ai/`, `main.py` (Tkinter)).
6. **Build betiği `build.py` (kök) sıfırdan** — SprayTarih `tools/build_exe.py` şablon. Ham `web/`
   ve `ai/` **gömülmez**; `dist/web-hazir/` (obfuscate `--rename-globals false
   --control-flow-flattening false`, `--obfuscate-yok` kaçışı) + `ai/` → `dist/web.pak`.
   `--include-package-data` faster_whisper, ctranslate2, onnxruntime, nvidia.* ; `noisereduce`,
   `edge_tts`, `piper`, `flask` include. `_add_cuda_dll_dirs()` (`web_server.py:280-315`)
   site-packages'a bakıyor → frozen'da dist içindeki `nvidia/*/bin` yollarına düşecek şekilde
   `paths` üzerinden yeniden yazılır.
7. **Ollama Python tarafında başlatılmaz** (BASLAT.bat işi); EXE'de kalıcı lisansta Ollama yoksa
   mevcut `degraded` yolu çalışır ("Şu an düşünemiyorum…") — KURULUM.md hata tablosunda.
8. **`orchestrator/main.py` (Tkinter, 813 satır, kullanılmıyor)** ve `build_model.py`,
   `test_runner.py`, `veri_uretim/`, `kurulum/` build dışı.

## Risk — önce doğrula (G0 spike)

Nuitka standalone + faster-whisper (ctranslate2) + nvidia cu12 DLL'leri + onnxruntime + piper:
**Aican'da hiç denenmedi.** Lisans katmanı yazılmadan önce yalnız mevcut `run_web.py`'yi (pak'sız,
kapısız) standalone derleyip mikrofon→Whisper→oyun→TTS döngüsünün EXE'de çalıştığını gör.
Çalışmazsa ses hattı kararı yeniden açılır (klavye giriş + piper). Çıktı throwaway; `build.py`
bu spike'ın komutundan doğar. Beklenen dist ~2 GB, kurucu ~700 MB (lzma2).

## Uygulama — görev sırası (her görev TDD: RED → GREEN → `pytest` yeşil → commit)

Yollar aican köküne göre. Kopya kaynağı `01-Projects/SprayTarih/`.

### G0 — Build spike (throwaway)
- `pip install nuitka` (aican venv); `python -m nuitka --standalone run_web.py` + gerekli
  `--include-package-data`. Kayıt: hangi bayraklar gerekti, dist boyutu, açılış süresi.
- Kabul: EXE'den sergi sekmesi açılır, mikrofonla "merhaba" → Whisper → oyun menüsü → TTS ses.

### G1 — Faz 1: Merkez
1. `LisansMerkezi/urunler.py` `aican` kaydı: `ad "Aican"`, `klasor "aican"` doğru. Dokunma.
2. **Kullanıcı elle:** `MERKEZ.bat` → Aican → "Anahtar çifti üret" → hex kaydet → depo yedeği.
3. `python -c "import urunler; urunler.kopyayi_guncelle('aican')"` → `aican/lisans_bicim.py`.
   `LisansMerkezi/tests/test_urunler.py` yeşil.

### G2 — Faz 2: paths + çekirdek
- `orchestrator/paths.py` (yeni): `FROZEN`, `resource_root`, `data_root`, `ensure_seeded`,
  `activation_path`, `kaynak_oku`. Runtime yazımları (sapma #1) buraya bağlanır.
  Test: kaynakta yollar repo içinde; `FROZEN` monkeypatch'te `LOCALAPPDATA` altında; seed listesinde
  `aktivasyon.dat` yok.
- `lisans.py` (`URUN="aican"`, hex), `parmak_izi.py`, `lisans_durum.py` — SprayTarih kopyası,
  `paths` import'u `orchestrator.paths`.
- `tests/` (kök, yeni) + `pytest.ini` (`testpaths = tests orchestrator`, mevcut
  `orchestrator/test_quiz.py` ve `test_word_categories.py` kırılmaz).
- `.gitignore` += `.luden-lisans/`, `*.key`, `lisans.dat`, `lisanslar.json`, `aktivasyon.dat`,
  `dist/`, `build/`, `web.pak`, `web-hazir/`.

### G3 — Faz 3: içerik paketi
- `web_paket.py` — kopya, sihir `AIPAK1\n`.
- `web_server.py`: `create_app(config, paket=None, demo=False)`. `paket` varsa `/`, `/control`,
  `/<path:filename>` bellekten (`yol_coz`: sorgu dizisi atılır, elle MIME tablosu; `Cache-Control:
  no-store` korunur); `/assets/` diskten kalır. `ai/` yükleyicileri `paths.kaynak_oku` (sapma #2).
- Test: `test_web_paket.py` (round-trip, yanlış anahtar, paket_no açık), `test_serve.py`
  (`/app.js?v=1` 200, olmayan yol 404, MIME), `test_kaynak_oku.py`.

### G4 — Faz 4: lisans ekranı
- `orchestrator/requirements.txt` += `pywebview>=5,<6`.
- `lisans_ekrani.py` + `lisans_web/index.html` — SprayTarih kopyası, metinler "Aican".
- Test: `durumu_belirle` yedi durum (kopya).

### G5 — Faz 5: kapı + demo kilidi + filigran
- `web_server.py:main()` sırası: `load_config` → `_port_in_use` (ucuz socket, ikinci açılışta
  lisans ekranı çıkmasın) → **`lisans_kapisi(paths.FROZEN)`** → `_paketi_yukle` →
  `ensure_seeded` → `create_app(config, paket, demo)` → `open_browsers` → `app.run`.
  `LisansReddedildi(SystemExit)`; konsolsuz EXE için SprayTarih `_fatal` mesaj kutusu deseni.
- Demo kilidi (sapma #3), filigran (sapma #4); `control.js`/`app.js` `kilitli` ve filigran.
- Test: `inspect.getsource(main)` sıra kilidi (`lisans_kapisi` < `create_app` < `app.run`);
  `test_demo_kilidi.py` (Flask test client: demo'da POST /api/test_mode 403, GET kilitli, /api/send
  sohbet kapalı metni; demo değilken eski davranış); `/api/filigran` içerik.

### G6 — Faz 6+7: build + damga
- `surum.py` (kök): `SURUM="0.9.0"`, `URUN_ADI="Aican"`, `SIRKET="Luden Studio"`, `DOSYA_SURUMU`,
  `KURUCU_ADI`.
- `build.py` (kök) — G0 komutu + sapma #6. İçerik anahtarı `LUDEN_LISANS` /
  `~/.luden-lisans/urunler/aican/icerik.key`'den **okunur**. `--include-data-dir=lisans_web`,
  `--include-data-dir=assets`, `--include-data-files=dist/web.pak=web.pak`,
  `--include-module=` lisans, lisans_bicim, lisans_durum, lisans_ekrani, parmak_izi, web_paket,
  surum; `--include-package=cryptography` (webview için **verilmez** — SprayTarih notu).
  Damga bayrakları `surum`'dan; `--output-filename=Aican.exe`; `sys.stdout.reconfigure(utf-8)`.
- Test `tests/test_build.py`: komutta ham `web`/`ai` yok, `web.pak` var, `main.py` yok, dört
  damga bayrağı `surum`'dan, `SURUM` 3 / `DOSYA_SURUMU` 4 hane.

### G7 — Faz 8: kurucu
- `installer/Aican.iss` — SprayTarih kopyası, **yeni GUID**, `Source: "..\build\run_web.dist\*"`
  recursesubdirs, `/DSURUM /DURUN /DKURUCU_ADI` dışarıdan, Türkçe.
- `build.py --kurucu`: dist taraması (sapma #5) → ISCC bul (`ISCC` env > `%LOCALAPPDATA%\Programs\
  Inno Setup 6` > ProgramFiles(x86) > ProgramFiles) → kurucu → ZIP (+`KURULUM.txt`) → SHA-256.
- Test `tests/test_kurucu.py` (SprayTarih uyarlaması) + dist taramasında yasak ad → durur.

### G8 — Faz 10 + kapanış
- `docs/KURULUM.md` (müşteri): GPU + internet ön koşulu; **Ollama kalıcı lisans için** ayrı adım
  (`ollama pull qwen3:4b-instruct-2507-q4_K_M`); "Daha fazla bilgi" / "Yine de çalıştır" birebir
  (testle kilitli); hata tablosu (7 lisans durumu + "Şu an düşünemiyorum" = Ollama yok +
  Whisper modeli iniyor).
- `docs/TESLIM.md`; `README.md` "Lisans"/"Kurucu"/"Demo kilidi" bölümleri + §15 sınırlar;
  README'nin eski Tkinter anlatımı web akışına çekilir (zaten yanlış).
- `LisansMerkezi/urunler.py` → `etkin: True`; `test_urunler.py` senkron.
- `.claude/agents/aican-gelistirici.md` güncellenir (Flask/`run_web.py`/qwen3, lisans dosyaları,
  `pytest` doğrulama). Kök `CLAUDE.md` aican satırına lisans notu. Submodule pointer commit; push onayla.

## Model / oturum seçimi (CLAUDE.md politikası)

- **Uygulama oturumu: yeni oturum, `opus` ana thread**, bu plan dosyasıyla başla (çok dosyalı
  mimari: paths + Flask + build). Oturum ortasında model değiştirme.
- Kod görevleri (G2–G7) `aican-gelistirici` (opus) — her G ayrı çağrı, sıralı (birbirine bağımlı).
- Çıktısı büyük işler **subagent'a**: G0 build logu, `pytest` tam koşusu, dist taraması →
  `sonnet` general-purpose, yalnız özet döner.
- G8 belgeleri (KURULUM/TESLIM/README) → `sonnet` (`vault-duzenleyici` ya da general-purpose).
- G1.2 (anahtar üretimi) ve G0 kabul testi (mikrofon) **kullanıcı elle**.
- Bağlam 200K'yı geçince `/compact`; G0 spike'ı ayrı oturumda yapmak makul (Nuitka log ağır).

## Doğrulama

Her görev sonunda: `cd 01-Projects/aican && pytest` ve
`git status --short | grep -iE "\.key|lisanslar\.json|luden-lisans|web\.pak|aktivasyon"` → boş.

Build sonrası (§13, standalone'a uyarlı):
1. Merkez'den **TEST (1 dk)** anahtarı → `lisans.dogrula()` okur; içerik anahtarı `web.pak`'ı çözer.
2. `build/run_web.dist/` içinde ham `web/`, `ai/`, `main.py` **yok**; `web.pak`, `lisans_web/`, `assets/` var.
3. `(Get-Item build\run_web.dist\Aican.exe).VersionInfo` → CompanyName/ProductVersion dolu.
4. Kurucuyu Program Files'a kur → lisans ekranı gelir, tarayıcı açılmaz; anahtar sonrası
   `%LOCALAPPDATA%\Aican\{aktivasyon.dat,config.json,logs/}` oluşur, iki sekme açılır,
   `/app.js` 200, `/yok.js` 404.
5. **Demo anahtar:** filigran görünür, `g` tuşu/toggle yok, "merhaba" → oyun menüsü, sohbet kapalı,
   Ollama kapalıyken çalışır. **Kalıcı anahtar:** filigran yok, sohbet açık (Ollama ile).
6. Kaynaktan `python run_web.py` → lisans sorulmaz, `test_mode` config'den, davranış değişmemiş.
7. Kaldır → yeniden kur → aktivasyon yerinde.

Elle (kullanıcı): saat 5 gün geri → "saat"; kurulum klasörünü kopyala → "başka makine";
GPU'suz makinede açılış → Whisper CPU'ya düşer mi / hata mesajı ne (KURULUM.md'ye yazılır).
