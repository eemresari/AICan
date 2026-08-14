# AI Body — Sergi Prototipi

Konya Bilim Merkezi sergi ünitesi için yapay zekâ tabanlı ifade prototipi.

**Akış:** ziyaretçi metin yazar → yerel AI (Gemma 3 4B) bir jest seçer → ekrandaki **96×96 yazılım LED matrisi** o jestin animasyonunu oynatır → kullanıcı **Durdur**'a basana kadar devam eder. Tüm oturum istatistikleri bir log dosyasına kaydedilir.

```
[Tkinter giriş]  →  [Ollama / Gemma 3 4B]  →  [96×96 yazılım matrisi]
     metin             jest seçimi              ışık animasyonu
                          ↓
                    [logs/session.log]
                  detaylı oturum kaydı
```

Tek bir Python süreci. Donanım yok, ESP32 yok — `python main.py` çağırınca her şey ekranda.

---

## 🔧 Sıfırdan Kurulum (Yeni Bilgisayarda)

### Önkoşullar

| Bileşen | Sürüm | Boyut | Kontrol komutu |
|---|---|---|---|
| **Python** | 3.10+ | ~30 MB | `python --version` |
| **Git** | herhangi | ~50 MB | `git --version` |
| **Ollama** | son sürüm | ~500 MB | `ollama --version` |
| **Gemma 3 4B modeli** | — | **~3.1 GB** | `ollama list` |

Toplam disk gereksinimi: ~4 GB. RAM: en az 6 GB (model yüklenince ~3 GB kullanır).

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

Kurulan paketler:
- `requests` — Ollama API çağrısı için
- `ollama` — Python istemci kütüphanesi
- `psutil` — RAM/CPU istatistikleri

Tkinter Python ile birlikte gelir, ek kurulum gerekmez.

---

### 6. Çalıştır

```bash
python main.py
```

Tkinter penceresi açılır.

