# Aican — Kurulum ve Anahtar Kılavuzu

Bu belge Aican'ı ilk kez kuran kişi içindir. Teknik bilgi gerektirmez.

**Gereken:**

- Windows 10 veya 11 (64-bit), yönetici hakkı olan bir hesap.
- **NVIDIA ekran kartı.** Konuşmayı yazıya çeviren model (Whisper) GPU'da
  çalışır; gerekli CUDA kütüphaneleri kurulumun içinde gelir, ayrıca bir şey
  kurmanız gerekmez.
- **İlk açılışta internet bağlantısı.** İki sebepten: (1) konuşma tanıma
  modeli (Whisper large-v3-turbo, ~1,5 GB) ilk açılışta internetten iner ve
  diskte kalır; (2) sesli yanıt üretimi (edge-tts) her seferinde internete
  bağlanır — bu yüzden sergi makinesinin **sürekli** internete çıkabilmesi
  gerekir, yalnız ilk açılışta değil.
- Google Chrome ya da Microsoft Edge (Windows'ta hazır gelir) — sergi iki
  sekmede açılır (sergi ekranı + kontrol paneli).

---

## 1. Dosyayı indirin ve açın

Size e-postayla iki şey gönderildi:

1. Bir **indirme bağlantısı** (Google Drive) — içinde
   `Aican-Kurulum-0.9.0.zip` var.
2. Bir **anahtar** — ya `lisans.dat` adlı bir dosya ya da `LDN1.` ile başlayan
   uzun bir metin.

ZIP'i indirin, sağ tık → **Tümünü ayıkla**. İçinden
`Aican-Kurulum-0.9.0.exe` çıkar.

> **Dosyanın bozulmadığını doğrulamak isterseniz** (isteğe bağlı): e-postadaki
> SHA-256 özetiyle karşılaştırın. PowerShell'de:
> ```powershell
> Get-FileHash .\Aican-Kurulum-0.9.0.zip -Algorithm SHA256
> ```
> Çıkan değer e-postadakiyle aynı olmalı.

## 2. "Windows bilgisayarınızı korudu" uyarısı

Kurucuya çift tıkladığınızda mavi bir SmartScreen penceresi çıkabilir. Bu bir
virüs uyarısı **değildir**: Windows, henüz çok sayıda kişi tarafından
indirilmemiş yeni dosyalar için bunu gösterir.

**Yapılacak:** pencerede **Daha fazla bilgi** yazısına tıklayın, sonra çıkan
**Yine de çalıştır** düğmesine basın.

Doğru dosyada olduğunuzu şuradan teyit edebilirsiniz: aynı pencerede
*Yayımcı* satırında **Luden Studio** yazar.

## 3. Kurulum

Kurucu sizi birkaç adımda yönlendirir. Varsayılanları kabul etmeniz yeterli:

- Kurulum yeri: `C:\Program Files\Luden Studio\Aican`
- Başlat menüsüne kısayol eklenir; isterseniz masaüstüne de.

Kurulum dosyaları büyüktür (konuşma tanıma ve ekran kartı kütüphaneleri
dahil, ~2 GB); açılması birkaç dakika sürebilir.

Kurulum bitince Aican'ı Başlat menüsünden **Aican** ile açarsınız.

## 4. Anahtarı girme

İlk açılışta **Aican — Lisans** penceresi gelir. İki yol var, ikisi de aynı
sonuca varır:

- **Lisans dosyası seç...** → size gönderilen `lisans.dat` dosyasını seçin.
- Ya da anahtar metnini (`LDN1.` ile başlayan uzun satır) kutuya **yapıştırıp**
  **Anahtarı kullan** deyin.

Anahtar kabul edilirse pencere kapanır ve iki tarayıcı sekmesi açılır (sergi
ekranı ve kontrol paneli). Anahtar bu bilgisayara bağlanır; her açılışta
yeniden girmeniz **gerekmez**.

İlk açılışta konuşma tanıma modeli henüz diskte yoksa **"Whisper modeli
iniyor"** benzeri bir bekleme olur (internet hızına göre birkaç dakika). Bu
işlem yalnızca ilk açılışta olur.

### Deneme (demo) anahtar ile kalıcı anahtar arasındaki fark

**Deneme anahtarında:**
- Yalnızca iki oyun oynanır: **eş/zıt anlam** ve **atasözü**.
- **Sohbet kapalıdır** — Aican'a serbest yazı/konuşma ile mesaj yazılamaz.
- Ekranın köşesinde kurum adı ve son kullanım tarihini gösteren soluk bir
  **filigran** durur.
- Ollama (aşağıya bakın) kurulu olmasa da çalışır — deneme sürümü ona hiç
  ihtiyaç duymaz.

**Kalıcı anahtarda:** tüm oyunlar ve serbest sohbet açıktır, filigran yoktur;
ama sohbetin çalışması için Ollama'nın ayrıca kurulmuş ve **çalışıyor**
olması gerekir (bkz. aşağıdaki adım).

## 5. Kalıcı lisans için: Ollama kurulumu (ayrı adım)

Bu adım **yalnızca kalıcı anahtarla** ilgilidir; deneme anahtarında
atlayabilirsiniz. Aican'ın kurucusu Ollama'yı **kurmaz ve başlatmaz** —
sohbetin çalışması için aşağıdakileri elle yapmanız gerekir:

1. [ollama.com/download](https://ollama.com/download) adresinden Ollama'yı
   Windows'a kurun.
2. Bir komut satırında (PowerShell veya CMD) modeli indirin:
   ```
   ollama pull qwen3:4b-instruct-2507-q4_K_M
   ```
   İndirme ~2,5 GB — internet hızına göre 5-15 dakika sürer.
3. Ollama'nın **Aican her açıldığında arka planda çalışıyor** olması gerekir
   (kurulumdan sonra normalde otomatik başlar; sistem tray'de görünür). Ollama
   kapalıyken Aican yine açılır, oyunlar oynanır; yalnız sohbet isteğine
   "Şu an düşünemiyorum, birazdan tekrar dener misin?" diye kibar bir yanıt
   döner (aşağıdaki tabloya bakın).

## 6. Kamera veya donanım gerekmiyor

Aican'ın çalışması için kamera ya da harici donanım gerekmez; ziyaretçi
mikrofonla konuşur ya da yazıyla yanıt verir, ekrandaki 96×96 ışık matrisi
tepki verir.

---

## Hata mesajları ne anlama geliyor?

Lisans penceresinde çıkabilecek yedi durum:

| Pencerede yazan | Anlamı | Ne yapmalı |
|---|---|---|
| Bu bilgisayarda kayitli bir anahtar yok. Lisans dosyanizi secin ya da anahtar metnini yapistirin. | Normal ilk açılış | Anahtarınızı girin |
| Sureniz doldu. Devam etmek icin yeni bir anahtar girin. | Deneme anahtarının süresi bitti | Bizden yeni anahtar isteyin |
| Bu kurulum baska bir bilgisayara ait. Bu makine icin yeni bir anahtar gerekiyor. | Anahtar başka makineye bağlanmış | O makine için verilen anahtar burada çalışmaz; yeni anahtar isteyin |
| Sistem saati geri alinmis gorunuyor. Saati duzeltip programi yeniden baslatin. | Bilgisayarın tarihi geriye çekilmiş | Windows saatini doğru tarihe getirip programı yeniden açın |
| Bu anahtar gecerli degil. | Metin eksik/bozuk kopyalanmış olabilir | Anahtarın tamamını, başındaki `LDN1.` dahil kopyalayın |
| Bu anahtar programin eski bir surumu icin uretilmis. | Program güncellendi, anahtar eski | Bizden bu sürüm için anahtar isteyin |
| Bu anahtar Aican icin degil; baska bir oyunun anahtari. | Başka bir oyunun anahtarı | Doğru anahtarı isteyin |

Lisans penceresi dışındaki durumlar:

| Ne oluyor | Anlamı | Ne yapmalı |
|---|---|---|
| "Şu an düşünemiyorum, birazdan tekrar dener misin?" | Ollama çalışmıyor ya da model henüz `ollama pull` ile inmemiş (yalnız kalıcı anahtarda görülür; demoda sohbet zaten kapalı) | Ollama'nın açık olduğundan ve modelin indiğinden emin olun (yukarıdaki adım) |
| Açılış uzun sürüyor / "Whisper modeli iniyor" | İlk açılışta konuşma tanıma modeli internetten iniyor | Bekleyin; yalnızca ilk açılışta olur, sonraki açılışlar hızlıdır |

**Ekran kartı yoksa ne olur?** Bilinmiyor — bu sürüm yalnız NVIDIA ekran
kartlı makinede elle test edildi, başka bir donanım varsayımıyla önceden bir
söz **veremiyoruz**. GPU'suz bir makinede denemeniz gerekirse önce bize
danışın; ne olduğunu görüp bu belgeyi güncelleriz.

## Sık sorulanlar

**Anahtar neden bu bilgisayara bağlanıyor?**
Anahtar süreli olduğu için, ilk kullanıldığı makineye bağlanır. Bilgisayar
değiştirirseniz bize yazın, yeni bir anahtar üretiriz.

**Bilgisayarı formatlarsam / donanım değiştirirsem?**
Küçük değişiklikler (RAM, ekran kartı) sorun çıkarmaz. Anakart veya disk
değişirse "başka bilgisayara ait" mesajı gelebilir; yeni anahtar isteyin.

**İnternet gerekiyor mu?**
Evet — hem ilk açılışta (konuşma tanıma modeli iner) hem de her açılışta
(sesli yanıt üretimi internet üzerinden çalışır). SprayTarih ya da
KimyaLab'ın aksine Aican tamamen çevrimdışı çalışmaz.

**Oyun açıldı ama pencere boş / siyah?**
Chrome veya Edge kurulu olmalı; ikisi de yoksa varsayılan tarayıcı açılır ve
tam ekran için **F11**'e basmanız gerekir.

**Ayarlarım, oturum kayıtlarım nerede duruyor?**
Aktivasyon, ayarlar (`config.json`) ve loglar
`%LOCALAPPDATA%\Aican` klasöründedir (log dosyası:
`%LOCALAPPDATA%\Aican\logs\session.log`). Programı kaldırdığınızda bu klasör
**silinmez** — yeniden kurunca anahtarınızı yeniden girmeniz gerekmez.
Tamamen temizlemek isterseniz klasörü elle silin.

**Nasıl kaldırırım?**
Ayarlar → Uygulamalar → **Aican** → Kaldır.

## Destek

Sorun devam ederse `%LOCALAPPDATA%\Aican\logs` klasörünün içeriği ve hata
penceresinin fotoğrafıyla birlikte bize yazın.
