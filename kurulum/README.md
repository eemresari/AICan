# AICAN — Yeni (Temiz) PC Kurulumu

Sergiye konacak, yeni formatlanmış bir Windows 11 PC'yi oyunu çalıştıracak hâle
getirme rehberi. Kurulum sırasında **internet şarttır**; sergide internet
opsiyoneldir (sesler cache'ten + Piper çevrimdışı yedeğiyle çalışır).

---

## Hangi PC, hangi profil?

Kurulum kartı `nvidia-smi` ile kendi tespit eder ve profili **otomatik önerir**;
sadece onaylaman yeter.

| Profil | Makine | Dil modeli | Whisper |
|---|---|---|---|
| `sergi5090` | **Yeni sergi PC'si** — MSI MPG Infinite X3 AI, Core Ultra 9 285K, 64 GB, **RTX 5090 32 GB** | `gemma4:26b` (MoE, 3.8B aktif, ~18 GB) | `large-v3` · float16 |
| `sergi` | Eski sergi PC'si — i5-10400F, 16 GB, GTX 1660 Ti 6 GB | `qwen3:4b-instruct-2507-q4_K_M` | `large-v3-turbo` · int8_float16 |
| `laptop` | Geliştirme laptopu — RTX 3050 Ti 4 GB | `qwen3:4b-instruct-2507-q4_K_M` | `large-v3-turbo` · int8_float16 |

Kartı elle görmek için: `python kurulum\donanim.py`

### Yeni PC'de model neden `gemma4:26b`?

32 GB VRAM'in tamamını tek bir dev modele vermek sergi için **yanlış** olurdu:
AICan'ın cevapları en fazla 12 kelime, gecikme ise çocukların ilgisini
belirliyor. `gemma4:26b` bu işin tam ortası —

- **MoE, 3.8B aktif parametre**: 25 milyar parametrelik bilgi, 4B model hızıyla.
  Dense bir 27B'ye göre kat kat hızlı; sergide cevap neredeyse anında.
- **~18 GB** (Q4_K_M) → Whisper `large-v3` (~3 GB) + 16K KV cache (~1,5 GB) +
  Windows masaüstü ile birlikte **~24 GB**; 32 GB kartta ~8 GB pay kalıyor.
- **Gemma soyu**: bu proje `gemma3:4b`'yi zaten Türkçe *doğallık* testinde
  seçmişti (qwen ile güvenlikte eşit, doğallık + hızda önde). `gemma4:26b`
  aynı soyun 6 katı büyüğü — üslup bozulmuyor, kelime dağarcığı büyüyor.

Alternatifler (denemek istersen `config.sergi5090.json` içinde `ollama_model`):
`qwen3.5:35b-a3b` (~24 GB, daha çok toplam parametre, daha dar VRAM payı) ·
`gemma4:12b` (~7,6 GB, en hızlısı, kart başka iş de yapacaksa).

### Sergi TEST MODUNDA açılıyor — modelin rolü

`config.sergi5090.json` içinde `test_mode: true`. Bu modda menüde yalnız
**Eş/Zıt Anlam + Atasözü** var, sohbet kapalı, "merhaba" doğrudan oyun menüsünü
açıyor. Ekranda **`g`** ile açılıp kapanır ve `config.json`'a kalıcı yazar.

Test modu açıkken **LLM hiç çağrılmıyor** — `/api/send` sohbeti `bridge.request`'e
gitmeden geri döner, `word_llm`'in tek kullanıcısı olan kelime oyunu da
`izinli_oyunlar` dışında kalır. Yani bu modda **kritik yol ses tanımadır**;
`large-v3` + `float16` + `beam_size 5` bu yüzden seçildi.

Buna rağmen model boşuna inmiyor: `warmup_on_start` + `keep_alive: -1` sayesinde
açılışta VRAM'e yüklenip orada kalıyor. Sergide `g` ile sohbeti açtığında ilk
ziyaretçi 18 GB'lik soğuk yüklemeyi beklemez — cevap ilk andan itibaren hızlı.
VRAM bütçesi zaten ikisini birlikte sayıyor (model + Whisper yerleşik, ~22/32 GB).

### RTX 5090'da dikkat: INT8 ÇALIŞMAZ

Blackwell (sm_120) INT8 tensor çekirdekleri farklı padding istiyor; CTranslate2
4.6.2 bu yüzden INT8'i bu mimaride **kapattı**. Whisper'ı `int8` ya da
`int8_float16` ile açmaya çalışırsan `CUBLAS_STATUS_NOT_SUPPORTED` alırsın.

- `config.sergi5090.json` bu yüzden **`float16`** kullanır — 32 GB'da zaten bol.
- `requirements.txt` **`ctranslate2>=4.6.3`** ister (CUDA 12.8 desteği 4.6.3'te geldi).
- NVIDIA sürücüsü **≥ 570** olmalı (CUDA 12.8'in tabanı).
- Yanlış profil kopyalanırsa: `web_server.py` artık CPU'ya düşmeden önce
  `float16`'yı dener, `saglik_kontrol.py` da uyumsuzluğu **HATA** olarak basar.

---

## A) Sıfırdan kurulum — projenin makinede hiç olmadığı durum

Yeni sergi PC'sinde tek dosya yeter. `kurulum\SIFIRDAN_KUR.ps1`'i USB ile taşı,
**PowerShell'i yönetici olarak** aç:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\SIFIRDAN_KUR.ps1
```

Betik sırasıyla: winget kontrolü → **Git** kurar → **Python 3.13** kurar →
ekran kartını/sürücüyü kontrol eder → depoyu `C:\aican`'a **klonlar**
(`sergi-pc-rtx5090` dalı) → `KUR.bat`'ı çağırır.

Seçenekler: `-Hedef D:\aican` · `-Dal <ad>` · `-Anahtar <elevenlabs-key>` · `-Sessiz`

> Depo özelse `git clone` sırasında GitHub kimlik penceresi açılır — kullanıcı
> adı + **PAT** (parola değil) gir.

> **Not:** winget yeni kurulan programın PATH'ini açık pencereye yansıtmaz.
> "kuruldu ama görünmüyor" dersen PowerShell'i kapat, yeniden aç, tekrar çalıştır.

## B) Proje klasörü zaten makinedeyse

`kurulum\KUR.bat` → çift tık. (USB ile kopyaladıysan bu yol daha hızlı: cache ve
ses dosyaları da beraberinde gelmiş olur.)

### KUR.bat ne yapar (11 adım)

1. **Python** sürüm kontrolü (3.10+; yoksa winget ile kurar)
2. **Ekran kartı + sürücü** tespiti — profil bunu takip eder, Blackwell'i tanır
3. **VC++ Redistributable** (Whisper/Piper DLL'leri için şart — temiz Windows'ta yoktur)
4. **pip bağımlılıkları** (`orchestrator/requirements.txt`) + ctranslate2 sürümünü basar
5. **Profil** — karta göre önerilir, onaylarsın → `config.json`; VRAM sığıyor mu der
6. **Ollama** kurar/günceller, sunucuyu başlatır, modeli indirir ve **GPU'ya
   gerçekten yerleştiğini doğrular** (`size_vram`)
7. **Whisper** modelini ön-indirir — config'te *seçili* olanı (sergide internet gerekmesin)
8. **Ses varlıkları** — Piper çevrimdışı sesini indirir, ElevenLabs cache'ini denetler
9. **ElevenLabs anahtarı** (opsiyonel; boşsa ücretsiz edge-tts + Piper çalışır)
10. Masaüstüne **AICAN Baslat** kısayolu; istersen **otomatik başlatma**
11. **Sağlık kontrolü** → `0 HATA` görmeden sergiye çıkma

Soru sormadan kurmak için: `KUR.bat --sessiz` (profil karttan seçilir, otomatik=evet).

### Model indirmesi takılırsa — kurulumu bloke etmesin

`gemma4:26b` 18 GB; sallanan bir ağda `ollama pull` **geri sarar** (inen GB artıp
azalır). Sebep: Ollama 4 paralel akış kullanıyor, biri kopunca o parçayı baştan
alıyor. İnen parçalar diskte kalır, sıfırdan başlamaz.

```powershell
kurulum\MODEL_INDIR.bat            # akışı 1'e indirir, kesilirse kaldığı yerden tekrar dener
kurulum\MODEL_INDIR.bat gemma4:12b # daha küçük model (7,6 GB)
```

> Ayarın sunucu tarafında geçerli olması için Ollama'yı **sistem tepsisinden
> Quit** edip yeniden açman gerekebilir.

**Önemli:** Sergi `test_mode: true` ile açıldığı için **LLM kullanılmıyor.**
Model inmeden de Whisper, oyunlar ve sesler tam çalışır — indirmeyi sonraya
bırakıp kurulumun geri kalanını bitirebilirsin. Model sonradan indiğinde
`BASLAT.bat` onu açılışta VRAM'e yükler.

---

## C) Elden taşınması gereken TEK şey: ses önbelleği

`orchestrator/tts/cache/` (~830 MB) ElevenLabs kredisiyle üretilmiş hazır
seslerdir ve `.gitignore`'da — **klonla gelmez**.

```powershell
# ESKI PC'de — canlı anahtarları paketle (ölü cache'i almaz)
cd orchestrator
python -m tts.paket_hazirla            # önce rapor: kaç dosya, kaç MB
python -m tts.paket_hazirla --kopyala  # tts\sergi_paketi\ oluşur

# USB ile taşı, YENI PC'de:
#   sergi_paketi\cache\  -> C:\aican\orchestrator\tts\cache\
#   (voices\ zaten KUR.bat tarafından indirildi)

# YENI PC'de doğrula — EKSIK = 0 görmelisin
cd C:\aican\orchestrator
python -m tts.gen_batch_elevenlabs --eksik
```

Taşımazsan oyun yine çalışır: replikler canlı sentezlenir (ElevenLabs kredisi +
gecikme), anahtar da yoksa ücretsiz edge/Piper sesine düşer.

---

## D) Başlat & doğrula

- **Başlat:** Masaüstündeki `AICAN Baslat` (veya proje kökünde `BASLAT.bat`).
  Ollama'yı gerekirse başlatır, sunucuyu kaldırır, sergi + kontrol sekmelerini açar.
- **Sağlık kontrolü (istediğin an):** `python kurulum\saglik_kontrol.py`
- **Test modu:** herhangi bir ekranda **`g`** → sadece Eş/Zıt + Atasözü, sohbet kapalı,
  "merhaba" doğrudan oyun menüsü açar. Ayar kalıcıdır.
- Ekran kısayolları: `f` tam ekran · `d` sürekli mikrofon aç/kapa · `s` ses aç/kapa ·
  `m` mikrofon seviye göstergesi · **`k` ortam gürültüsünü yeniden ölç**.

### Ortam gürültüsü kalibrasyonu

Ekran ilk açıldığında **4 saniye boyunca ortamı dinler** ("Ortam sesi ölçülüyor —
lütfen sessiz olun" yazar) ve konuşma eşiğini o salona göre kendi kurar. Bu süre
boyunca **kimse konuşmasın**, yoksa ölçüm reddedilir (ekranda uyarır) ve
varsayılan ayarlarla devam eder.

- Ölçüm 12 saat geçerlidir; sayfa yenilense de tekrar sormaz.
- **Salon dolunca/boşalınca ya da mikrofonun yeri değişince `k` ile yeniden ölç.**
- `m` göstergesinde `kalib done` + ölçülen alt eşik görünür; çubuk kırmızı çizgiyi
  yalnız konuşurken geçmeli. Sürekli geçiyorsa ortam gürültülü → `k`.
- Ölçüm reddedilse bile sistem canlı olarak ortamı takip etmeyi sürdürür,
  sadece daha yavaş uyum sağlar.
- Sorun çıkarsa `config.json` → `voice_input_calibration_enabled: false` eski
  (elle ayarlı eşikli) davranışı birebir geri getirir.

## Sergi günü kontrol listesi

- [ ] `saglik_kontrol.py` → **0 HATA**
- [ ] Model GPU'da mı? (`ollama ps` → `size_vram` dolu; sağlık kontrolü de bakar)
- [ ] Whisper `cuda` + `float16` mı? (`/api/durum` ya da sağlık kontrolü)
- [ ] TTS cache taşındı mı? (`gen_batch_elevenlabs --eksik` → 0)
- [ ] Ses geliyor mu? (ilk tıklamadan sonra — tarayıcı ses kilidi ilk dokunuşta açılır)
- [ ] Mikrofon izni verildi mi? (kiosk modunda sorulmaz, ama aygıtı kontrol et)
- [ ] Test modu rozeti yanıyor mu? (`g`)
- [ ] Her iki oyundan birer tur oyna
- [ ] Ses seviyesi / mikrofon mesafesi sahada ayarlandı mı?
- [ ] **Ortam kalibrasyonu salon son halindeyken yapıldı mı?** (`k`, 4 sn sessizlik —
      `m` göstergesinde `kalib done` görünmeli)

## Sorun giderme

| Belirti | Çare |
|---|---|
| "Python bulunamadi" | KUR.bat'ı tekrar çalıştır; olmadıysa python.org'dan kur ("Add to PATH" işaretli) |
| "DLL load failed" (faster_whisper/piper) | VC++ Redistributable eksik → https://aka.ms/vs/17/release/vc_redist.x64.exe kur, sağlık kontrolünü tekrar koş |
| **`CUBLAS_STATUS_NOT_SUPPORTED`** | RTX 50 serisinde INT8 → `config.json`'da `whisper_compute_type` **float16** olmalı; `pip install -U "ctranslate2>=4.6.3,<5"` |
| **Cevaplar 10 kat yavaş, `size_vram=0`** | Ollama kartı tanımamış → `winget upgrade -e --id Ollama.Ollama --source winget` + NVIDIA sürücüsünü güncelle |
| Sağlık kontrolü "modelin %X'i GPU'da" diyor | Model karta sığmıyor → daha küçük model (`gemma4:12b`) ya da `num_ctx` düşür |
| **İnen GB sürekli artıp azalıyor** | Ollama 4 paralel akış kullanıyor, biri kopunca o parça baştan alınıyor → `kurulum\MODEL_INDIR.bat` (akışı 1'e indirir + kaldığı yerden tekrar dener) |
| Model inmiyor | İnterneti kontrol et; `MODEL_INDIR.bat` dene; olmazsa `ollama pull <model>` elle |
| Ses yok | Tarayıcıda sayfaya bir kez tıkla; `s` tuşu ses kapalı olabilir; sağlık kontrolüne bak |
| Sesler robot gibi / farklı | TTS cache taşınmamış → C bölümü |
| Mikrofon çalışmıyor | Tarayıcı adres çubuğu → mikrofon izni; Windows ayarları → gizlilik → mikrofon |
| **Kimse konuşmadan kendi kendine dinlemeye başlıyor** | Ortam gürültüsü eşiğin üstünde → `k` ile yeniden kalibre et (4 sn sessizlik). `m` ile eşiği doğrula |
| **Ölçüm sırasında "Ortam ölçümü yapılamadı" çıktı** | Ölçüm sırasında konuşulmuş ya da ortam çok gürültülü → sessizliği sağlayıp `k` |
| `git clone` yetki hatası | Depo özel — GitHub kullanıcı adı + **PAT** gir (parola değil) |