İlk istek model RAM'e yüklenirken **10-20 saniye** sürer. Sonraki istekler 3-5 sn.

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
├── ai/
│   ├── gestures.json         ← 30 jest tanımı (renk, desen, hız)
│   ├── system_prompt.txt     ← Gemma sistem promptu (kuralları)
│   ├── test_examples.json    ← 50 referans test örneği
│   └── Modelfile             ← build_model.py üretir (gitignore'da)
├── orchestrator/
│   ├── main.py               ← Tkinter UI + ana akış
│   ├── llm_bridge.py         ← Ollama HTTP köprüsü
│   ├── gesture_engine.py     ← 36 desen + jest dispatcher
│   ├── matrix_sim.py         ← Tkinter Canvas tabanlı 96×96 görüntüleyici
│   ├── session_logger.py     ← Detaylı oturum logu
│   ├── stats.py              ← RAM / token istatistikleri (psutil)
│   ├── build_model.py        ← Modelfile üretici
│   ├── config.json           ← URL/model/yol ayarları
│   └── requirements.txt
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

- **Tek thread'li UI, çok thread'li ağ:** Tkinter ana thread'i blok olmaz; LLM çağrısı arka plan thread'inde, sonuç `queue.Queue` üzerinden 50ms `after()` poll'üyle ana thread'e gelir.
- **Frame loop:** matris ~30 fps'te (33ms throttle) render edilir; tüm desenler `time.monotonic()` tabanlı.
- **Süresiz jest:** AI bir jest seçince matriste sonsuza kadar oynar. Sadece **Durdur** butonu bitirir. Bu, sergi izleyicisinin animasyonu rahatça izlemesini sağlar.
- **`gestures.json` = doğru kaynak:** desen, renk, hız — hepsi buradan okunur. Yeni jest eklerken sadece bu dosyayı güncelle (`gesture_engine.PATTERN_DISPATCH` listesi geçerli `desen` değerlerini gösterir).
- **`session_logger.py`:** her oturum başında dosyaya başlık yazar, her olayı satır satır kaydeder, kapanışta özet ekler. Önceki oturumlar korunur (3 boş satır boşlukla).

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

### 6. Yasaklı kelime filtresi (küfür / nefret / yasak konu)

Ziyaretçinin küfür, hakaret, nefret söylemi ya da serginin kapsam dışı bıraktığı
konuları (din, etnik köken, siyaset/parti) içeren sözü **ekrana hiç yazılmaz**.
Uyarı da verilmez, "bunu söyleyemezsin" denmez — AI yalnızca **"Anlamadım, başka
bir şey söyler misin?"** repliğini `anlamadim` jestiyle okur. Sansür olduğu belli
edilmez.

- **Liste:** `ai/yasakli_kelimeler_tr_en.json` (TR + EN, ~1900 terim/ifade;
  dosyanın kendi `matching_policy` alanı eşleşme kurallarını tarif eder).
- **Kod:** `orchestrator/yasakli_filtre.py` — tam token/ifade eşleşmesi
  (alt-dize **aranmaz**). Yakalanan biçimler:
  leetspeak (`s1kt1r`), harf uzatma (`siiiktiiir`), harflenmiş söz (`a m k`,
  `s.i.k.t.i.r`), aksansız yazım (`GOTUNU SIKEYIM`), Türkçe ek soyma
  (`aptalsın → aptal`), **fiil çekimleri** (`sikiyorum`, `sikeceğim`,
  `gebericeksin`), **ünsüz yumuşaması** (`taşağını → taşak`, `amcığına → amcık`)
  ve **yapışık yazım** (`amınakoyum`, `siktirgit`, `orospuçocuğu`).
  Kapsam ölçümü: 342 Türkçe kök × 45 ek = 15.308 çekim taranıyor, yalnız
  3 bilinçli boşluk kalıyor (`kaza`, `malı`, `memeli` — hepsi koruma listesinde).
- **Nerede uygulanır:** `/api/transcribe` (sesli yol — metin istemciye **hiç
  gönderilmez**, sergi ekranı göstermek istese bile elinde metin olmaz),
  `/api/send`, `/api/game/input` ve panelin ekrana yazmadan önce sorduğu
  `/api/filter_check`.
- **Oyun bozulmaz:** yasaklı girdi oyun motoruna girmez → **tur/soru tüketilmez**,
  çocuk aynı soruya yeniden cevap verebilir. O turun beklenen cevapları
  (`game.stt_hints()`) filtreden **muaftır**: "güzel'in zıt anlamlısı?" sorusuna
  "çirkin" cevabı engellenmez (o kelimeyi zaten AI'nin kendi sorusu ekrana yazar).
- **Log:** engellenen sözün **kendisi hiçbir loga yazılmaz**; `logs/session.log`'a
  yalnız kategori/severity, sergi raporuna ise sayaç düşer
  (`Yasaklı girdi: 3 engellendi (agir 1) [...]`).
- **Ses:** replik sabit olduğu için açılıştaki TTS ön-ısıtmasına eklendi
  (`_warm_texts`) — ElevenLabs ile **bir kez** sentezlenip `orchestrator/tts/cache`'e
  yazılır; sahada anında çalar ve her engellemede yeniden kredi harcamaz
  (jest `anlamadim`, yoğunluk 0.6 — payload ile birebir aynı anahtar).

Ayarlar (`orchestrator/config.json`):

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `yasakli_filtre_enabled` | `true` | Filtreyi tamamen kapatır |
| `yasakli_diller` | `["tr","en"]` | Hangi dil listeleri yüklensin |
| `yasakli_fuzzy` | `false` | Bulanık (1 harf hatalı) eşleşme |
| `yasakli_fuzzy_min_uzunluk` | `6` | Bulanık eşleşmenin alt sınırı |
| `yasakli_baglam_duyarli` | `false` | Listenin `context_sensitive` terimleri (mal, it, deli, kel, top…) yalnız saldırı bağlamında engellensin |
| `yasakli_izinli` | `[]` | Görevlinin izin verdiği kelimeler (çekimlerini de açar) |
| `yasakli_ek_terimler` | `[]` | Listede olmayan, engellenmesi istenen kelimeler |
| `yasakli_debug` | `false` | **Teşhis:** filtreden geçen sözleri metniyle `logs/session.log`'a yazar (`YASAKLI-TESHIS`). Sergi günü kapalı olmalı |
| `yasakli_yanit` | "Anlamadım, başka bir şey söyler misin?" | Tek replik |

Listede yalnız ifade olarak geçen ama tek başına da söylenen kelimeler
(`tecavüz`, `intihar`, `meme`, `otuzbir`, `avrat`…) kodda `EK_TERIMLER` ile
tamamlandı. Yeni bir kelime eklemek için dosyaya dokunmadan
`yasakli_ek_terimler` kullanılabilir. Bilerek **eklenmedi:** `göğüs` (fen
sorularında geçen normal bir kelime).

**Bilinmesi gerekenler (sahada karşılaşılır):**

- Liste hakaret olarak **gündelik kelimeler** de içeriyor: `koyun, kaz, tavuk,
  maymun, böcek, mal, it, top, kel, deli, çirkin, aptal…`. Kelime Türetme'de çocuk
  bunlardan birini söylerse "anlamadım" duyar. Çözüm: o kelimeyi `yasakli_izinli`
  listesine ekle ya da `yasakli_baglam_duyarli: true` yap.
- `yasakli_fuzzy` **kapalı** gelir: sergi verisi üzerinde ölçüldüğünde
  `gerçek→gerzek`, `cansız→çapsız`, `dingin→dingil`, `oturmak→osurmak` gibi
  yanlış engeller üretiyordu. STT hatalarını da yakalamak istenirse açılabilir.
- Atasözü verisindeki "Allah dağına göre kar verir" gibi satırlar yasak konu
  (din) listesine takılır; ziyaretçi atasözünün tamamını tekrarlarsa ipucu
  muafiyeti devreye girer, ama bu atasözünü tamamen çıkarmak daha temiz olur.

Test: `python orchestrator/test_yasakli.py` (Ollama/Whisper gerekmez).

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
