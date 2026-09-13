# Aican — iyi ses (ElevenLabs önbelleği) yerine ücretsiz Piper sesinin çalması

## Context

Aican'ın derlemesi alındı, ama sergi ekranı **`tr_TR-dfki-medium` (Piper, ücretsiz/çevrimdışı)**
sesiyle konuşuyor. Oysa depoda ElevenLabs ile önceden üretilmiş **6490 parçalık, 900 MB'lık
ses önbelleği** var (`orchestrator/tts/cache/`, 44100 Hz).

Ölçümle doğrulanan durum (motorlar farklı örnekleme hızı üretir: ElevenLabs 44100,
edge 24000, Piper 22050 Hz):

| Dizin | Dosya | Hz | Motor |
|---|---|---|---|
| `orchestrator/tts/cache/` | 6490 | 44100 | ElevenLabs — **iyi ses, sağlam** |
| `aican/cache/` (izlenmeyen kopya) | 6490 | 44100 | Aynı dosyalar — **kod buradan hiç okumuyor** |
| `%LOCALAPPDATA%\Aican\tts\cache\` | 51 | 22050 (51/51) | **Piper** — EXE %100 ücretsiz sesle konuşmuş |

**Önemli düzeltme:** İlk incelemede "11 replik önbellekte yok" göründü ve sana bu soruldu.
Yanlıştı — ölçüm tekrarlandı: tarayıcı ve `gen_batch` metni **cümlelere bölüp** (`_split_sentences_tr`)
parça parça seslendiriyor; önbellek de parça anahtarlı. Cümle bazında **40/40 isabet** var.
Önbellek eksiksiz; **hiçbir metni değiştirmeye gerek yok** (seçtiğin "metinleri önbelleğe uydur"
seçeneği konusuz kaldı). Gerçek hatalar aşağıdaki dört maddede.

### Kök nedenler

1. **Kurulu uygulamanın config'i bozuk.** `%LOCALAPPDATA%\Aican\config.json` (11 Eyl 22:33)
   `tts_engine="edge"` + `tts_voice="01p4omegjS2n3rSDCM5u"` (bir **ElevenLabs voice_id**'si)
   taşıyor. edge-tts bu adı reddeder ama hatayı ancak ilk sentezde verir; açılış probu
   (`orchestrator/web_server.py:479-521`) bunu yakalayıp motoru **kalıcı Piper'a sabitler**.
   `paths.ensure_seeded()` var olan dosyayı asla ezmediği için (`paths.py:185`), 13 Eyl'de
   `--kendi-ses` ile üretilen doğru `dist/config.json` bu makineye hiç ulaşmadı.
2. **Ses önbelleği EXE'ye hiç paketlenmiyor.** `build.py` Piper `.onnx`'ini kopyalıyor
   (`--include-data-dir=...tts/voices`) ama `tts/cache` için böyle bir satır yok;
   `build/run_web.dist/tts/` altında yalnız `voices` var. Kurulumdan sonra 6490 iyi parçanın
   **hiçbiri** makinede değil.
3. **Önbellek zehirlenmesi.** `_tts_synth_cached` (`web_server.py:558-577`) koruması
   `src = state.engine.last_engine` üzerinden çalışıyor; motor düz `PiperEngine`'e sabitlenince
   `last_engine` yok → `src is None` → koruma devre dışı → Piper sesi ElevenLabs voice_id
   anahtarı altına yazılıyor. `%LOCALAPPDATA%`'daki 51 dosya tam olarak bu.
4. **`BASLAT.bat` kaynaktan çalıştırmayı başlatamıyor.** `py -3`/`python` ile sistem
   Python'ını seçiyor; bağımlılıklar `.venv`'de (sistem Python'ında `flask` bile yok).
   Senin ".bat'tan tıklayıp doğrulayayım" isteğin bu hâliyle çalışmaz.

Ayrıca `_warm_tts_cache` **tam metni** ön-ısıtıyor, tarayıcı ise **cümle parçası** istiyor —
ön-ısıtma boşa sentez yapıyor ve (3) ile birlikte zehirlenmenin taşıyıcısı oluyor.

### Hedef

Sergi, hem kaynaktan hem kurulu EXE'de önceden üretilmiş ElevenLabs sesiyle konuşsun;
ElevenLabs API anahtarı **hiç gerekmesin** (anahtar yok — önbellekte olmayan bir şey kalmadı);
motor/ses uyumsuzluğu bir daha sessizce Piper'a düşmesin.

## Uygulama

### 1. Önbelleği kuruluma göm — kopyalamadan, salt-okunur tohum dizini olarak
- `orchestrator/tts/cache.py` → `WavCache.__init__(..., seed_dir=None)`; `get()` önce yazılabilir
  dizine, isabet yoksa `seed_dir`'e bakar. `put()`/`_maybe_evict()` **yalnız** yazılabilir dizine
  dokunur (tohum salt okunur, eviction onu silemez).
- `orchestrator/paths.py` → `tts_cache_seed_dir()`: frozen'da `resource_root()/tts/cache`,
  kaynaktan çalışırken `None` (zaten yazılabilir dizinin kendisi).
- `orchestrator/web_server.py:865-870` → `WavCache(paths.tts_cache_dir(), seed_dir=paths.tts_cache_seed_dir(), ...)`.
- `build.py` → Piper sesleri desenini izle: `--include-data-dir={ORCH}/tts/cache=tts/cache`
  (sabitler `PIPER_SESLER`/`PIPER_HEDEF` komşusu olarak `TTS_ONBELLEK`/`TTS_ONBELLEK_HEDEF`).
- `build.py::verify_dist` (`:531`) → `tts/cache/*.wav` yoksa **derlemeyi düşür**; mesaj
  Whisper/Piper kapılarıyla aynı dille ("sergi ücretsiz sesle konuşur").

900 MB'ı `%LOCALAPPDATA%`'ya kopyalamak yerine yerinde okumak: ilk açılışta kopyalama
gecikmesi yok, diskte ikinci bir 900 MB yok, eviction tohumu yiyemez.

### 2. Motor↔ses uyumsuzluğunu çalışma zamanında yakala
`web_server._load_tts_async` içinde, edge motoru kurulmadan önce: `tts_voice`
edge ses adı kalıbına (`^[a-z]{2}-[A-Z]{2}-\w+Neural$`) uymuyorsa `DEFAULT_TTS_VOICE`'a düş ve
`log.warning` + `logger.log_event` ile yüksek sesle bildir. Bu, hem bu makinedeki bozuk
config'i hem de ileride müşteriye giden derlemelerde aynı tuzağı kapatır — probun sessiz
Piper sabitlemesine hiç gelinmez.

### 3. Zehirlenme deliğini kapat
`_tts_synth_cached`: koruma `state.engine`'in o anki hâline değil, **config'in istediği motora**
bakmalı. `config["tts_engine"]` ile sesi gerçekten üreten motoru (`last_engine`, yoksa
`engine.name`) karşılaştır; farklıysa `cache.put` **yapma**. Böylece Piper'a sabitlenmiş bir
oturum ElevenLabs anahtar uzayına yazamaz.

### 4. Ön-ısıtmayı cümle parçasına indir
`_warm_tts_cache` → her metni `_split_sentences_tr` ile bölüp parça parça ısıtsın
(`gen_batch_elevenlabs.py` ve tarayıcı ile aynı anahtar uzayı). Şu an ürettiği tam-metin
parçalarını kimse istemiyor.

### 5. `BASLAT.bat` doğru yorumlayıcıyı seçsin
`:bul_python` başına: `%~dp0.venv\Scripts\python.exe` varsa onu kullan. Sonrası değişmez
(KUR.bat ile kurulmuş sistem Python'ı hâlâ ikinci sıra).

### 6. Bu makinedeki kalıntıları temizle (tek seferlik, onayınla)
- `%LOCALAPPDATA%\Aican\config.json` → `tts_engine="elevenlabs"`, `tts_voice="01p4omegjS2n3rSDCM5u"`
  (6490 parçanın anahtar uzayı). Dosyayı silmek yerine iki alanı düzeltiyoruz.
- `%LOCALAPPDATA%\Aican\tts\cache\*.wav` (51 dosya, hepsi 22050 Hz Piper) → **sil**.
- `aican/cache/` (900 MB, izlenmeyen, hiçbir kod okumuyor) → **sil**.

### 7. Testler
- `orchestrator/tests` (veya `tests/`): `WavCache` tohum dizininden okur, tohuma yazmaz,
  eviction tohumu silmez.
- Geçersiz `tts_voice` + `tts_engine="edge"` → motor edge'de kalır, ses varsayılana düşer
  (mevcut `orchestrator/test_tts_yedek_yoklugu.py` desenini izle: sahte motor, ağa çıkma).
- Yedeğe düşmüş sentez `cache.put` çağırmaz.
- `tests/test_build.py`: `verify_dist` `tts/cache` yoksa `False` döner.

## Doğrulama

1. `python -m pytest` (kök) + `orchestrator/test_tts_yedek_yoklugu.py` — yeşil.
2. **Kaynaktan çalıştır** (senin istediğin adım): `BASLAT.bat` (düzeltildikten sonra çift tık;
   ben başlatırsam `.venv\Scripts\python.exe run_web.py`). Sergi sekmesinde bir oyun aç, konuştur.
3. Kanıt: `logs/session.log` → `TTS hazir (elevenlabs=01p4... + yedek: edge -> piper)`;
   `/api/speak` dönen WAV'ın başlığı **44100 Hz** olmalı (22050 = Piper = hata). Ön-ısıtma
   sonrası `orchestrator/tts/cache` dosya sayısı **6490'da kalmalı** (artıyorsa hâlâ canlı
   sentez var demektir).
4. Ancak bu geçtikten sonra `python build.py --kendi-ses` + `--kurucu`; `verify_dist` yeni
   `tts/cache` kapısından geçmeli. Kurucuyu kurup EXE'yi aç, aynı 44100 Hz kontrolünü yap.

**Not:** `build.py --kendi-ses` bizim sergimizin derlemesi için **zorunlu**; bayraksız derleme
`tts_engine`'i `edge`e zorlar, önbellek voice_id'si eşleşmez ve sergi yine ücretsiz sesle konuşur.
