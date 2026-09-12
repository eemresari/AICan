# Aican — Teslim Kontrol Listesi

Bu belge **senin** içindir (Luden Studio), müşteri için değil. Müşteriye giden
belge `docs/KURULUM.md`'dir.

Teslim modeli: **site üzerinden açık indirme yok.** İsteyen kişi siteden talep
açar; sen Drive linkini ve anahtarı e-postayla elden gönderirsin. Kimin hangi
anahtarı aldığı Lisans Merkezi'nin kayıtlarında durur.

---

## A. Paketi üret (sürüm başına bir kez)

```powershell
cd 01-Projects\aican
.venv\Scripts\python.exe build.py            # dist\web.pak + build\run_web.dist\Aican.exe
.venv\Scripts\python.exe build.py --kurucu   # kurucu + ZIP + SHA-256
```

Ön koşullar (bir kez):

- `~/.luden-lisans/urunler/aican/icerik.key` var (Lisans Merkezi →
  Aican → *Anahtar çifti üret*). Yoksa build ilk adımda durur.
- `npx` (Node.js) kurulu — `javascript-obfuscator` onunla çekilir
  (`winget install OpenJS.NodeJS.LTS`). Yoksa `--obfuscate-yok` ile geç;
  paket yine `web.pak` içinde şifrelenir, yalnız JS okunabilir kalır
  (çözülürse).
- Inno Setup 6: `winget install JRSoftware.InnoSetup`.
- Piper çevrimdışı sesi indirilmiş olmalı — yoksa build ön kontrolde durur:
  `python -m piper.download_voices tr_TR-dfki-medium --data-dir orchestrator/tts/voices`
- Whisper CT2 modeli build sırasında `dist/whisper/<boyut>/` altına gömülür
  (yerel HF önbelleğinden kopyalanır; önbellek boşsa bir kez internetten iner).
- Boyut (2026-09-12 ölçümü): standalone dist **~4,0 GB**, kurucu EXE ve ZIP
  **~2,4 GB** (CUDA + Whisper modeli + Piper sesi dahil). Derleme ~7 dakika,
  kurucunun sıkıştırması ~8 dakika sürer. ZIP, EXE'den neredeyse hiç küçük
  değildir (içerik zaten sıkışık) — ZIP yalnız tarayıcı/e-posta geçidi için.

1. `python build.py` çıktısında obfuscation ve `web.pak` üretimini gör; ardından
   `build\run_web.dist\` klasörünün oluştuğunu doğrula (`build.verify_dist`
   çağrılır — ham `web/`, `ai/`, `main.py` **yok**; `web.pak`, `lisans_web/`,
   `assets/` **var** diyorsa devam et).
2. `--kurucu` önce dist'i tarar: `aktivasyon.dat`, `*.key`, `lisanslar.json`,
   `logs\`, `.tarayici_profili\`, ham `web\`/`ai\`, `main.py` ya da içinde dolu
   `tts_elevenlabs_api_key` olan `config.json` bulursa **durur**. Bu dosyalar
   normalde `%LOCALAPPDATA%\Aican`'da olur; dist'e düşmüşlerse test sırasında
   `AICAN_DATA_ROOT` ile denenmiş ve unutulmuştur.
3. Sonunda yazdırılan **SHA-256** satırını kopyala. O özet e-postaya girecek.
4. Çıktılar: `dist\Aican-Kurulum-0.9.0.exe` ve yanındaki `.zip` (+ `.zip.sha256`).
   **Müşteriye giden dosya ZIP'tir.**

> Sürüm numarası tek yerde: `surum.py`. Artırınca kurucu adı, EXE damgası ve
> "Program Ekle/Kaldır" kaydı birlikte değişir. İlk gerçek müşteri teslimi
> **1.0.0** olacak; 0.9.x kendi test kurulumlarını işaretler.

### Build sonrası doğrulama

Plan (`docs/plans/2026-09-11-lisans-ve-kurucu-entegrasyonu.md`, "Doğrulama")
maddeleriyle birebir:

```powershell
.venv\Scripts\python.exe -m pytest -q
(Get-Item build\run_web.dist\Aican.exe).VersionInfo   # CompanyName / ProductVersion dolu mu
Get-ChildItem build\run_web.dist -Directory | Select-Object Name  # web/ ai/ YOK, lisans_web/ assets/ VAR
```

Sonra sırayla dene:

| # | Adım | Beklenen |
|---|---|---|
| 1 | Merkez'den **TEST (1 dakika)** anahtarı üret | `lisans.dogrula()` okur; içerik anahtarı `web.pak`'ı çözer |
| 2 | `build\run_web.dist\` içeriğine bak | Ham `web/`, `ai/`, `main.py` yok; `web.pak`, `lisans_web/`, `assets/` var |
| 3 | `Aican.exe` özellikleri | CompanyName/ProductVersion dolu (yukarıdaki `VersionInfo` komutu) |
| 4 | Kurucuyu **Program Files'a** kur, ilk aç | Lisans penceresi gelir, tarayıcı **açılmaz**; anahtar sonrası `%LOCALAPPDATA%\Aican\{aktivasyon.dat,config.json,logs\}` oluşur, iki sekme açılır, `/app.js` 200, `/yok.js` 404 |
| 5 | **Demo anahtar** ile aç | Filigran görünür, `g` tuşu/TEST toggle'ı yok, "merhaba" → oyun menüsü, sohbet kapalı, Ollama kapalıyken bile çalışır |
| 6 | **Kalıcı anahtar** ile aç (Ollama açık, model inik) | Filigran yok, sohbet açık ve yanıt veriyor |
| 7 | Kaynaktan `python run_web.py` çalıştır | Lisans hiç sorulmaz, `test_mode` `config.json`'dan okunur, davranış değişmemiş |
| 8 | Kaldır → yeniden kur | Anahtar sorulmaz, `%LOCALAPPDATA%\Aican` yerinde (aktivasyon korunur) |

Elle (kullanıcı, otomatikleştirilmedi): Windows saatini 5 gün geri al →
"saat" mesajı; kurulum klasörünü başka makineye kopyala → "başka
bilgisayara ait"; **GPU'suz makinede açılış** → Whisper'ın CPU'ya düşüp
düşmediği / ne tür bir hata verdiği not edilip `docs/KURULUM.md`'ye işlenir
(şu an bilinmiyor, plan bunu bilerek açık bırakıyor).

## B. Anahtar üret

```
01-Projects\LisansMerkezi\MERKEZ.bat
```

Key ver sekmesi → **Aican** → süre → kurum adı → *Yeni üret ve ver* →
`.dat olarak kaydet`.

- Süre seçimi kuruma göre: deneme için 7-14 gün, değerlendirme için 30 gün.
- Kurum adını yaz — oyundaki filigranda o görünür. Havuz anahtarı verirsen
  filigranda kurum yerine `Demo — #42` çıkar.
