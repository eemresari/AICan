# AICAN — Oyun Modu Yol Haritası

> **DURUM (güncel):** Faz 0 + Faz 1 + **Faz 2 (duygusal derinlik)** tamamlandı ve test edildi.
> Backend uçları Flask test_client ile uçtan uca doğrulandı (insist + outcome JSON'da dönüyor);
> game_engine birim testi geçti; JS sözdizimi temiz.
> **Faz 3 (Kelime Türetme) kodlandı ve backend testleri geçti** (LLM + 1 tekrar hakkı + çift ekran 20 sn zaman barı).
> Kalan: tarayıcıda canlı oynanış onayı (Ollama açıkken — kelime kalitesi/süre/duygular gözle).
>
> **Onaylanan kararlar:** (1) Önce TKM, kelime sonra ✓ · (2) Dokunmatik butonlar,
> sadelik korunarak ✓ · (3) Hile dozajı ince ayarlı, belli değil — AI ~%45 kazanır,
> yine de kaybedip şaşırabilir ✓

> **Sergi teması güncellemesi:** "Yapay zekânın duyguları var mı?"
> Mevcut sohbet + jest sistemi **aynen korunur**; üstüne ziyaretçinin AI ile
> **oyun oynayabildiği** bir mod eklenir. Önemli olan: AI'nın kazanınca/kaybedince
> **gerçek bir insan gibi duygusal tepki vermesi** — hatta ara sıra hile yapması,
> ısrar etmesi, üst üste kaybedince şaşırması/sinirlenmesi.

---

## 1. Temel ilke — "her şeyi LLM'e sordurmuyoruz"

Oyun mantığı ve duygu seçimi **deterministik kod** ile yürür (hızlı, güvenilir, sergi
ortamında çökme riski yok). Local AI (Ollama) yalnızca **dil gerektiren** yerlerde
ve **lezzet/replik üretiminde** devreye girer.

| Görev | Kim karar verir? |
|---|---|
| Taş-kağıt-makas AI hamlesi | Deterministik kod (rastgele / hile) |
| Kazanma/kaybetme sonucu | Deterministik kod |
| Hangi duygunun (jestin) oynayacağı | Deterministik kod (jest havuzundan) |
| Üst üste kaybetme → endişe/korku/öfke | Deterministik kod (rastgele atama) |
| Kelime türetme oyununda kelime/geçerlilik | Local AI (LLM) |
| Repliklerin metni ("yine mi kaybettim...") | Şablon + opsiyonel LLM lezzeti |

---

## 2. Akış (kullanıcının gördüğü)

```
Ziyaretçi: "OYUN OYNAYALIM"  (yazılı ya da sesli)
        ↓  (LLM'e GİTMEZ — sabit/hazır cevap)
AI: "Tamamdır! Hangi oyunu oynamak istersin?
     1) Taş Kağıt Makas
     2) Kelime Türetme"
        ↓  (kullanıcı: "1" / "taş kağıt makas" / "kelime")
   → seçilen oyunun modu aktive olur
        ↓
[Taş Kağıt Makas]
Ziyaretçi: "taş"   (sesli/yazılı)
        ↓  AI hamlesini seçer (göremeden rastgele — ya da hile)
Sergi ekranı: AI'nın hamlesi büyük emoji + sonuç + DUYGU JESTİ
   - AI kazandı → 😊/↑ sevinç + ekran SARI yanar
   - AI kaybetti → 💧/↓ üzüntü, bazen "bir daha oynayalım" ısrarı
   - üst üste kaybetti → ❗şaşkınlık → 🔥/⚡ öfke/korku (rastgele)
   - berabere → ❓ merak
        ↓
"Çıkış" / "dur" / boşta kalma → sohbet moduna döner
```

> "OYUN OYNAYALIM" girildiğinde gelen menü cevabı **kesinlikle sabittir** (LLM üretmez),
> böylece her zaman aynı net seçenekler çıkar.

---

## 3. Duygu → Jest eşlemesi (mevcut 31 jesti yeniden kullanır)

Hiç yeni görsel/jest üretmeden, var olan dağarcıkla:

| Oyun olayı | Jest havuzu (rastgele seçilir) | Ek efekt |
|---|---|---|
| **AI tur kazandı** | `gurur` ↑, `mutluluk_yogun` 😊, `nese` 🏀 | **ekran sarı** + böbürlenme repliği |
| **AI kazanma serisi (2+)** | `gurur` (yoğunluk artar), `hayranlik` ⭐ | giderek artan ukalalık |
| **AI tur kaybetti** | `uzgun_yavas` 💧, `hayal_kirikligi` ↓ | bazen "bir daha?" ısrarı |
| **AI kaybetme serisi (2)** | `saskinlik` ❗ | "yine mi?!" |
| **AI kaybetme serisi (3+)** | rastgele `ofke` 🔥 / `korku` ⚡ / `panik` ✨ / `uzgun_derin` ☹ | (endişe ≈ korku) |
| **Berabere** | `soru_isareti` ❓, `merak`, `kararsiz` | "aynı şeyi mi düşündük?" |
| **Hile anı** | `gurur` / `nese` + sinsi replik | (opsiyonel görsel ipucu) |
| **Oyun başlangıcı / menü** | `selamlama` 👋 / `nese` | — |
| **AI hamlesini düşünürken** | `dusunce` / `bekle` 🕐 | kısa "düşünme" beklemesi |

---

## 4. Mimari kararı — oyun mantığı nerede yaşıyor?

**Öneri: Backend (Python `orchestrator/`)** içinde yeni bir `game_engine.py` modülü.

Neden backend:
- Oyun durumu (skor, seri, aktif oyun) tek yerde, tek ziyaretçili kiosk için ideal.
- Kelime oyunu zaten LLM'e (llm_bridge) erişmek zorunda — backend'de doğal.
- Oturum loglaması (`session_logger.py`) Python'da; oyunları da loglarız.
- Mevcut `/api/send` deseni korunur; oyun **paralel yol** olur, sohbet bozulmaz.

Frontend (`control.js`) sadece **ince yönlendirici**: "OYUN OYNAYALIM" hazır komutunu
yakalar, mod'u "oyun"a alır, sonraki girdileri `/api/game/*` uçlarına yollar, sergi
ekranına oyun mesajlarını broadcast eder.

> **Sohbet çekirdeği (`llm_bridge.py`, `system_prompt.txt`, `gestures.json`) DEĞİŞMEZ.**
> Oyun modu ek katman olarak gelir.

---

## 5. Faz faz yol haritası

### Faz 0 — Tasarım & altyapı (davranış değişikliği yok)
- [ ] `game_engine.py` iskeleti: `GameSession` durum makinesi (boşta / menü / TKM / kelime).
- [ ] Duygu havuzu tablosunu koda dök (yukarıdaki eşleme).
- [ ] BroadcastChannel protokol genişletmesi: yeni mesaj tipleri
      `game_menu`, `game_ai_move`, `game_result`, `game_exit`.
- [ ] Hazır komut sistemi: girdi normalize + eşleştirme ("oyun oynayalım", "oyun", "1", "taş"...).

### Faz 1 — Taş Kağıt Makas MVP (duygu vitrini)
- [ ] Backend `GameEngine`: TKM kuralları, AI hamlesi (rastgele), sonuç, skor, seri sayacı.
- [ ] Deterministik duygu seçimi (kazandı/kaybetti/berabere/seri).
- [ ] Uçlar: `POST /api/game/start`, `POST /api/game/move`, `POST /api/game/exit`.
- [ ] `control.js`: "OYUN OYNAYALIM" hazır komut yakalama → menü → oyun moduna geçiş/yönlendirme.
- [ ] `app.js` / sergi ekranı: menüyü göster, kullanıcı+AI hamlesini (emoji) göster,
      sonucu göster, duygu jestini oynat, **kazanınca sarı ışık**.
- [ ] Tam döngü manuel test (yaz + ses ile "taş").

### Faz 2 — Duygusal derinlik & hile ✓
- [x] Seriye bağlı tırmanan duygular (`_emotion_for`: şaşkınlık→öfke/korku/panik).
- [x] AI kaybedince "bir daha oynayalım" ısrarı (bazen) — `INSIST_1/2/3` olasılıkları kayıp
      serisiyle artar; ayrı `_TXT["insist"]` havuzu; payloadda `insist` bayrağı.
- [x] Hile mekaniği (`_ai_move`: kayıpta artan, galibiyette azalan kazanç eğilimi).
- [x] Replik çeşitliliği (şablon havuzları — her olay için 3-5 replik). _(opsiyonel LLM lezzeti: sonraya)_
- [x] Sarı kazanç ışığı: `#win-flash` overlay + `--gesture-glow` altın override (app.js `triggerWinFlash`);
      ısrar anında `#ai-text` nabız animasyonu.

### Faz 3 — Kelime Türetme (LLM oyunu) — DETAYLI PLAN

> **Onaylanan kararlar:** (1) Kelime kaynağı = **LLM (gemma3:4b)** · (2) Kullanıcı hatasında
> **1 nazik tekrar hakkı** · (3) Zaman barı **her iki ekranda** (kontrol paneli otorite, sergiye yansır).

**Kural:** Kelime zinciri. Bir kelimenin **son harfiyle başlayan** yeni bir kelime söylenir; sırayla
(AI ↔ ziyaretçi) devam eder. Başlangıç **rastgele** (bazen AI bazen ziyaretçi). AI önce kuralları
**sabit metinle** (LLM'siz) kısaca anlatır. Her doğru cevapta AI insani duygu verir (sevinç/heyecan).
AI **birkaç turdan sonra yenilir** (aşağıdaki olasılık eğrisi). Kullanıcının her cevabı kontrol edilir.

#### 3.1 LLM rolü — `orchestrator/word_llm.py` (YENİ, çekirdek dosyalara dokunmaz)
Ayrı modül; `bridge.url` + `bridge.model` ile Ollama'ya kendi promptu ve JSON şemasıyla bağlanır
(`/api/chat`, `format` şeması + `think:false`, kısa `num_predict`, ~12 sn timeout).
- `uret_kelime(harf, kullanilmis)` → `harf` ile başlayan, kullanılmamış bir Türkçe kelime veya `None`.
- `gecerli_mi(kelime)` → `bool` (gerçek Türkçe kelime mi?). **Lenient:** model hata/kararsızsa kabul et
  (ziyaretçiyi modelin zayıflığından cezalandırma).
- Determinist ön-kontroller LLM'den ÖNCE: doğru harfle başlıyor mu? + daha önce kullanıldı mı?
  (string kontrolü — LLM'e ancak bunlar geçerse `gecerli_mi` için gidilir → hız + az çağrı).

#### 3.2 Durum makinesi — `game_engine.py` yeni faz `"kelime"`
Yeni alanlar: `word_used` (set), `word_turn` (`"ai"|"user"`), `word_required_letter`,
`word_last`, `word_ai_count` (AI başarılı cevap sayısı), `word_user_retried` (bool),
`word_score` (AI/SEN doğru sayısı — HUD'da gösterilir).
- **AI yenilme eğrisi** (determinist): `n = word_ai_count`. `n < GRACE(2)` → p=`BASE(0.95)`;
  değilse `p = max(FLOOR(0.05), 0.95 - DECAY(0.30)*(n-GRACE+1))`. → AI ~4-5. cevapta yenilir.
  Tur geldiğinde zar: başarı → LLM'den kelime üret (geçmezse 2. dene, yine olmazsa pes);
  başarısızlık → doğrudan duygusal pes ("aklıma gelmiyor… pes! Sen kazandın.") = `user_win`.
- **Kullanıcı turu:** ön-kontrol (harf/kullanılmış) + `gecerli_mi`. Geçersizse → `word_user_retried`
  yoksa **1 tekrar** (nazik replik + süre sıfırlanır), varsa **kayıp** (`ai_win`). Süre dolması (timeout)
  → tekrar hakkı YOK, doğrudan kayıp. Geçerliyse → AI heyecanlı tepki, harf güncellenir, sıra AI'ya.

#### 3.3 Uçlar — `web_server.py`
- `POST /api/game/input {text, timeout?}` (mevcut) — kelime fazında kullanıcı kelimesi / timeout işler.
- `POST /api/game/ai_turn` (**YENİ**) — sıra AI'dayken AI'nın kelimesini/pes'ini üretir (LLM burada çağrılır).
- Akış (tek kullanıcı kelimesi = 2 hızlı round-trip): input → "evet doğru!" (anında) + sıra AI →
  frontend `ai_turn` çağırır (AI düşünme barı dönerken) → AI kelimesi veya pes.

#### 3.4 Zaman barı (frontend otorite = `control.js`, sergiye broadcast)
- Mesaj tipleri: `timer_start {seconds, who}` · `timer_stop`. `who: "user"` ("SEN — 20 sn") /
  `"ai"` ("AICAN düşünüyor"). Kullanıcı turunda 20 sn geri sayım; bitince
  `POST /api/game/input {timeout:true}`. AI turunda bar görsel (fetch döner dönmez `timer_stop`).
- `web/AI_Body_v2.html`: `#word-timer` çubuğu (genişlik 100%→0 CSS geçişi, son ~5 sn kırmızı).
- `web/Kontrol_Paneli.html`: oyun alanında kompakt bar + kalan saniye.

#### 3.5 Duygu → jest (mevcut id'ler)
| Olay | Jest havuzu |
|---|---|
| AI doğru cevap | `gurur`, `mutluluk_yogun`, `nese` (üst üste → `hayranlik`) |
| Kullanıcı doğru | `hayranlik`, `nese`, `onayla_sicak`, `merak` (heyecan) |
| AI düşünürken | `dusunce`, `bekle` |
| AI zorlanıyor (yenilmeye yakın) | `saskinlik`, `kararsiz`, `bilmiyorum` |
| AI pes/yenildi | `hayal_kirikligi`/`uzgun_yavas` + centilmen `hayranlik`/`huzur` |
| Kullanıcı geçersiz (tekrar) | `soru_isareti`, `merak`, `anlamadim` |
| Kullanıcı kaybetti (timeout/2. hata) | `gurur`(yumuşak), `mutluluk_sakin`, `onayla_net` |
| Giriş/kural anlatımı | `selamlama`, `nese` |

#### 3.6 Görev listesi
- [x] `word_llm.py`: Ollama kelime üret + geçerlilik (ayrı prompt/şema, lenient, ~12 sn timeout).
- [x] `game_engine.py`: `"kelime"` fazı, yenilme eğrisi, 1 tekrar, timeout, duygu eşlemesi, payload.
- [x] `web_server.py`: `/api/game/ai_turn` + input `timeout` bayrağı + GameEngine lazy WordLLM (bridge'den).
- [x] `control.js`: kelime payload işleme, 20 sn geri sayım, timeout tetikleme, otomatik `ai_turn`, timer broadcast.
- [x] `app.js`: sergi zaman barı (geri sayım animasyonu), `timer_start/stop`, kelime tepkileri.
- [x] `AI_Body_v2.html` + `Kontrol_Paneli.html`: zaman barı öğeleri + CSS.
- [x] Backend birim testi (LLM mock'landı, Ollama gerekmez): 12/12 geçti — zincir kuralı, 1 tekrar→kayıp,
      timeout→kayıp, AI yenilme eğrisi (~4 turda pes), kullanılmış kelime reddi, iki başlangıç dalı.
      Ayrıca Flask `test_client` e2e: `/api/game/ai_turn` + input timeout + kelime payload uçtan uca ✓.
- [ ] **Manuel (kalan):** Ollama açıkken tarayıcıda canlı oynanış — gemma3:4b kelime kalitesi/hızı,
      zaman barı görünümü, duygu jestleri, sarı ışık. (Headless doğrulanamaz.)

**Bilinen sınır:** Son harf `ğ` gibi nadir başlangıçlarda LLM kelime bulamayabilir → AI pes eder
(tematik olarak sorun değil). gemma3:4b Türkçe kelime bilgisi zayıf olabilir; `gecerli_mi` lenient tutulur.

#### 3.7 Rötuşlar (kullanıcı geri bildirimi — 2026-06-14)
- **Hazırlık adımı:** Menüden "2" seçilince oyun HEMEN başlamaz; AI önce kuralları anlatır ve
  "Hazırsan başlayalım — 'başla' de ya da butona dokun" der (yeni `word_turn="hazir"` durumu,
  `kind:"ready"`, süre yok, `▶ Başla` butonu). Onay (`başla/hazırım/evet/…`) gelince `_begin_kelime()`
  gerçek oyunu başlatır (rastgele başlayan + süre).
- **AI sadece kelimeyle cevap verir:** Oyun sırasında AI'nın turunda `yanit` = yalnızca bulduğu kelime
  (Türkçe-doğru ilk harf büyütme `_cap`). Cümle/şablon yok. Kullanıcı doğru bilince AI kısa tezahürat
  ("Bravo!", "Helal!") + duygu jesti verir (sevinç/heyecan jestte).
- **Zaman barı üst banta alındı:** Sergi ekranında `#word-timer` `top:16px` (header bandı, ortada),
  daha kompakt — figürü/konuşmayı kapatmaz.

### Faz 4 — Cila & sergi sağlamlığı
- [ ] Boşta kalma / "dur" → sohbet moduna güvenli dönüş.
- [ ] Hata yönetimi (Ollama düşerse oyun donmasın), zaman aşımları.
- [ ] Oyunların oturum loglaması (`session_logger`).
- [ ] Oyun modunda sesli giriş ("taş" de) testi.
- [ ] e2e test (mevcut `e2e_snapshots` altyapısına oyun senaryosu).

### Faz 5 — Sergi teması güncellemesi (opsiyonel, paralel)
- [ ] Sergi ekranı başlık/altyazı: "Yapay zekânın duyguları var mı?"
- [ ] Açılış/attract ekranı temayı anlatsın.
- [ ] README tema ve oyun modu bölümü.

---

## 6. Senden karar bekleyenler

1. **MVP sıralaması:** Önce **Taş Kağıt Makas**'ı tam bitirip duyguları vitrine
   koyalım, kelime oyunu sonra — onaylıyor musun? (Önerim: evet.)
2. **Kelime Türetme kuralı** ne olsun? (örn. *kelime zinciri*: önceki kelimenin son
   harfiyle başlayan yeni kelime / *harften kelime* / *kategori* — Faz 3'te netleştiririz.)
3. **Menüye ek olarak butonlar** da olsun mu? (Kontrol panelinde "Oyun" hızlı butonu
   + sergi ekranında 1/2 dokunmatik seçenek — sergi dokunmatikse faydalı.)
4. **Hile dozajı:** AI ne sıklıkla hile yapsın? (örn. her ~5 turda bir, kaybederken artan.)
