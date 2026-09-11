# AI Body — Sergi Prototipi

Konya Bilim Merkezi sergi ünitesi için yapay zekâ tabanlı ifade prototipi.

**Akış:** ziyaretçi konuşur ya da yazar → yerel AI (Ollama / Qwen3 4B) bir jest
seçer → ekrandaki **96×96 yazılım LED matrisi** o jestin animasyonunu oynatır
→ kullanıcı **Durdur**'a basana kadar devam eder. Tüm oturum istatistikleri
bir log dosyasına kaydedilir. Ayrıca iki oyun modu (eş/zıt anlam, atasözü)
sohbetten bağımsız çalışır.

```
[Tarayıcı: sergi + kontrol paneli]  →  [Flask / web_server.py]  →  [Ollama / Qwen3 4B]
   iki sekme, BroadcastChannel            mikrofon → Whisper STT      jest seçimi
                                                    ↓                       ↓
                                          [96×96 yazılım matrisi]   [edge-tts / Piper TTS]
                                              ışık animasyonu           sesli yanıt
                                                    ↓
                                            [logs/session.log]
                                          detaylı oturum kaydı
```

Tek bir Python süreci (Flask sunucusu). Donanım yok, ESP32 yok — `python
run_web.py` çağırınca sergi ve kontrol paneli iki tarayıcı sekmesinde açılır.
Eski Tkinter arayüzü (`orchestrator/main.py`) hâlâ depoda durur ama
**kullanılmıyor**; üretim akışı budur.

---

## 🔧 Sıfırdan Kurulum (Yeni Bilgisayarda)

### Önkoşullar

| Bileşen | Sürüm | Boyut | Kontrol komutu |
|---|---|---|---|
| **Python** | 3.10+ | ~30 MB | `python --version` |
| **Git** | herhangi | ~50 MB | `git --version` |
| **NVIDIA ekran kartı + CUDA sürücüsü** | — | — | konuşma tanıma (Whisper) GPU'da çalışır |
| **Ollama** | son sürüm | ~500 MB | `ollama --version` |
| **Qwen3 4B Instruct modeli** | `qwen3:4b-instruct-2507-q4_K_M` | **~2,5 GB** | `ollama list` |
| **Whisper large-v3-turbo modeli** | — | **~1,5 GB** | ilk açılışta `faster-whisper` otomatik indirir |

Toplam disk gereksinimi: ~6 GB. RAM: en az 6 GB (Ollama modeli yüklenince
~3 GB kullanır). **İnternet:** ilk açılışta (Whisper modeli iner) ve her
açılışta (edge-tts sesli yanıt üretimi çevrimiçi çalışır) gereklidir —
kaynaktan çalıştırmada da paketlenmiş EXE'de de aynı.

---

### 1. Python (eğer kurulu değilse)