- Satılmış kurulum için **Kalıcı** seç: süre denetimi olmaz, filigran çıkmaz.

Anahtar **tek makineye** bağlanır (ilk kullanıldığı makineye). Müşteri
bilgisayar değiştirirse yeni anahtar üret; eskisini iptal etmen gerekmez.

Ayrıntı: `01-Projects/LisansMerkezi/README.md`.

## C. E-postayı gönder

Gönderilecek dört şey:

1. Drive linki (ZIP).
2. ZIP'in SHA-256 özeti.
3. `lisans.dat` (ek olarak) **veya** anahtar metni.
4. `docs/KURULUM.md` — PDF'e çevirip ekle ya da içeriğini e-postaya yapıştır
   (ZIP'in içinde kısa `KURULUM.txt` olarak zaten gider; `docs/KURULUM.md`
   varsa o da ZIP'e eklenir).

E-postada mutlaka geçmesi gereken cümle: **"Windows mavi bir uyarı
gösterebilir; 'Daha fazla bilgi' → 'Yine de çalıştır' deyin."** Sertifika
satın alınmadığı için bu uyarı ilk kurulumlarda çıkar ve destek çağrılarının
en yaygın sebebidir.

Aican'a özgü ek cümle: kalıcı anahtarla teslim ediyorsan sohbetin çalışması
için müşterinin Ollama'yı ayrıca kurması ve modeli indirmesi gerektiğini
(`docs/KURULUM.md` §5) açıkça belirt — kurucu bunu **yapmaz**.

> **Sertifika neden yok:** Microsoft Mart 2024'te EV sertifikasının SmartScreen
> avantajını kaldırdı; Azure Trusted Signing Türkiye'yi desteklemiyor. Kalan
> tek yol OV sertifikası, o da itibar birikene kadar uyarıyı engellemiyor.
> Karar KimyaLab'da alındı (`KimyaLab/docs/TESLIM.md`), burada aynen geçerli.

## D. Kayıt

Lisans Merkezi anahtarı otomatik "verildi" olarak işaretler. Müşteri anahtarını
kaybederse Kayıtlar sekmesinden aynı anahtar yeniden görünür — yenisini üretme.

---

## Yeni sürüm çıkarken

1. `surum.py` içindeki `SURUM`'u artır.
2. A adımını tekrarla; yeni ZIP ve **yeni** SHA-256.
3. Eski anahtarlar çalışmaya devam eder — anahtar sürüme değil ürüne bağlıdır
   (yalnız `lisans.PAKET_NO` artırılırsa "bu anahtar programın eski bir sürümü
   için üretilmiş" mesajı çıkar; o zaman Merkez'de de `paket_no` artırılır ve
   dağıtılmış anahtarlar yenilenir).
4. Müşteri programı kaldırıp yeniden kurabilir; `%LOCALAPPDATA%\Aican`
   silinmediği için ayarları ve aktivasyonu yerinde kalır.

## Kabul edilen sınırlar

- Lisans **dosyasının** başka bir makinede yeniden aktive edilmesi
  engellenemez (bir kez aktive olduktan sonra kilitlenir, ama ilk
  aktivasyondan önce dosya kimin elindeyse o kullanır). `son_kullanim_ts`
  mutlak tavanı bunu süreyle sınırlar.
- Anakart değişince yeniden aktivasyon gerekir (HMAC anahtarı birincil
  bileşenden türetilir).
- `web.pak` lisanslı kullanıcı tarafından çözülebilir — korunan şey lisansı
  **olmayan** kişinin içeriği görememesi. JS obfuscation ek maliyet, engel
  değil.
- Konuşma tanıma ve seslendirme **çevrimdışı çalışır** (Whisper modeli ve
  Piper sesi pakette gelir); internet yalnız sesli yanıt kalitesini artırır
  (edge-tts çevrimiçi birincil, kesilince Piper'a düşülür). Kalıcı lisanstaki
  **sohbet** ise yerel bir Ollama sürecine bağımlıdır — o kurulmamışsa
  "Şu an düşünemiyorum" yanıtı döner.

## Depo güvenliği (her teslimden bağımsız)

- `~/.luden-lisans/` **asla commit edilmez** — özel anahtar sızarsa herkes
  Aican anahtarı üretebilir.
- Anahtar çifti üretimi **geri alınamaz**; ürettikten hemen sonra Lisans
  Merkezi'nden *Depoyu yedekle*.
- Oyunun içinde hiçbir anahtar yoktur, yalnız açık anahtar durur
  (`lisans.ACIK_ANAHTAR_HEX`). EXE'yi parçalayan biri anahtar **üretemez**.