[python.org/downloads](https://python.org/downloads) → Windows installer indir → kur.

Kurarken **"Add Python to PATH"** kutusunu işaretle. Yoksa terminal `python` komutunu bulamaz.

```bash
python --version    # 3.10 veya üstü görmeli
pip --version
```

---

### 2. Ollama (yerel AI sunucusu)

[ollama.com/download](https://ollama.com/download) → Windows installer indir → kur.

Kurulumdan sonra Ollama otomatik olarak arka planda çalışır (sistem tray'de balık ikonu görürsün). Doğrula:

```bash
ollama --version
ollama list      # bos liste donmeli (henuz model yok)
```

---

### 3. Qwen3 4B Instruct modelini indir

Aktif model `qwen3:4b-instruct-2507-q4_K_M` (config.json'daki `ollama_model`).
2026-07-03 A/B testinde (50 örnek, jest doğruluğu) qwen3:4b-instruct 45/50 ile
gemma3:4b'yi (33/50) açık farkla geçti; gemma'nın Türkçesi daha akıcı ama kural
takibi zayıf. Karşılaştırma raporları: `logs/after_prompt_v3_qwen3-4b.json` ve
`logs/ab_gemma3-4b.json`.

```bash
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

İndirme ~2.5 GB — internet hızına göre 5-15 dakika sürer. Bittiğinde:

```bash
ollama list
# NAME                            ID              SIZE     MODIFIED
# qwen3:4b-instruct-2507-q4_K_M   0edcdef34593    2.5 GB   X minutes ago
```

**Hızlı test** (Ollama düzgün çalışıyor mu):

```bash
ollama run qwen3:4b-instruct-2507-q4_K_M "merhaba"
# Turkce kisa bir yanit gelmesi gerek (Ctrl+D ile cik)
```

---

### 4. Projeyi indir

```bash
git clone <REPO_URL> aican
cd aican
```

Veya GitHub'dan ZIP indirip aç.

---

### 5. Python paketlerini kur

```bash
cd orchestrator
pip install -r requirements.txt
```

Kurulan başlıca paketler (tam liste `orchestrator/requirements.txt`'de):
- `flask` — web sunucusu (sergi + kontrol paneli iki sekmede servis edilir)
- `requests`, `ollama` — Ollama API çağrısı için
- `faster-whisper`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` — GPU'da konuşma tanıma
- `edge-tts`, `piper-tts` — sesli yanıt (çevrimiçi birincil, Piper çevrimdışı yedek)
- `pywebview`, `cryptography` — lisans penceresi ve imza doğrulama (yalnız dondurulmuş EXE'de devreye girer; kaynaktan çalıştırmada lisans hiç sorulmaz)
- `psutil` — RAM/CPU istatistikleri

Tkinter Python ile birlikte gelir ama artık kullanılmıyor (bkz. giriş).

---

### 6. Çalıştır

```bash
python run_web.py
```

Flask sunucusu ayağa kalkar ve varsayılan tarayıcıda iki sekme açılır: sergi
ekranı (`/`) ve kontrol paneli (`/control`). Kaynaktan çalıştırmada lisans
penceresi **çıkmaz**; `config.json`'daki `test_mode` aynen geçerlidir.

İlk istek model RAM'e yüklenirken **10-20 saniye** sürer. Sonraki istekler 3-5 sn.
İlk açılışta ayrıca Whisper modeli internetten inmemişse birkaç dakikalık bir
bekleme olur (bkz. "Lisans" bölümü altındaki ön koşullar).

---

## 🎯 Hızlı Mod (Opsiyonel) — Sistem Promptunu Modele Göm

Sistem promptu (~2200 token) her istekte yeniden işleniyor → istek başına ~2.5 sn ekstra gecikme. Modele bir kez gömerek hızlandırabilirsin:

```bash
cd orchestrator
python build_model.py
```

Bu script:
1. `ai/system_prompt.txt`'yi okur
2. `ai/Modelfile` üretir
3. `ollama create aican -f ai/Modelfile` çalıştırır → `aican` adında özel model

Sonra `orchestrator/config.json` içinde:

```json
{
  "ollama_model": "aican",
  "use_baked_prompt": true
}
```

yap, yeniden başlat. Her istek ~2-3 sn daha hızlı olur.

> **Not:** Sistem promptunu (`ai/system_prompt.txt`) değiştirdiğin her seferde `python build_model.py` tekrar çalıştır.

---

## 🖥 Arayüz

Bu düzen artık **tek Tkinter penceresi değil, iki tarayıcı sekmesidir**:
sergi ekranı (`/`, yalnız 96×96 matris ve idle göz animasyonu) ve kontrol
paneli (`/control`, aşağıdaki panel). İkisi `BroadcastChannel` ile haberleşir;
sergi makinesinde ikisi de açık tutulur, ziyaretçi yalnız sergi sekmesini
görür. Alandaki bilgiler aynı kalır — yalnız pencere yerine sekme:

```
┌──────────────────────────┬─────────────────────────────────────┐
│                          │  Durum                              │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓        │    Ollama: ✓                        │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓        │    Aktif jest: sicaklik             │
│  ▓▓ 96×96 matris ▓▓      │    AI yanıtı: "Merhaba..."          │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓        ├─────────────────────────────────────┤
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓        │  Son komut                          │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓        │    jest_id, yoğunluk, süre          │
│                          ├─────────────────────────────────────┤
│                          │  İstatistik                         │
│                          │    Düşünme süresi, Token, Hız, RAM  │
│                          ├─────────────────────────────────────┤
│                          │  [_______________] [Gönder][Durdur] │
│                          ├─────────────────────────────────────┤
│                          │  Log (son 12 olay)                  │
└──────────────────────────┴─────────────────────────────────────┘
```

**Kısayollar:**
- `Enter` → mesaj gönder
- `Durdur` butonu → aktif jest durur, idle nefes geri gelir
- `ESC` veya pencereyi kapat → oturum özeti yazılır, çık

---

## 📋 Test Mesajları

| Yazdığın | Beklediğin jest | Görsel |
|---|---|---|
| `merhaba` | sicaklik | turuncu yumuşak nabız |
| `seni seviyorum` | sevgi | atan kalp ♥ |
| `bugün çok mutluyum` | mutluluk_yogun | gülen yüz 😊 |
| `babamı kaybettim` | uzgun_derin | üzgün yüz ☹ |
| `başardım` | gurur | yukarı ok ↑ |
| `vay canına!` | saskinlik | ünlem ❗ |
| `ürperti hissediyorum` | (sicaklik beklenir, mirror yasağı) | turuncu nabız |
| `2+2 4 mü eder` | onayla_net | yeşil çek ✓ |
| `dünya düz` | reddet_net | kırmızı çarpı ✗ |
| `bana şarkı söyle` | reddet_yumusak | mavi çarpı ✗ |
| `ne demek istedin` | soru_isareti | sarı ? |
| `asdfgh` | anlamadim | sallanan ? |

---

## 📁 Klasör Yapısı

```
AICAN/
├── README.md                 ← bu dosya
├── run_web.py                 ← GİRİŞ NOKTASI: Flask sunucusunu kaldırır, iki sekme açar
├── build.py                   ← standalone EXE + kurucu üretimi (bkz. "Kurucu")
├── surum.py                   ← ürün adı/sürüm — tek kaynak
├── lisans.py, lisans_bicim.py,
│   lisans_durum.py, lisans_ekrani.py,
│   parmak_izi.py, web_paket.py ← lisans hattı (bkz. "Lisans")
├── lisans_web/index.html      ← lisans penceresi (pywebview, ham girer)
├── installer/Aican.iss        ← Inno Setup kurucu tanımı
├── docs/KURULUM.md            ← müşteriye giden kurulum kılavuzu
├── docs/TESLIM.md             ← teslim kontrol listesi (geliştirici içindir)
├── ai/
│   ├── gestures.json         ← 30 jest tanımı (renk, desen, hız)
│   ├── system_prompt.txt     ← LLM sistem promptu (kuralları)
│   ├── test_examples.json    ← 50 referans test örneği
│   └── Modelfile             ← build_model.py üretir (gitignore'da)
├── web/                       ← sergi + kontrol paneli ön yüzü (Flask servis eder)
│   ├── AI_Body_v2.html, Kontrol_Paneli.html
│   └── app.js, control.js, led-panel.js
├── orchestrator/
│   ├── web_server.py         ← ÜRETİM: Flask uygulaması, lisans kapısı, main()
│   ├── main.py                ← eski Tkinter UI — kullanılmıyor, dokunulmuyor
│   ├── paths.py               ← kaynak/dondurulmuş yol çözümleme (tek giriş noktası)
│   ├── llm_bridge.py          ← Ollama HTTP köprüsü
│   ├── game_engine.py         ← eş/zıt anlam + atasözü oyunları, test_mode
│   ├── gesture_engine.py      ← 36 desen + jest dispatcher
│   ├── session_logger.py      ← Detaylı oturum logu
│   ├── stats.py               ← RAM / token istatistikleri (psutil)
│   ├── build_model.py         ← Modelfile üretici
│   ├── config.json            ← URL/model/yol ayarları (kaynakta tohum = gerçek dosya)
│   └── requirements.txt
├── tests/                      ← lisans hattı + build testleri (kök seviyesinde)
└── logs/
    └── session.log           ← her oturumda buraya eklenir (gitignore'da)
```

---

## 🎨 30 Jest, 36 Desen

Jestler iki kategoriye ayrılır:
- **`duygu_tepkisi`** (20 jest) — AI'nın iç durumu/atmosferi
- **`cevap_tepkisi`** (10 jest) — AI'nın iletişimsel cevabı

**Sembolik şekiller** (tek bakışta okunur):

| Şekil | Jest |
|---|---|
| ✓ checkmark | onayla_net (parlak yeşil), onayla_sicak (yumuşak yeşil-sarı) |
| ✗ x_mark | reddet_net (kırmızı), reddet_yumusak (yumuşak mavi) |
| ? question_mark | soru_isareti (sarı sakin), anlamadim (sallanan) |
| 😊 smile_face | mutluluk_yogun |
| ☹ sad_face | uzgun_derin |
| 💧 tear_drop | uzgun_yavas |
| 🔥 fire | ofke |
| ⚡ lightning | korku |
| ↑ arrow_up | gurur |
| ↓ arrow_down | hayal_kirikligi |
| ❗ exclamation | saskinlik |
| ⭐ star | hayranlik |
| ♥ heart | sevgi |
| ● lonely_dot | yalniz (tek titrek nokta) |
| 🏀 bouncing | nese (zıplayan toplar) |
| 🕐 clock | bekle (dönen ibre) |
| ⚡ chaotic_flash | panik (kaotik flaş) |

Geri kalan jestler atmosferik desenler kullanır (pulse, ripple, sparkle, drop, fade, three_dots, two_color_swing…).

---

## 📊 Oturum Logu — `logs/session.log`

Uygulama her başladığında bu dosyaya yeni bir oturum **eklenir** (üzerine yazmaz). Her oturum şu yapıdadır:

```
================================================================================
OTURUM BAŞLANGICI — 2026-05-03 14:32:01
================================================================================
Model adı:           qwen3:4b-instruct-2507-q4_K_M
Model boyutu:        2.5 GB
Format:              gguf
Family:              qwen3
Parametre sayısı:    4.3B
Quantization:        Q4_K_M
Python:              3.13.0
Platform:            Windows 11 (AMD64)
Başlangıç RAM:       ollama=50 MB, python=35 MB

KONUŞMA GEÇMİŞİ
[14:32:15] >> 'merhaba'
           jest_id:        sicaklik
           yogunluk:       0.70
           yanit:          'Merhaba, seni gördüğüme sevindim.'
           wall_time:      4.20 s
           prompt_tokens:  2240
           eval_tokens:    18
           tok_per_s:      30.0
           ram_ollama:     2890 MB
           ...

================================================================================
OTURUM ÖZETİ — 2026-05-03 14:45:22
================================================================================
Süre:                    13 dk 21 sn
Toplam istek:            6
Performans, Token kullanımı, RAM, Kategori dağılımı, En sık jestler...
```

**Oturum sonundaki özet** Claude/ChatGPT'ye verilebilir → otomatik optimizasyon önerileri çıkar.

---

## 🛠 Sorun Giderme

### "Ollama: ✗ (bağlanamadı)"
- `ollama list` çalışıyor mu? Servis sistem tray'de görünmeli.
- İlk açılışta Ollama yavaş cevap verirse panel ✗ gösterebilir. **Mesaj göndermeyi dene** — ilk başarılı istek panelı `✓` günceller.

### Yanıt çok yavaş (>30 sn) veya timeout
- İlk istek model yüklenirken yavaştır (~10-20 sn). Sonrakiler 3-5 sn.
- `request_timeout_sec`'i artır (`config.json`, varsayılan 35).
- Daha küçük model dene: `ollama pull gemma3:1b` ve `config.json`'da güncelle.
- "Hızlı mod" Modelfile entegrasyonunu kullan (yukarıda).

### Yanlış jest seçiliyor
- Yanlış kategorize ediliyorsa `ai/system_prompt.txt`'deki örneklere ekle.
- Modelfile kullanıyorsan `python build_model.py` tekrar çalıştır.
- 4B model küçük; daha kaliteli için: `ollama pull qwen2.5:7b-instruct` (4.4 GB).

### "psutil yok"
- `pip install psutil` ile ekle. Olmazsa diğer her şey çalışır, sadece RAM gösterilmez.

### PlatformIO klasörleri tekrar oluşuyor (`src/`, `platformio.ini` vb.)
- VS Code'da PlatformIO uzantısı yüklü olunca otomatik yaratıyor. `.gitignore`'da bunlar zaten dışlandı; sorun değil.

---

## 🏗 Mimari Notlar

- **Flask + tarayıcı, çok thread'li ağ:** `web_server.py` istekleri `threaded=True` ile karşılar; LLM/STT/TTS çağrıları istek thread'inde çalışır, sonuç doğrudan HTTP yanıtıyla döner (eski Tkinter'daki `queue.Queue`/`after()` poll deseni yalnız kullanılmayan `orchestrator/main.py`'de kalır).
- **Frame loop:** matris ~30 fps'te (33ms throttle) render edilir; tüm desenler `time.monotonic()` tabanlı — bu kısım tarayıcı tarafında (`web/led-panel.js`) değişmeden çalışır.
- **Süresiz jest:** AI bir jest seçince matriste sonsuza kadar oynar. Sadece **Durdur** butonu bitirir. Bu, sergi izleyicisinin animasyonu rahatça izlemesini sağlar.
- **`gestures.json` = doğru kaynak:** desen, renk, hız — hepsi buradan okunur. Yeni jest eklerken sadece bu dosyayı güncelle (`gesture_engine.PATTERN_DISPATCH` listesi geçerli `desen` değerlerini gösterir).
- **`session_logger.py`:** her oturum başında dosyaya başlık yazar, her olayı satır satır kaydeder, kapanışta özet ekler. Önceki oturumlar korunur (3 boş satır boşlukla).

---

## Lisans

Dondurulmuş EXE açılışta — mikrofon/GPU/Ollama thread'leri başlamadan,
Flask sunucusu kalkmadan — bir lisans anahtarı ister
(`orchestrator/web_server.py:lisans_kapisi`). Kaynaktan `python run_web.py`
ile çalıştırmada kapı **yoktur**; `config.json`'daki `test_mode` aynen
geçerlidir, geliştirme döngüsü değişmez.

- **Anahtar üretimi** bu depoda değil, [Lisans Merkezi](../LisansMerkezi)'nde
  (`MERKEZ.bat` → Aican). EXE'de yalnız **açık** anahtar durur
  (`lisans.py:ACIK_ANAHTAR_HEX`); özel anahtar `~/.luden-lisans/` altındadır ve
  **asla commit edilmez**.
- **İçerik paketi:** `web/` ve `ai/` EXE'nin yanına ham konmaz. Build, JS'i
  obfuscate edip ikisini `web.pak` olarak şifreler; anahtar lisansın imzalı
  yükünde gelir, paket lisans kapısından sonra **bellekte** çözülür
  (`_paketi_yukle`) ve oradan servis edilir (`paths.kaynak_oku` şimi —
  `ai/*.json` yükleyicileri de aynı yoldan geçer). Lisansı olmayan kişi
  içeriği göremez.
- **Aktivasyon** `%LOCALAPPDATA%\Aican\aktivasyon.dat` — makine parmak izine
  (anakart/disk/MAC, 3'ten 2'si) HMAC ile bağlı; kopyalamak işe yaramaz.
  Demo anahtarlarda süre ilk aktivasyondan sayılır, saat geri alınırsa kilit.
- **Filigran:** demo lisansta sergi köşesinde `Kurum — tarih — #no` yazar
  (`GET /api/filigran`, `web/app.js`); kalıcı lisansta yoktur.

### Demo kilidi

Deneme (demo) lisansta sohbet **tamamen kapalıdır**, yalnız iki oyun
oynanabilir. Bu mevcut `test_mode` altyapısı üzerine kurulu ve demoda
**zorla açık ve kilitli** tutulur:

- `test_mode["on"]` demo'da `True`'ya zorlanır; `GET /api/test_mode` her
  zaman `kilitli: true` döner (kontrol panelinde `g` tuşu ve TEST toggle'ı
  gizlenir); `POST /api/test_mode` `403 {"error": "demo_kilidi"}` verir.
  `/api/pull`, `/api/model` da demoda `403`.
- `/api/send` demoda serbest metin yerine sabit
  `TEST_SOHBET_KAPALI_TEXT` ile yanıtlar — yeni bir LLM isteği hiç atılmaz.
- Ollama warmup thread'i demoda **hiç başlatılmaz** (`_warmup_baslat`) —
  demo lisans Ollama'nın kurulu olmasına bağımlı değildir.
- Kaynaktan çalıştırmada (`paths.FROZEN` `False`) bu kilit devreye
  girmez; `config.json`'daki `test_mode` olduğu gibi geçerlidir.

Kalıcı lisansta Ollama **ayrıca** kurulmalı/çalışıyor olmalıdır (kurucu onu
başlatmaz); kapalıysa sohbet 403 değil, `meta.degraded: true` ile birlikte
"Şu an düşünemiyorum, birazdan tekrar dener misin?" der — kiosk hata kutusu
göstermez.

### Kurucu

`installer/Aican.iss` (Inno Setup 6). KimyaLab'daki "yalnız EXE girer"
kuralı burada uygulanamaz: Aican standalone derlenir (Nuitka `--standalone`,
CUDA/Whisper native DLL'leri onefile'da tamamlanamadığı için), yani
`build/run_web.dist/*` **tamamı** kurucuya girer. Onun yerine
`build.kurucu_uret()` ISCC'den **önce** dist'i tarar: `aktivasyon.dat`,
`*.key`, `lisanslar.json`, `logs/`, `.tarayıcı_profili/`, ham `web/`/`ai/`,
`main.py` ya da içinde dolu `tts_elevenlabs_api_key` olan `config.json`
bulursa build **durur** (`tests/test_kurucu.py`).

**Tohum config:** `orchestrator/config.json` (sergi makinesinin gerçek ayarları)
EXE'ye ham girmez; `build.tohum_hazirla()` onu `dist/config.json`'a yazarken
`test_mode: false` ve `tts_engine: "edge"` zorlar (`build.TOHUM_ZORLA`) — kalıcı
lisanslı müşteri ilk açılışta tam ürünü ve anahtarsız TTS'i görür; demo lisansta
`test_mode`'u zaten `web_server` zorla açar. Dolu `tts_elevenlabs_api_key` build'i
durdurur. Depodaki dosya değişmez.

Sürüm numarası tek yerde: `surum.py`.

Müşteriye giden kılavuz: [`docs/KURULUM.md`](docs/KURULUM.md). Geliştirici
teslim kontrol listesi: [`docs/TESLIM.md`](docs/TESLIM.md).
Dosyalar: `lisans.py`, `lisans_bicim.py` (Merkez'den birebir kopya — elle
düzenleme, `LisansMerkezi/tests/test_urunler.py` senkronu denetler),
`lisans_durum.py`, `parmak_izi.py`, `lisans_ekrani.py` + `lisans_web/`,
`web_paket.py`, `surum.py`, `orchestrator/paths.py`.

### Dürüst sınırlar

- Kaynaktan çalıştırmada (`python run_web.py`) lisans kapısı **hiç yoktur**;
  `test_mode` yalnız `config.json`'dan okunur. Bu bilinçli bir açık kapı —
  geliştirme döngüsü lisanssız kalsın diye.
- JS obfuscation ve `web.pak` şifrelemesi **caydırıcıdır, engel değil**:
  DevTools açan biri çalışan (obfuscate edilmiş) JS'i görebilir; paketin
  kapattığı şey içeriği diskten kopyalama/lisanssız görüntüleme yoludur.
  Süre/lisans kontrolü teorik olarak yamalanabilir — ama yamalayan kişi
  zaten geçerli bir anahtara sahiptir, bu artık sözleşme alanıdır.
- Lisans dosyasının ilk aktivasyondan önce başka bir makinede kullanılması
  engellenemez (çevrimdışı sistem); `son_kullanim_ts` mutlak tavanı bunu
  süreyle sınırlar.
- Anakart değişince yeniden aktivasyon gerekir (HMAC anahtarı birincil
  bileşenden türetilir) — küçük donanım değişiklikleri (RAM, ekran kartı)
  sorun çıkarmaz.
- GPU'suz bir makinede açılışın ne yapacağı **bilinmiyor**; bu sürüm yalnız
  NVIDIA GPU'lu makinede elle test edildi (bkz. `docs/KURULUM.md`).

---

## 🛡 Sergi Dayanıklılığı

Kiosk günlerce kesintisiz çalışacaksa aşağıdaki önlemler önerilir.

### 1. Gecelik yeniden başlatma (Windows Görev Zamanlayıcı)

Tarayıcı ve sunucuyu her gece (örn. 04:00, sergi kapalıyken) tazelemek bellek sızıntılarını ve Ollama KV-cache şişmesini sıfırlar:

1. `taskschd.msc` aç → **Görev Oluştur**.
2. **Tetikleyici:** Günlük, 04:00.
3. **Eylem 1:** `taskkill /IM msedge.exe /F & taskkill /IM python.exe /F` (bir `.bat` içinde; kendi tarayıcı sürecinin adını kullan).
4. **Eylem 2 (veya ayrı görev, 1-2 dk sonra):** `python orchestrator/web_server.py` çalıştıran bir `.bat` (çalışma dizini proje kökü olacak şekilde). Sunucu açılışta iki sekmeyi kendisi açar.
5. Görevi **"Kullanıcı oturum açmış olsun olmasın"** yerine kiosk kullanıcısı oturumunda çalışacak şekilde ayarla (tarayıcı penceresi açılabilsin).

### 2. `/api/health` ile izleme (watchdog)

`GET http://127.0.0.1:5057/api/health` şunu döner:

```json
{ "ollama": true, "model": "qwen3:4b-instruct-2507-q4_K_M", "tts": true, "tts_status": "hazir", "uptime_s": 12345.6 }
```

- `ollama: false` → Ollama servisi düşmüş; `ollama serve`/servisi yeniden başlat.
- `tts: false` → TTS motoru yüklenememiş (`tts_status` sebep verir); ses olmadan sergi çalışmaya devam eder.
- `uptime_s` → gecelik yeniden başlatmanın gerçekten olduğunu doğrulamak için (sabah küçük bir değer görmelisin).
- Basit watchdog: Görev Zamanlayıcı'da 5 dakikada bir `curl -s http://127.0.0.1:5057/api/health || <yeniden-baslat.bat>` koşan bir görev.

Ayrıca `/api/send`, Ollama tamamen kapalıyken bile artık HTTP 200 + nazik bir "Şu an düşünemiyorum…" yanıtı döner (`meta.degraded: true`) — kiosk hata kutusu göstermez.

### 3. Ollama ortam değişkenleri

Bu makinede `setx` ile sistem geneline eklendi (yeni kurulumda tekrar ekle, sonra Ollama'yı yeniden başlat):

```bat
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_NUM_PARALLEL 1
setx OLLAMA_MAX_LOADED_MODELS 1
```

- `FLASH_ATTENTION=1` + `KV_CACHE_TYPE=q8_0` → KV cache yarıya iner, 4 GB VRAM'e daha rahat sığar.
- `NUM_PARALLEL=1` + `MAX_LOADED_MODELS=1` → tek kiosk isteği için gereksiz paralellik/ikinci model yüklemesi engellenir.

### 4. `ollama ps` — %100 GPU kontrolü

```bash
ollama ps
# NAME                            ...  PROCESSOR    ...
# qwen3:4b-instruct-2507-q4_K_M   ...  100% GPU
# %100 GPU degilse: config'te llm_num_gpu=99 zorlamasi + oksuz llama-server.exe
# sureclerini kontrol et (Stop-Process -Name llama-server) — kismi CPU tasmasi 4-5x yavaslatir.
```

`PROCESSOR` sütununda **100% GPU** görünmeli. `xx%/yy% CPU/GPU` görünüyorsa model VRAM'e sığmamış demektir (yanıtlar belirgin yavaşlar) — KV cache ayarlarını (yukarıda) doğrula, başka VRAM tüketen uygulama (tarayıcı GPU sekmeleri dahil) var mı bak, gerekirse daha küçük model kullan.

### 5. Oyun oturumu izleri

Oyun başlangıç/bitişleri de `logs/session.log`'a yazılır (`OYUN [tkm|kelime|quiz] basladi/bitti/yarim_birakildi | skor…` satırları) — gün sonunda hangi oyunların ne kadar oynandığı buradan çıkarılır.

---

## 🚀 Geleceğe Yönelik

- **Gerçek donanım:** ESP32 + WS2812B 32×32 panel (HUB75) ile fiziksel sergiye taşınabilir. Aynı `gestures.json` ve sistem promptu kullanılır; sadece firmware (`src/main.cpp`) yeniden yazılması gerekir.
- **Daha iyi model:** RAM yeterse `qwen2.5:7b-instruct` (4.4 GB, daha iyi Türkçe), `qwen2.5:14b-instruct` (9 GB, premium kalite).
- **Çoklu dil:** sistem promptu İngilizce'ye çevrilirse aynı sistem İngilizce ziyaretçilerle de çalışabilir.

---

## 🙏 Atıflar / Açık Kaynak

Web arayüzündeki **otonom "canlı göz" idle animasyonu** ([web/led-panel.js](web/led-panel.js) içindeki `EyeSystem` sınıfı) aşağıdaki açık kaynak projelerin mantığından ilham alınarak — kod birebir kopyalanmadan — projenin 96×96 Canvas pipeline'ına yeniden uyarlanmıştır:

- **FluxGarage / RoboEyes** (Arduino/C++, MIT) — parametrik göz çizimi, `autoblinker`, `idle`, `curiosity`, `tired` davranış mantığı. <https://github.com/FluxGarage/RoboEyes>
- **sidikalamini / eyes-animation** (Python/Pygame) — akışkan pupil hareketi ve durum geçişleri için referans. <https://github.com/sidikalamini/eyes-animation>

Lisans uyumluluğu: yukarıdaki projelerden kod paylaşımı yapılmamış, yalnızca davranış tasarımı (göz parametreleri, kırpma/bakınma/uyku durumları, organik zamanlama) referans alınmıştır. Sergi tarafındaki implementasyon tamamen bu proje için yazılmıştır.
