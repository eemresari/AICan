// AI Body — Sergi Ekrani (tepki ekrani)
// gestures.json'u backend'den fetch eder; kontrol panelinden BroadcastChannel ile mesaj alir.

(function () {
  const HIZ = {
    cok_yavas: 0.45,
    yavas: 0.7,
    orta: 1.0,
    hizli: 1.4,
    cok_hizli: 1.9,
  };

  const $ = (q) => document.querySelector(q);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const els = {
    userText: $('#user-text'),
    aiText: $('#ai-text'),
    gestureBadge: $('#gesture-badge'),
    statusDot: $('#status-dot'),
    statusText: $('#status-text'),
    canvas: $('#led-canvas'),
    leftPlaceholder: $('#left-placeholder'),
    rightPlaceholder: $('#right-placeholder'),
    testList: $('#test-list'),
    testPanel: $('#test-panel'),
    controls: document.querySelector('.controls'),
    gameHud: $('#game-hud'),
    winFlash: $('#win-flash'),
    wordTimer: $('#word-timer'),
    gameOptions: $('#game-options'),
    sttWait: $('#stt-wait'),
    aiThinking: $('#ai-thinking'),
    stateBadge: $('#state-badge'),
    attractBox: $('#attract'),
    attractMsg: $('#attract-msg'),
    attractCount: $('#attract-count'),
    attractNum: $('#ac-num'),
  };

  let panel;
  let immersiveOn = false;            // tam ekran (immersive) göz modu açık mı
  let ledBaseSize = 876;              // normal LED boyutu (init'te canvas'tan alınır)
  const LED_IMMERSIVE_SIZE = 1080;    // immersive'de göz boyutu (stage yüksekliği = tüm ekran)
  let gestures = [];
  let gestureMap = new Map();
  let activeTypewriter = null;
  let bc = null;                 // BroadcastChannel — kontrol paneli ile iki yonlu

  // ——— Aşamalı durum rozeti (Dinliyorum/Düşünüyorum/Konuşuyor/Yazıyor) ———
  // Öncelik: dinleme > düşünme > konuşma (TTS) > yazma (daktilo); boşta gizli.
  let stListening = false;
  let stThinking = false;
  let stTyping = false;
  let stSpeaking = false;
  let stTranscribing = false;   // STT sürüyor — "bekle" balonu görünür, rozet gizli
  function updateStateBadge() {
    const b = els.stateBadge;
    if (!b) return;
    if (stTranscribing) { b.classList.add('hidden'); return; }  // bekle balonu konuşuyor
    let label = null;
    if (stListening) label = 'Dinliyorum…';
    else if (stThinking) label = 'Düşünüyorum…';
    else if (stSpeaking) label = 'Konuşuyor…';
    else if (stTyping) label = 'Yazıyor…';
    if (!label) { b.classList.add('hidden'); return; }
    const span = b.querySelector('.sb-label');
    if (span) span.textContent = label;
    b.classList.remove('hidden');
  }

  // STT "bekle" balonu: söz alındı, Whisper yazıya çeviriyor. Ziyaretçi bu
  // sırada tekrar konuşup sistemi karıştırmasın diye görünür uyarı.
  // Kısa bekletme replikleri — her açılışta rastgele biri seçilir.
  const STT_WAIT_TEXTS = ['Bir saniye…', 'Bekle…', 'Anlaşılıyor…', 'Seni duydum…'];
  function setSttWait(on) {
    stTranscribing = !!on;
    if (els.sttWait) {
      if (stTranscribing) {
        const label = els.sttWait.querySelector('.go-label');
        if (label) {
          label.textContent =
            STT_WAIT_TEXTS[Math.floor(Math.random() * STT_WAIT_TEXTS.length)];
        }
      }
      els.sttWait.classList.toggle('hidden', !stTranscribing);
    }
    updateStateBadge();
  }

  // Otonom "canlı göz" idle — etkileşim olmadan X sn geçince devreye girer.
  const EYE_IDLE_TIMEOUT_MS = 30000;
  let eyeIdleTimer = null;
  function noteInteraction() {
    if (panel) panel.setEyeIdle(false);
    if (eyeIdleTimer) clearTimeout(eyeIdleTimer);
    eyeIdleTimer = setTimeout(() => {
      if (panel) panel.setEyeIdle(true);
    }, EYE_IDLE_TIMEOUT_MS);
  }

  // ——— Yardimcilar ———————————————————————————————————————————
  function speedFor(jest) {
    const h = jest && jest.animasyon ? jest.animasyon.hiz : 'orta';
    return HIZ[h] != null ? HIZ[h] : 1.0;
  }
  function primaryFor(jest) {
    return (jest && jest.animasyon && jest.animasyon.ana_renk) || [120, 220, 255];
  }
  function secondaryFor(jest) {
    const a = jest && jest.animasyon;
    return (a && a.ikincil_renk) || (a && a.ana_renk) || [200, 120, 255];
  }
  function durationMsFor(jest) {
    const s = jest && jest.animasyon && jest.animasyon.sure_sn;
    return (typeof s === 'number' ? s : 4.0) * 1000;
  }
  function intensityFor(jest, override) {
    if (typeof override === 'number') return override;
    const v = jest && jest.animasyon && jest.animasyon.yogunluk_varsayilan;
    return typeof v === 'number' ? v : 0.85;
  }
  function humanName(id) {
    if (!id) return '';
    return id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // ——— Typewriter ——————————————————————————————————————————————
  // Daktilo hızı metin uzunluğuna adaptif: kısa metin ~22ms/harf, uzun ~12ms/harf
  // (uzun cevaplar sıkmadan akar; arada doğrusal geçiş).
  function adaptiveTypeSpeed(text) {
    const n = String(text || '').length;
    if (n <= 60) return 22;
    if (n >= 200) return 12;
    return Math.round(22 - ((n - 60) / 140) * 10);
  }
  // ——— Metni kutuya sigdir (kaydirma cubugu cikmasin) ——————————————————
  // Konusma balonunun sabit bir max-height'i var. Kaydirma yerine, TAM metni
  // gecici olcup scrollHeight kutuyu asiyorsa font boyutunu 34px'den ~18px'e
  // kademeli kucultur. Olcum daktilo BASLAMADAN once yapilir; boylece yazarken
  // boyut sabit kalir ve zipplama olmaz. Kisa mesajlar 34px'de kalir.
  const FIT_MAX_FS = 34, FIT_MIN_FS = 18;
  function fitSpeechText(el, fullText) {
    if (!el) return;
    const prev = el.textContent;
    el.style.fontSize = FIT_MAX_FS + 'px';
    el.textContent = fullText || '';
    let fs = FIT_MAX_FS;
    // scrollHeight (tam icerik) > clientHeight (max-height ile sinirli) => tasma
    while (fs > FIT_MIN_FS && el.scrollHeight > el.clientHeight) {
      fs -= 1;
      el.style.fontSize = fs + 'px';
    }
    el.textContent = prev;   // typeInto zaten '' ile bastan yazacak
  }

  function typeInto(el, text, speed) {
    if (activeTypewriter && activeTypewriter.id) {
      clearInterval(activeTypewriter.id);
      if (activeTypewriter.el === els.aiText) { stTyping = false; updateStateBadge(); }
      // KRİTİK: kesilen daktilonun promise'i de çözülsün — yoksa onu await
      // eden zincir (drvApplyPayload → drvBusy) SONSUZA DEK asılı kalır ve
      // sürücü sonraki tüm sesli girdileri yok sayar ("mikrofon öldü" belirtisi).
      if (activeTypewriter.resolve) { try { activeTypewriter.resolve(); } catch (_) {} }
    }
    const ms = (typeof speed === 'number') ? speed : adaptiveTypeSpeed(text);
    el.textContent = '';
    el.classList.add('typing');
    if (el === els.aiText) { stTyping = true; updateStateBadge(); }
    let i = 0;
    return new Promise((resolve) => {
      const id = setInterval(() => {
        if (i >= text.length) {
          clearInterval(id);
          el.classList.remove('typing');
          if (el === els.aiText) { stTyping = false; updateStateBadge(); }
          resolve();
          return;
        }
        el.textContent += text[i++];
      }, ms);
      activeTypewriter = { el, id, resolve };
    });
  }

  // ——— Seslendirme (TTS) ————————————————————————————————————————
  // AI cevabi geldiginde /api/speak'ten duyguya gore tonlanmis sesi cek ve cal.
  // Ses, yazi (typewriter) ile PARALEL baslar; ses backend'de CPU'da uretilir.
  let ttsEnabled = true;       // 'S' tusu ile acilip kapanir
  let ttsReady = false;        // backend motoru hazir mi (bilgi amacli)
  let ttsPrimed = false;       // tarayici autoplay kilidi acildi mi
  let currentAudio = null;

  async function checkTtsStatus() {
    try {
      const r = await fetch('/api/speak/status');
      const d = await r.json();
      // autoplay=false veya enabled=false ise sesi hic deneme
      ttsEnabled = (d.enabled !== false) && (d.autoplay !== false);
      ttsReady = !!d.ready;
    } catch (_) { ttsReady = false; }
  }

  // Tarayici autoplay politikasi: ilk kullanici etkilesiminde sesi "ac".
  // (Sergi kiosk'unda gorevli sayfayla bir kez etkilesince ses acilir.)
  function primeAudio() {
    if (ttsPrimed) return;
    ttsPrimed = true;
    try {
      const a = new Audio(
        'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=');
      a.volume = 0;
      a.play().catch(() => {});
    } catch (_) {}
  }

  // ——— Cumle-bazli akis: metin cumle parcalarina bolunur, parcalar SIRAYLA
  // POST edilir ve gelen sesler kuyrukta kesintisiz arka arkaya calinir.
  // Ilk parca gelir gelmez ses baslar; tek cumlelik kisa metin = tek istek.
  let speakToken = 0;          // artan sayac: her yeni konusma eskisini iptal eder
  let audioQueue = [];         // sirada bekleyen blob URL'leri
  let queuePlaying = false;
  let speakProducingToken = -1; // speak() hangi jeton icin hâlâ ses parçaları çekiyor
  let speechWaiters = [];

  // Kuyruk, iki fetch arasında kısa süre boş kalabilir. Üretici bitmeden bu
  // boşluğu "konuşma bitti" saymak sayacı ve mikrofon kapısını erken açar.
  function speechIdle() {
    return speakProducingToken !== speakToken && !queuePlaying && audioQueue.length === 0;
  }
  function speechSettle() {
    if (!speechIdle()) return;
    const ws = speechWaiters; speechWaiters = [];
    for (const w of ws) { try { w(); } catch (_) {} }
  }
  function whenSpeechDone(timeoutMs) {
    if (speechIdle()) return Promise.resolve();
    const ms = (typeof timeoutMs === 'number' && timeoutMs > 0) ? timeoutMs : 20000;
    return new Promise((resolve) => {
      let settled = false;
      let tid = null;
      const finish = () => {
        if (settled) return;
        settled = true;
        if (tid) clearTimeout(tid);
        const i = speechWaiters.indexOf(finish);
        if (i >= 0) speechWaiters.splice(i, 1);
        resolve();
      };
      speechWaiters.push(finish);
      tid = setTimeout(() => {
        if (settled) return;
        // Asılı fetch/oynatma sürücüyü sonsuza dek kilitlemesin; geç kalan ses
        // cevap penceresi açıldıktan sonra başlamasın diye jetonu da iptal et.
        console.warn('TTS bitişi ' + ms + ' ms içinde gelmedi — konuşma iptal edildi');
        try { stopSpeech(); } finally { finish(); }
      }, ms);
    });
  }

  // Cumle sinirlari: .!?… + bosluk. orchestrator/web_server.py _split_sentences_tr
  // ile BIREBIR ayni mantik (on-isitma onbellek anahtarlari isabet etsin diye).
  const SENT_MIN_LEN = 10;
  function splitSentences(text) {
    const parts = String(text || '').trim().split(/(?<=[.!?…])\s+/)
      .map((s) => s.trim()).filter(Boolean);
    const out = [];
    let buf = '';
    for (const p of parts) {
      buf = buf ? buf + ' ' + p : p;
      if (buf.length >= SENT_MIN_LEN) { out.push(buf); buf = ''; }
    }
    if (buf) {
      if (out.length) out[out.length - 1] += ' ' + buf;
      else out.push(buf);
    }
    return out;
  }

  // Aktif konusmayi tamamen durdur: calan ses + bekleyen kuyruk + suren fetch'ler.
  function stopSpeech() {
    speakToken++;              // eski uretici dongu/kuyruk zincirleri gecersiz olsun
    queuePlaying = false;
    if (currentAudio) {
      try { currentAudio.pause(); URL.revokeObjectURL(currentAudio.src); } catch (_) {}
      currentAudio = null;
    }
    for (const u of audioQueue) { try { URL.revokeObjectURL(u); } catch (_) {} }
    audioQueue = [];
    if (stSpeaking) { stSpeaking = false; updateStateBadge(); }
    speakProducingToken = -1;
    speechSettle();
  }

  async function fetchSpeechUrl(text, jestId, yogunluk) {
    const r = await fetch('/api/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, jest_id: jestId || '', yogunluk: yogunluk }),
    });
    if (!r.ok) { if (r.status !== 503) console.warn('TTS HTTP', r.status); return null; }
    const blob = await r.blob();
    return URL.createObjectURL(blob);
  }

  function playQueue(token) {
    if (token !== speakToken || queuePlaying) return;
    const url = audioQueue.shift();
    if (!url) return;
    queuePlaying = true;
    stSpeaking = true;                     // "Konuşuyor…" rozeti
    updateStateBadge();
    let a;
    try {
      a = new Audio(url);
    } catch (e) {
      console.warn('Ses nesnesi oluşturulamadı', e);
      try { URL.revokeObjectURL(url); } catch (_) {}
      queuePlaying = false;
      playQueue(token);
      if (!queuePlaying && stSpeaking) { stSpeaking = false; updateStateBadge(); }
      speechSettle();
      return;
    }
    currentAudio = a;
    let bitti = false;
    const done = () => {
      if (bitti) return;
      bitti = true;
      try { URL.revokeObjectURL(url); } catch (_) {}
      if (token !== speakToken) return;   // stopSpeech geldi: kuyruga dokunma
      queuePlaying = false;
      if (currentAudio === a) currentAudio = null;
      playQueue(token);                    // siradaki parca — kesintisiz devam
      if (!queuePlaying && stSpeaking) { stSpeaking = false; updateStateBadge(); }
      speechSettle();
    };
    a.onended = done;
    a.onerror = done;
    try {
      const started = a.play();
      if (started && typeof started.catch === 'function') {
        started.catch((e) => { console.warn('Ses oynatilamadi (autoplay kilidi?)', e); done(); });
      }
    } catch (e) {
      console.warn('Ses oynatilamadi (autoplay kilidi?)', e);
      done();
    }
  }

  // Imza SABIT: speak(text, jestId, yogunluk) — ayni jest/yogunluk tum parcalara.
  async function speak(text, jestId, yogunluk) {
    if (!ttsEnabled || !text) return;
    stopSpeech();
    const token = speakToken;
    // İlk await'ten önce işaretle: speak() çağrısının hemen ardından kurulan
    // whenSpeechDone bekleyicisi fetch aralığını yanlışlıkla boş sanmasın.
    speakProducingToken = token;
    // Yankı filtresi referansı: mikrofon TTS çalarken kayıt yaparsa sunucu,
    // transkripti bu metinlerle kıyaslayıp salt yankıyı atar (viTranscribeAndSend).
    viTtsRecent.push(String(text));
    if (viTtsRecent.length > 2) viTtsRecent.shift();
    const yog = (typeof yogunluk === 'number' ? yogunluk : 0.7);
    try {
      const parcalar = splitSentences(text);
      for (const parca of parcalar) {
        if (token !== speakToken || !ttsEnabled) return;
        const url = await fetchSpeechUrl(parca, jestId, yog);
        if (token !== speakToken) {          // bu arada iptal geldi
          if (url) { try { URL.revokeObjectURL(url); } catch (_) {} }
          return;
        }
        if (!url) return;                    // backend hatasi: kalan parcalari zorlama
        audioQueue.push(url);
        playQueue(token);
      }
    } catch (e) {
      console.warn('TTS hata:', e);
    } finally {
      // Eski, iptal edilmiş fetch yeni speak() üreticisinin bayrağını söndürmesin.
      if (speakProducingToken === token) speakProducingToken = -1;
      speechSettle();
    }
  }

  // ——— Jesti tetikle ————————————————————————————————————————————
  // Varsayilan duration: Infinity — jest, baska bir jest gelene kadar oynar.
  function triggerGesture(gestureId, opts = {}) {
    const g = gestureMap.get(gestureId);
    if (!g) {
      console.warn('Bilinmeyen jest_id:', gestureId);
      return;
    }
    const primary = opts.primary || primaryFor(g);
    const secondary = opts.secondary || secondaryFor(g);
    const speed = (opts.speed != null) ? opts.speed : speedFor(g);
    const intensity = intensityFor(g, opts.intensity);
    const duration = (opts.duration != null) ? opts.duration : Number.POSITIVE_INFINITY;
    const isEmoji = (g.gorsel_tipi === 'emoji');

    panel.setGesture({
      pattern: g.animasyon.desen,
      primary, secondary,
      speed, intensity,
      duration,
      gestureId: g.id,
      isEmoji,
    });
    panel.setIdle({
      pattern: 'breathe',
      primary,
      secondary,
      speed: 0.6,
      intensity: 0.7,
      gestureId: null,
      isEmoji: false,
    });

    els.gestureBadge.classList.remove('hidden');
    const rgb = 'rgb(' + primary.join(',') + ')';
    els.gestureBadge.innerHTML =
      '<span class="dot" style="background:' + rgb + ';' +
      ' box-shadow: 0 0 12px ' + rgb + '"></span>' + humanName(g.id);
    // Jest rozeti değişiminde ~300ms cross-fade (yalnız opacity animasyonu)
    els.gestureBadge.classList.remove('swap');
    void els.gestureBadge.offsetWidth;      // reflow — animasyonu baştan başlat
    els.gestureBadge.classList.add('swap');

    // Arka plan ve dış halo aktif jestin baskın rengine kaysın.
    // CSS transition'lar yumuşak (1.4s) geçiş yapar.
    const root = document.documentElement.style;
    root.setProperty('--gesture-glow',   primary.join(','));
    root.setProperty('--gesture-glow-2', secondary.join(','));

    // Gözler de jest rengiyle uyumlu olsun (idle moduna döndüğünde bu renkten gelir)
    if (panel && panel.eyes) panel.eyes.setColors(primary, secondary);

    // Jest = etkileşim; eye idle'ı kapat ve sayacı sıfırla.
    noteInteraction();
  }

  // ——— "Düşünüyorum…" göstergesi ————————————————————————————
  // Kontrol paneli 'thinking' yayınlar; ai_reply gelince temizlenir.
  // 45 sn güvenlik zaman aşımı, backend cevap veremezse takılı kalmayı önler.
  let thinkingSafetyId = null;
  function thinkingGestureId() {
    if (gestureMap.has('bekle')) return 'bekle';
    for (const g of gestures) {
      if (g.animasyon && g.animasyon.desen === 'three_dots') return g.id;
    }
    return null;
  }
  function setThinking(on, label, jest) {
    stThinking = !!on;
    if (thinkingSafetyId) { clearTimeout(thinkingSafetyId); thinkingSafetyId = null; }
    if (els.aiThinking) {
      if (on) {
        els.aiThinking.textContent = label || 'Düşünüyorum…';
        els.aiThinking.classList.remove('hidden');
        if (els.rightPlaceholder) els.rightPlaceholder.style.display = 'none';
      } else {
        els.aiThinking.classList.add('hidden');
      }
    }
    if (on) {
      thinkingSafetyId = setTimeout(() => setThinking(false), 45000);
      // jest=false: hızlı yerel oyun yanıtlarında jest titremesin (yalnız gösterge)
      if (jest !== false) {
        const gid = thinkingGestureId();
        if (gid) triggerGesture(gid, { intensity: 0.6 });
      }
      noteInteraction();
    }
    updateStateBadge();
  }

  // ——— Attract / boşta modu (zamanlayıcı otoritesi control.js'te) ————
  // attract_on: gözler LED panelde sürer; davet metinleri yumuşak fade ile döner.
  // attract_countdown: "Hâlâ orada mısın?" + görünür geri sayım.
  // Herhangi bir gerçek etkileşim mesajı attract'ı anında kapatır.
  const ATTRACT_MSGS = ['Bana bir soru sor!', 'Benimle oyun oyna!', 'Sana uzayı anlatayım mı?'];
  // Test modunda sohbet kapalı — davet metinleri yalnızca oyuna çağırır.
  const ATTRACT_MSGS_TEST = ['Hadi oyun oynayalım!', 'Atasözü tamamlayalım mı?', 'Eş ve zıt anlamlıları biliyor musun ?'];
  function attractMsgs() { return testModeOn ? ATTRACT_MSGS_TEST : ATTRACT_MSGS; }

  // ——— Test modu göstergesi ('g' tuşu; durum backend'de) ————————————
  let testModeOn = false;
  let testBadgeEl = null;
  function setTestBadge(on) {
    const changed = testModeOn !== !!on;
    testModeOn = !!on;
    // Backend mod değişiminde oyun durumunu sıfırlar — sürücü de senkron kalsın.
    if (changed) {
      drvGamePhase = null;
      drvTurnId = null;
      drvInputGateAt = 0;
      drvApplySeq++;
      drvOptions = [];
    }
    if (!testBadgeEl) {
      testBadgeEl = document.createElement('div');
      testBadgeEl.style.cssText =
        'position:fixed;bottom:10px;left:12px;z-index:60;display:none;pointer-events:none;' +
        'font:600 11px/1.4 monospace;letter-spacing:2px;color:rgba(255,209,102,0.55);';
      testBadgeEl.textContent = 'TEST MODU';
      document.body.appendChild(testBadgeEl);
    }
    testBadgeEl.style.display = testModeOn ? 'block' : 'none';
  }
  let testToggleBusy = false;
  async function toggleTestModeFromDisplay() {
    if (testToggleBusy) return;    // tuş basılı tutulursa istek seli olmasın
    testToggleBusy = true;
    try {
      // Kör toggle yerine hedef durum: tekrar/yarış durumlarında yakınsar.
      const r = await fetch('/api/test_mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ on: !testModeOn }),
      });
      const d = await r.json();
      setTestBadge(!!d.on);
      if (bc) bc.postMessage({ type: 'test_mode', on: !!d.on });  // panel de öğrensin
    } catch (e) {
      console.warn('test modu değiştirilemedi', e);
    } finally {
      testToggleBusy = false;
    }
  }
  const ATTRACT_CYCLE_MS = 6000;
  const ATTRACT_FADE_MS = 800;
  const ATTRACT_CANCEL = new Set([
    'user_text', 'thinking', 'ai_reply', 'manual_gesture', 'listening',
    'game_score', 'game_options', 'game_option_select', 'timer_start', 'game_exit',
  ]);
  let attractActive = false;
  let attractIdx = 0;
  let attractCycleId = null;
  let attractFadeId = null;

  function attractShow() {
    if (!els.attractBox || attractActive) return;
    attractActive = true;
    // Bekleme moduna girişte LED HEMEN "canlı göz" animasyonuna geçsin —
    // oyun-sonu geçişi 30 sn'lik eye-idle sayacını beklemesin (bitiş mesajı →
    // skor → doğrudan gözlü bekleme ekranı). Sonraki etkileşim noteInteraction
    // ile gözü kapatır.
    if (eyeIdleTimer) { clearTimeout(eyeIdleTimer); eyeIdleTimer = null; }
    if (panel) panel.setEyeIdle(true);
    attractIdx = 0;
    if (els.attractCount) els.attractCount.classList.add('hidden');
    if (els.attractMsg) {
      els.attractMsg.classList.remove('out');
      els.attractMsg.textContent = attractMsgs()[0];
    }
    els.attractBox.classList.remove('hidden');
    attractCycleId = setInterval(() => {
      if (!els.attractMsg) return;
      els.attractMsg.classList.add('out');               // yumuşak fade-out
      attractFadeId = setTimeout(() => {
        const msgs = attractMsgs();
        attractIdx = (attractIdx + 1) % msgs.length;
        els.attractMsg.textContent = msgs[attractIdx];
        els.attractMsg.classList.remove('out');           // fade-in
      }, ATTRACT_FADE_MS);
    }, ATTRACT_CYCLE_MS);
  }
  function attractHide() {
    if (attractCycleId) { clearInterval(attractCycleId); attractCycleId = null; }
    if (attractFadeId) { clearTimeout(attractFadeId); attractFadeId = null; }
    attractActive = false;
    if (els.attractBox) els.attractBox.classList.add('hidden');
    if (els.attractCount) els.attractCount.classList.add('hidden');
  }
  function attractCountdownTick(seconds) {
    if (!attractActive) attractShow();
    if (els.attractCount) els.attractCount.classList.remove('hidden');
    if (els.attractNum) els.attractNum.textContent = String(seconds);
  }

  // ——— Yildiz tozu ——————————————————————————————————————————
  // Performans: 2 karede 1 çizim (parıltı dt-tabanlı — algılanan hız değişmez),
  // sekme gizliyken tamamen durur.
  function initStars() {
    const c = document.getElementById('stars');
    if (!c) return;
    const ctx = c.getContext('2d');
    function resize() {
      c.width = window.innerWidth;
      c.height = window.innerHeight;
    }
    resize(); window.addEventListener('resize', resize);
    const stars = [];
    for (let i = 0; i < 220; i++) {
      stars.push({
        x: Math.random() * 1920,
        y: Math.random() * 1080,
        r: Math.random() * 1.2 + 0.2,
        a: Math.random(),
        speed: 0.2 + Math.random() * 0.6,
      });
    }
    let frameNo = 0;
    let lastDraw = performance.now();
    function draw(now) {
      requestAnimationFrame(draw);
      if (document.hidden) { lastDraw = now; return; }   // gizliyken dur
      frameNo++;
      if (frameNo % 2 === 1) return;                     // 2 karede 1 çiz
      const dt = Math.min(100, now - lastDraw) / 16.7;   // ~kare cinsinden süre
      lastDraw = now;
      ctx.clearRect(0, 0, c.width, c.height);
      for (const s of stars) {
        s.a += 0.005 * s.speed * dt;
        const alpha = 0.3 + 0.4 * (0.5 + 0.5 * Math.sin(s.a));
        ctx.fillStyle = 'rgba(200, 220, 255, ' + alpha + ')';
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    requestAnimationFrame(draw);
  }

  // ——— Test paneli (T tusu) ——————————————————————————————————
  function buildTestPanel() {
    if (!els.testList) return;
    els.testList.innerHTML = '';
    gestures.forEach((g, idx) => {
      const btn = document.createElement('button');
      btn.className = 'test-item';
      const rgb = 'rgb(' + primaryFor(g).join(',') + ')';
      btn.innerHTML =
        '<span class="num">' + String(idx + 1).padStart(2, '0') + '</span>' +
        '<span class="swatch" style="background:' + rgb + '"></span>' +
        '<span class="name">' + humanName(g.id) + '</span>' +
        '<span class="pat">' + g.animasyon.desen + '</span>';
      btn.addEventListener('click', () => triggerGesture(g.id));
      els.testList.appendChild(btn);
    });
  }

  // ——— Mod (emoji/desen) ————————————————————————————————
  function applyMode(mode) {
    const m = (mode === 'emoji') ? 'emoji' : 'desen';
    if (panel) panel.setMode(m);
    try { localStorage.setItem('aibody.mode', m); } catch (_) {}
  }
  function loadStoredMode() {
    try { return localStorage.getItem('aibody.mode') || 'desen'; } catch (_) { return 'desen'; }
  }

  // ——— Sarı kazanç ışığı (AI tur kazandığında ekran bir kez parlar) ——
  // Aktif jest rengini sıcak altın sarısına çevirir + kısa bir parlama efekti.
  // Bir sonraki jest geldiğinde renk doğal olarak kendi jestine döner.
  const WIN_GLOW = [255, 205, 70];     // sıcak altın sarısı
  const WIN_GLOW_2 = [255, 145, 45];   // turuncu vurgu
  let winFlashTimer = null;
  function triggerWinFlash() {
    const root = document.documentElement.style;
    root.setProperty('--gesture-glow', WIN_GLOW.join(','));
    root.setProperty('--gesture-glow-2', WIN_GLOW_2.join(','));
    const flash = els.winFlash;
    if (!flash) return;
    flash.classList.remove('on');
    void flash.offsetWidth;            // reflow — animasyonu baştan başlat
    flash.classList.add('on');
    if (winFlashTimer) clearTimeout(winFlashTimer);
    winFlashTimer = setTimeout(() => flash.classList.remove('on'), 1600);
  }

  // ——— Kelime oyunu zaman barı (sergi ekranı) ————————————————
  // control.js otorite; burada yalnızca görsel geri sayım gösterilir.
  let dispTimer = { id: null };
  function startDisplayTimer(seconds, who) {
    const bar = els.wordTimer;
    if (!bar) return;
    stopDisplayTimer();
    const fill = bar.querySelector('.wt-fill');
    const label = bar.querySelector('.wt-label');
    const num = bar.querySelector('.wt-num');
    bar.classList.remove('hidden');
    bar.classList.toggle('ai', who === 'ai');
    if (label) label.textContent = (who === 'ai') ? 'AICAN düşünüyor…' : 'SENİN SIRAN';
    const endsAt = Date.now() + seconds * 1000;
    const tick = () => {
      const remain = Math.max(0, (endsAt - Date.now()) / 1000);
      if (num) num.textContent = Math.ceil(remain) + ' sn';
      if (fill) {
        fill.style.width = (remain / seconds) * 100 + '%';
        fill.classList.toggle('low', remain <= 5);
      }
      if (remain <= 0) stopDisplayTimer();
    };
    tick();
    dispTimer.id = setInterval(tick, 100);
    noteInteraction();
  }
  function stopDisplayTimer() {
    if (dispTimer.id) { clearInterval(dispTimer.id); dispTimer.id = null; }
    if (els.wordTimer) els.wordTimer.classList.add('hidden');
  }

  // ——— Oyun skor HUD ————————————————————————————————————
  function updateGameHud(active, score) {
    if (!els.gameHud) return;
    if (active && score) {
      els.gameHud.innerHTML =
        '<span class="ghud-lbl">BEN</span>' +
        '<span class="ghud-num">' + score.ai + '</span>' +
        '<span class="ghud-sep">·</span>' +
        '<span class="ghud-num">' + score.user + '</span>' +
        '<span class="ghud-lbl">SEN</span>';
      els.gameHud.classList.remove('hidden');
    } else {
      els.gameHud.classList.add('hidden');
    }
  }

  function optionKeyLabel(button, index) {
    const key = String((button && button.key) || '').trim();
    const readable = {
      tas: 'taş',
      kagit: 'kağıt',
      makas: 'makas',
      cikis: 'çıkış',
      basla: 'başla',
      edebiyat: 'edebiyat',
      tarih: 'tarih',
      bilim: 'bilim',
      genel: 'genel',
      eszit: 'eş/zıt',
      atasozu: 'atasözü',
      dogruyanlis: 'doğru/yanlış',
      kelime: 'kelime',
      bilgi: 'bilgi',
    };
    if (readable[key]) return readable[key];
    if (/^[0-9]+$/.test(key)) return key;
    return key || String(index + 1);
  }

  function optionTextLabel(button, index) {
    const raw = (button && button.label) ? String(button.label) : optionKeyLabel(button, index);
    const clean = raw.replace(/^[^\p{L}\p{N}]+/u, '').replace(/\s+/g, ' ').trim();
    return clean || raw;
  }

  function normChoice(text) {
    return String(text || '')
      .replace(/[İI]/g, 'i').replace(/Ç/g, 'c').replace(/Ğ/g, 'g')
      .replace(/Ö/g, 'o').replace(/Ş/g, 's').replace(/Ü/g, 'u')
      .toLowerCase()
      .replace(/[çğıöşüâîû]/g, (c) => (
        { 'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'â': 'a', 'î': 'i', 'û': 'u' }[c] || c
      ))
      .replace(/[^a-z0-9 ]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function renderGameOptions(payload) {
    const box = els.gameOptions;
    if (!box) return;
    const buttons = Array.isArray(payload && payload.buttons) ? payload.buttons : [];
    const hint = (payload && payload.hint) ? String(payload.hint) : '';
    const total = buttons.length + (hint ? 1 : 0);
    box.innerHTML = '';
    if (!payload || !payload.visible || total === 0) {
      box.classList.add('hidden');
      return;
    }
    buttons.forEach((button, index) => {
      const row = document.createElement('div');
      row.className = 'game-option';
      row.style.animationDelay = Math.min(index * 45, 180) + 'ms';
      row.dataset.key = String((button && button.key) || '');
      row.dataset.choice = normChoice(
        row.dataset.key + ' ' + optionKeyLabel(button, index) + ' ' + optionTextLabel(button, index)
      );

      const key = document.createElement('span');
      key.className = 'go-key';
      key.textContent = optionKeyLabel(button, index);

      const label = document.createElement('span');
      label.className = 'go-label';
      label.textContent = optionTextLabel(button, index);

      row.appendChild(key);
      row.appendChild(label);
      box.appendChild(row);
    });
    if (hint) {
      // Sesli yonlendirme balonu: secenek degil, "ne soyleyecegini" gosterir.
      const row = document.createElement('div');
      row.className = 'game-option hint';
      row.style.animationDelay = Math.min(buttons.length * 45, 180) + 'ms';
      const key = document.createElement('span');
      key.className = 'go-key';
      key.textContent = '🎤';
      const label = document.createElement('span');
      label.className = 'go-label';
      label.textContent = hint;
      row.appendChild(key);
      row.appendChild(label);
      box.appendChild(row);
    }
    box.classList.remove('hidden');
    noteInteraction();
  }

  function selectGameOption(payload) {
    const box = els.gameOptions;
    if (!box || box.classList.contains('hidden')) return;
    const key = String((payload && payload.key) || '');
    const text = normChoice((payload && (payload.text || payload.label)) || key);
    let selected = null;
    for (const row of box.querySelectorAll('.game-option')) {
      if (row.classList.contains('hint')) continue;   // yonlendirme balonu secilemez
      row.classList.remove('selected', 'pulse');
      const rowKey = row.dataset.key || '';
      const rowChoice = row.dataset.choice || '';
      if (!selected && (
        (key && rowKey === key) ||
        (text && (rowChoice === text || rowChoice.includes(text) || text.includes(rowChoice)))
      )) {
        selected = row;
      }
    }
    if (!selected) return;
    selected.classList.add('selected');
    void selected.offsetWidth;
    selected.classList.add('pulse');
    setTimeout(() => selected && selected.classList.remove('pulse'), 1200);
  }

  function hideGameOptions() {
    if (!els.gameOptions) return;
    els.gameOptions.innerHTML = '';
    els.gameOptions.className = 'game-options hidden';
  }

  function resetSpeechPanels() {
    if (activeTypewriter && activeTypewriter.id) {
      clearInterval(activeTypewriter.id);
      if (activeTypewriter.el) activeTypewriter.el.classList.remove('typing');
      // KRİTİK (typeInto'daki ile AYNI gerekçe): kesilen daktilonun promise'i de
      // çözülsün. Yoksa onu await eden zincir (drvApplyPayload → whenSpeechDone →
      // cevap penceresi + geri sayım) SONSUZA DEK asılı kalır: kapı Infinity'de
      // kilitlenir (mikrofon sağır), yeni sayaç hiç başlamaz ve ekran yalnız
      // 5 dk'lık boşta sigortasıyla kurtulur.
      if (activeTypewriter.resolve) { try { activeTypewriter.resolve(); } catch (_) {} }
      activeTypewriter = null;
    }
    stTyping = false;
    if (els.aiThinking) els.aiThinking.classList.add('hidden');
    updateStateBadge();
    if (els.userText) els.userText.textContent = '';
    if (els.aiText) {
      els.aiText.textContent = '';
      els.aiText.classList.remove('insist', 'typing');
    }
    if (els.leftPlaceholder) els.leftPlaceholder.style.display = '';
    if (els.rightPlaceholder) els.rightPlaceholder.style.display = '';
    if (els.gestureBadge) els.gestureBadge.classList.add('hidden');
  }

  // ——— Sürekli sesli giriş (ekran mikrofonu + VAD) ————————————————————
  // Sergi ekranında mikrofon sürekli açık kalır: AI KONUŞMUYOR/DÜŞÜNMÜYOR/
  // YAZMIYORken dinler; kişi cümlesini bitirip sustuğunda (sessizlik eşiği)
  // segmenti otomatik Whisper'a (/api/transcribe) yollar. Çıkan metni panel
  // AÇIKSA BroadcastChannel'la panele iletir ('voice_input'); panel YOKSA
  // (sergi kurulumu: yalnız bu ekran) ekran-içi sürücü (drvHandleText) işler.
  // Bas-tut sistemi kontrol panelinde fallback kalır.
  //
  // Yankı koruması: AI DÜŞÜNÜRKEN (stThinking, çalan ses yok) kayıt durur.
  // AI KONUŞURKEN (stSpeaking, TTS) davranış holdDuringSpeech ile belirlenir:
  //  • holdDuringSpeech=true (VARSAYILAN, kullanıcı isteği): AI KESİLMEZ.
  //    Mikrofon açık kalır; ekranın kendi TTS yankısının ÜSTÜNDE (bargeInMult ile
  //    yükseltilen eşik) GERÇEK konuşma duyulursa kayıt sürer ama GÖNDERİLMEZ.
  //    AI cümlesini bitirince (stSpeaking=false) biriken söz normal endpointing
  //    ile transkribe edilip cevap olarak işlenir. Kişi araya girse de AI susmaz.
  //  • holdDuringSpeech=false: eski BARGE-IN — eşik bargeInMult ile yükseltilir,
  //    kullanıcı yeterince yüksek+sürekli konuşursa TTS kesilip hemen kaydeder.
  // bargeIn=false + holdDuringSpeech=false ile eski "konuşurken sağır" davranış.
  const VI = {
    enabled: true,          // özellik açık mı (config.voice_input.enabled)
    autostart: true,        // ilk dokunuşta kendiliğinden başlasın mı
    silenceMs: 1000,        // sustuktan sonra "cümle bitti" sayma süresi
    minSpeechMs: 350,       // bundan kısa ses = gürültü, gönderme
    silenceMsGame: 600,     // oyun modunda tek-kelime cevap → daha erken "bitti"
    minSpeechMsGame: 250,   // oyun modunda kısa komut ("taş") de geçerli
    maxUtteranceMs: 12000,  // güvenlik tavanı — tek konuşma bu kadar sürer
    onsetMult: 2.2,         // konuşma eşiği = gürültü_tabanı * mult
    absMinRms: 0.012,       // mutlak alt eşik (sessiz odada bile bu kadar gerek)
    cooldownMs: 400,        // AI sustuktan sonra tekrar dinlemeye geçme gecikmesi
    echoCancellation: true, // hoparlör yankısını bastır (TTS aynı ekrandan çalıyor)
    noiseSuppression: true, // Chrome DSP — uzak konuşmacıda Whisper'ı bozabilir, A/B için config'ten
    autoGain: true,         // AGC — sessizlikte kazancı yükseltip VAD eşiğini şaşırtabilir
    bargeIn: true,          // (holdDuringSpeech=false iken) kullanıcı araya girince TTS kesilsin
    bargeInMult: 2.2,       // TTS sırasında konuşma eşiği bu katsayıyla yükseltilir (echo artığı sayılmasın)
    bargeInMinMs: 280,      // barge-in için gereken sürekli yüksek-ses süresi
    holdDuringSpeech: true, // AI konuşurken kesme; söyleneni biriktir, AI bitince cevaba çevir
    // ——— Ortam gürültüsü kalibrasyonu (aşağıdaki blokta anlatılıyor) ———
    calibrationEnabled: true, // false → ESKİ davranış (EMA tabanı + elle ayarlı eşikler) birebir
    calibMs: 4000,            // açılışta kaç ms sessiz ortam dinlenip ölçülecek
    calibHeadroom: 1.35,      // kalibre alt eşik = ölçülen p90 * bu (tepe gürültü konuşma sayılmasın)
    calibMaxRms: 0.08,        // ölçülen medyan bunu aşarsa kalibrasyon REDDEDİLİR (konuşuldu/mikrofon bozuk)
    floorWindowMs: 15000,     // canlı gürültü tabanı penceresi
    floorPct: 0.10,           // pencerenin en sessiz %10'u = ortam gürültüsü
  };
  // Gürültü tabanının tırmanabileceği tavan: mikrofon arızası / sürekli uğultu
  // eşiği sonsuza götürüp sistemi sağır etmesin.
  const VI_FLOOR_MAX_RMS = 0.15;
  const VI_FLOOR_MIN_RMS = 0.0004;
  // Kalibrasyon sonucu bu kadar süre geçerli (tarayıcı yenilense de korunur).
  // Sergi günü içinde tekrar ölçüm istemez; ortam değişince operatör 'k' ile yeniler.
  const VI_CALIB_TTL_MS = 12 * 3600 * 1000;
  const VI_CALIB_STORE_KEY = 'aican_vi_calib_v1';
  // AI konuşması biterken biriken kaydın başındaki yankı/sessizlik sunucuda
  // kırpılır (trim_ms). Bu sabit, yankı-yalnız kaydın en fazla ne kadar
  // birikeceğini sınırlar: kayıt bu yaştan eskiyse tazelenir (blob küçük kalsın).
  const VI_HOLD_REFRESH_MS = 1200;
  // Konuşma başlangıcından bu kadar önce kırp (ilk sessiz ünsüzler kaybolmasın).
  const VI_TRIM_PAD_MS = 350;
  let viActive = false;          // dinleme fiilen açık mı (mic akışı var)
  let viStream = null;
  let viCtx = null;
  let viAnalyser = null;
  let viData = null;             // zaman-alanı örnek tamponu (Float32Array)
  let viRec = null;              // o anki konuşma için MediaRecorder
  let viChunks = [];
  let viMime = '';
  let viMonitorId = null;        // RMS izleme interval
  let viRecStartAt = 0;
  let viLastLoudAt = 0;
  let viHadSpeech = false;
  let viSpeechStartAt = 0;       // viHadSpeech'in ilk true olduğu an (anlık selam için)
  let viNoiseFloor = 0.01;       // ortam gürültüsü (EMA ile güncellenir)
  let viPendingAction = null;    // 'send' | 'discard' — onstop ne yapsın
  let viStopping = false;        // stop() çağrıldı, onstop bekleniyor (yarış engeli)
  let viBusyTranscribe = false;  // aynı anda tek transkripsiyon
  let viHoldUntil = 0;           // bu ana kadar yeni kayıt başlatma (cooldown)
  let viWasGated = false;
  let viBargeStart = 0;          // AI konuşurken sürekli yüksek-sesin başladığı an (barge-in)
  let viShowListening = false;   // rozet durumu takibi (spam engelle)
  let viMicWarnEl = null;        // mikrofon açılamadı uyarısı (görünür)
  let viOverlapTts = false;      // bu kayıt TTS çalarken mi sürdü (yankı riski → echo_text gönder)
  let viWasSpeakingTick = false; // önceki tick'te stSpeaking var mıydı (bitiş geçişini yakala)
  let viPendingBlob = null;      // STT meşgulken biten SON söz — düşürme, sıraya al (tek slot)
  let viTtsRecent = [];          // son çalınan 1-2 TTS metni (yankı filtresi referansı)
  let viHintEl = null;           // "duyamadım" geçici bildirimi
  let viHintLastAt = 0;

  // ——— ORTAM GÜRÜLTÜSÜ: KALİBRASYON + CANLI TABAN ————————————————————
  // Konuşma eşiği ortamın kendi gürültüsüne göre kayar (baseThr). Bunu iki
  // mekanizma besler:
  //
  //  1) AÇILIŞ KALİBRASYONU (viCalib*): mikrofon açılınca calibMs kadar
  //     KİMSE KONUŞMADAN ortam dinlenir. Ölçümün medyanı başlangıç gürültü
  //     tabanı, p90'ı ise (calibHeadroom ile) MUTLAK ALT EŞİK olur. Böylece
  //     salonun klima/kalabalık uğultusu "konuşma" sayılmaz ve sahada
  //     abs_min_rms'i elle kısma ihtiyacı kalkar. Sonuç localStorage'a yazılır
  //     (VI_CALIB_TTL_MS boyunca geçerli); operatör 'k' ile yeniden ölçtürür.
  //     Config'ten gelen abs_min_rms ALT SINIR olarak korunur — kalibrasyon
  //     eşiği yalnız YÜKSELTEBİLİR, asla elle ayarlanandan gevşetmez.
  //
  //  2) CANLI TABAN (viFloor*): son floorWindowMs'lik RMS penceresinin en
  //     sessiz %10'u (yüzdelik). Bu, eski EMA'nın yerine geçer. EMA yalnız
  //     "sessiz" sayılan tick'lerde güncellendiğinden GÜRÜLTÜLÜ ORTAMDA KİLİTLENİYORDU:
  //     ortam başlangıç tahmininin (0.01) üstündeyse her tick "konuşma" sayılır,
  //     taban hiç güncellenmez, sistem sonsuza dek boş kayıt gönderirdi. Yüzdelik
  //     her tick'te (TTS çalarken hariç — hoparlör yankısı tabanı şişirir) güncellenir;
  //     kişi konuşurken bile hecelerin arası pencerenin alt %10'unu doldurur.
  //     Kalibrasyon reddedilse bile bu katman ortamı yakalamayı sürdürür.
  //
  // calibrationEnabled=false → her iki mekanizma da devre dışı, eski EMA yolu
  // birebir çalışır (sergi günü tek anahtarla geri dönüş).
  let viCalibState = 'none';     // 'none' | 'running' | 'done' | 'failed'
  let viCalibSamples = [];
  let viCalibStartAt = 0;
  let viCalibAbsMin = 0;         // kalibrasyondan gelen mutlak alt eşik (0 = yok)
  let viCalibEl = null;          // "ortam ölçülüyor" ekran bildirimi
  let viFloorBuf = null;         // halka tampon (Float32Array) — son pencere RMS'leri
  let viFloorCap = 0;
  let viFloorHead = 0;
  let viFloorLen = 0;
  let viFloorTick = 0;           // yüzdelik hesabı için tick sayacı
  let viFloorTarget = 0;         // en son hesaplanan yüzdelik hedefi

  // Oyun modunda (drvGamePhase dolu) tek-kelime cevap beklenir; "cümle bitti"
  // ve "yeterince konuştu" eşiklerini kısaltmak tur başına ~400 ms gecikme
  // kazandırır. Sohbet modunda taban değerler kullanılır (doğal konuşma bölünmesin).
  function viSilenceMs() {
    return (drvGamePhase && VI.silenceMsGame) ? VI.silenceMsGame : VI.silenceMs;
  }
  function viMinSpeechMs() {
    return (drvGamePhase && VI.minSpeechMsGame) ? VI.minSpeechMsGame : VI.minSpeechMs;
  }

  // Mikrofon başlatılamadığında operatör görsün: sessiz console.warn yerine
  // ekranda kalıcı uyarı. Sürekli dinleme açılınca kendiliğinden kaybolur.
  function setMicWarn(on) {
    if (!viMicWarnEl) {
      if (!on) return;
      viMicWarnEl = document.createElement('div');
      viMicWarnEl.style.cssText =
        'position:fixed;bottom:10px;right:12px;z-index:60;pointer-events:none;' +
        'font:600 11px/1.4 monospace;letter-spacing:1px;color:rgba(255,90,90,0.75);';
      viMicWarnEl.textContent = '🎤 MİKROFON YOK — izin verin / cihazı bağlayın';
      document.body.appendChild(viMicWarnEl);
    }
    viMicWarnEl.style.display = on ? 'block' : 'none';
  }

  // Konuşma algılandı ama Whisper metin çıkaramadı ("hiç almıyor" hissinin en
  // sinsi hali: sistem duydu ama sessiz kaldı). Ziyaretçi/operatör GÖRSÜN diye
  // kısa bildirim — TTS harcamaz, 4 sn'de en fazla bir kez.
  function viShowHint(msg) {
    const now = Date.now();
    if (now - viHintLastAt < 4000) return;
    viHintLastAt = now;
    if (!viHintEl) {
      viHintEl = document.createElement('div');
      viHintEl.style.cssText =
        'position:fixed;bottom:56px;left:50%;transform:translateX(-50%);z-index:60;' +
        'pointer-events:none;padding:10px 18px;border-radius:12px;' +
        'background:rgba(0,0,0,0.72);border:1px solid rgba(120,220,255,0.35);' +
        'font:600 16px/1.4 system-ui,sans-serif;color:#cfeaff;';
      document.body.appendChild(viHintEl);
    }
    viHintEl.textContent = msg;
    viHintEl.style.display = 'block';
    setTimeout(() => { if (viHintEl) viHintEl.style.display = 'none'; }, 2200);
  }

  // ——— Mikrofon seviye göstergesi ('m' ile aç/kapa) ————————————————
  // Sahada "ses algılamıyor" şikayetinde GÖZLE teşhis: canlı RMS çubuğu,
  // eşik çizgisi ve durum. Çubuk kırmızı çizgiyi geçmiyorsa mikrofon kazancı
  // düşük (Windows ses ayarı) ya da config eşiği yüksek demektir.
  let viDbgEl = null;
  let viDbgOn = false;
  function viDebugUpdate(state, rms, thr) {
    if (!viDbgOn || !viDbgEl) return;
    const pct = Math.min(100, Math.round((rms || 0) * 2500));
    const thrPct = Math.min(100, Math.round((thr || 0) * 2500));
    viDbgEl.innerHTML =
      '🎤 ' + state
      + '<br>rms ' + (rms == null ? '—' : rms.toFixed(4))
      + ' / eşik ' + (thr == null ? '—' : thr.toFixed(4))
      + ' / taban ' + viNoiseFloor.toFixed(4)
      + '<br>kalib ' + (VI.calibrationEnabled ? viCalibState : 'kapalı')
      + ' · alt eşik ' + viEffAbsMin().toFixed(4)
      + (viCalibAbsMin ? ' (ölçüm)' : ' (config)')
      + '<div style="position:relative;height:8px;margin-top:4px;background:#123;border-radius:3px;">'
      +   '<div style="position:absolute;left:0;top:0;bottom:0;width:' + pct + '%;'
      +     'background:' + ((rms || 0) > (thr || 1) ? '#4f8' : '#29f') + ';border-radius:3px;"></div>'
      +   '<div style="position:absolute;left:' + thrPct + '%;top:-2px;bottom:-2px;width:2px;background:#f66;"></div>'
      + '</div>';
  }
  function viDebugToggle() {
    viDbgOn = !viDbgOn;
    if (viDbgOn && !viDbgEl) {
      viDbgEl = document.createElement('div');
      viDbgEl.style.cssText =
        'position:fixed;bottom:10px;left:12px;z-index:60;padding:8px 10px;pointer-events:none;'
        + 'background:rgba(0,0,0,0.72);border:1px solid rgba(120,220,255,0.35);border-radius:6px;'
        + 'font:600 11px/1.5 monospace;color:#9fdcff;min-width:240px;';
      document.body.appendChild(viDbgEl);
    }
    if (viDbgEl) viDbgEl.style.display = viDbgOn ? 'block' : 'none';
  }

  function viSetListeningBadge(on) {
    if (on === viShowListening) return;
    viShowListening = on;
    stListening = on;
    updateStateBadge();
  }

  function viStopRecorder(action) {
    if (!viRec || viRec.state !== 'recording' || viStopping) return;
    viPendingAction = action;
    viStopping = true;   // onstop işleyene kadar yeni kayıt açma
    // Gönderimden sonra kısa nefes: kontrol paneli 'thinking' yayıp mikrofonu
    // kapatana kadar tekrar tetiklenmesin.
    if (action === 'send') viHoldUntil = performance.now() + 800;
    try { viRec.stop(); } catch (_) {}
  }

  function viStartRecorder() {
    if (!viStream) return;
    // Sabit 128 kbps: tarayıcı varsayılanı düşük seçerse Whisper girdisi bozulmasın
    const recOpts = { audioBitsPerSecond: 128000 };
    if (viMime) recOpts.mimeType = viMime;
    try {
      viRec = new MediaRecorder(viStream, recOpts);
    } catch (e) {
      console.warn('VI: MediaRecorder açılamadı', e);
      viRec = null;
      return;
    }
    viChunks = [];
    viHadSpeech = false;
    viSpeechStartAt = 0;
    viOverlapTts = false;
    viPendingAction = null;
    viStopping = false;
    viRecStartAt = performance.now();
    viLastLoudAt = viRecStartAt;
    viRec.ondataavailable = (ev) => { if (ev.data && ev.data.size > 0) viChunks.push(ev.data); };
    viRec.onstop = viOnRecStop;
    try { viRec.start(); } catch (e) { console.warn('VI: kayıt başlamadı', e); viRec = null; }
  }

  function viInputGateAllows(speechStartAt) {
    // Kapı yalnız oyun akışında geçerlidir; sohbet/selam/göz modu eskisi gibi
    // her yeni sözü işler. İki damga da performance.now() zaman tabanındadır.
    if (!drvGamePhase || speechStartAt >= drvInputGateAt) return true;
    if (Number.isFinite(drvInputGateAt)) {
      console.info('VI: oyun girdisi atıldı — konuşma cevap penceresinden '
        + Math.max(0, Math.round(drvInputGateAt - speechStartAt)) + ' ms erken başladı');
    } else {
      console.info('VI: oyun girdisi atıldı — cevap penceresi hâlâ kapalı; konuşma '
        + Math.max(0, Math.round(performance.now() - speechStartAt)) + ' ms önce başladı');
    }
    return false;
  }

  function viOnRecStop() {
    const action = viPendingAction; viPendingAction = null;
    const chunks = viChunks; viChunks = [];
    const hadSpeech = viHadSpeech;
    const speechStartAt = viSpeechStartAt;
    const durMs = performance.now() - viRecStartAt;
    // Konuşma başlangıcından öncesi sunucuda kırpılsın: kayıt sürekli açık
    // olduğundan blob'un başında sessizlik/TTS yankısı birikir — Whisper'a
    // girmesi hem yavaşlatır hem AI'nın kendi cümlesini "duymasına" yol açar.
    const trimMs = (hadSpeech && viSpeechStartAt > viRecStartAt)
      ? Math.max(0, Math.round(viSpeechStartAt - viRecStartAt - VI_TRIM_PAD_MS)) : 0;
    const overlapTts = viOverlapTts;
    viRec = null;       // sonraki tick yeni kayıt açar (cooldown'a göre)
    viStopping = false; // artık güvenle yeniden başlatılabilir
    if (action === 'send' && hadSpeech && chunks.length && durMs >= viMinSpeechMs()) {
      if (!viInputGateAllows(speechStartAt)) return;
      const blob = new Blob(chunks, { type: viMime || 'audio/webm' });
      viTranscribeAndSend(blob, trimMs, overlapTts, speechStartAt);
    }
  }

  async function viTranscribeAndSend(blob, trimMs, overlapTts, speechStartAt) {
    // Oyun-sonu→göz geçişi beklenirken duyulan ses (bitiş TTS'inin yankısı,
    // oda gürültüsü, geçiş sırasındaki söz) İŞLENMEZ: gözler her zaman görünür,
    // selam ancak gözler açıldıktan sonraki YENİ sesle başlar.
    if (drvEndPending) return;
    // onstop'tan sonra önceki STT kuyruğunda beklerken kapı kapanmış olabilir;
    // başlangıç damgasını blob'la taşı ki ikinci VAD parçası yeni soruya kaymasın.
    if (!viInputGateAllows(speechStartAt)) {
      if (!viBusyTranscribe) setSttWait(false);
      return;
    }
    // SES GİRDİSİ = ETKİNLİK: transkript boş dönse bile ("Duyamadım") ziyaretçi
    // KONUŞUYORDUR — boşta sayacı sıfırlanır. Aksi halde tanınmayan denemeler
    // birikip oyun ORTASINDA attract/sıfırlamayı tetikliyordu.
    drvLastActivityAt = Date.now();
    if (viBusyTranscribe) {
      // Önceki STT sürerken biten söz DÜŞMESİN (eski davranış sessizce atıyordu
      // → "hiç almıyor"). En son söz tek slotta bekler; mevcut istek bitince işlenir.
      viPendingBlob = {
        blob: blob, trimMs: trimMs, overlapTts: overlapTts,
        speechStartAt: speechStartAt,
      };
      return;
    }
    viBusyTranscribe = true;   // viHoldUntil zaten viStopRecorder('send')'de ayarlandı
    setSttWait(true);          // "bekle — yazıya çeviriyorum" balonu (tekrar konuşmasın)
    const t0 = performance.now();
    try {
      const fd = new FormData();
      fd.append('audio', blob, 'utt.webm');
      if (trimMs > 0) fd.append('trim_ms', String(trimMs));
      // Kayıt TTS çalarken sürdüyse son çalan metni gönder: sunucu, transkript
      // salt yankıysa (AI kendi cümlesini duyduysa) atar.
      if (overlapTts && viTtsRecent.length) {
        fd.append('echo_text', viTtsRecent.join(' ').slice(-600));
      }
      // Oyun modunda kısa komut sözlüğüne bias ver (backend WHISPER_GAME_PROMPT).
      if (drvGamePhase) fd.append('context', 'game');
      // ZAMAN AŞIMI ŞART: /api/transcribe sunucuda takılırsa (CUDA kütüphane
      // hatası vb.) yanıtsız fetch viBusyTranscribe'ı SONSUZA DEK true bırakır
      // → mikrofon "duyar" ama hiçbir söz işlenmez (sahada yaşanan sağırlık).
      // 25 sn'de iptal et; finally bayrağı bırakır, döngü kendini toparlar.
      const ctl = new AbortController();
      const tid = setTimeout(() => ctl.abort(), 25000);
      let r;
      try {
        r = await fetch('/api/transcribe', { method: 'POST', body: fd, signal: ctl.signal });
      } finally {
        clearTimeout(tid);
      }
      const data = await r.json();
      const txt = ((data && data.text) || '').trim();
      const m = (data && data.meta) || {};
      console.info('VI: stt toplam ' + Math.round(performance.now() - t0) + ' ms'
        + ' | model ' + (m.stt_ms || 0) + ' ms | ses ' + (m.duration_s || 0).toFixed(1) + ' sn'
        + (m.trim_ms ? ' | trim ' + m.trim_ms + ' ms' : '')
        + (txt ? '' : ' | SONUÇ BOŞ (' + ((data && data.warning) || '?') + ')'));
      if (txt && !drvEndPending) {   // geçiş penceresinde biten STT de atılır
        // STT sürerken cevap/timeout yeni tura geçmiş olabilir. Eski kaydı o
        // turun güncel jetonuyla göndermemek için kapıyı gönderim öncesi yine doğrula.
        if (!viInputGateAllows(speechStartAt)) return;
        // Oyunu EKRAN-İÇİ sürücü yürütüyorsa (drvGamePhase dolu) cevap panele
        // GİTMEZ: arka plandaki panel sekmesi Chrome kısıtlamasıyla dakikada bir
        // uyanır — cevap orada bekletilirken sayaç "süre doldu" der (kum saati +
        // kilitlenme şikâyeti). Panel yalnız oyunu KENDİSİ sürüyorsa girdi alır.
        if (bc && panelAlive() && !drvGamePhase) {
          bc.postMessage({ type: 'voice_input', text: txt });  // panel açık: oradan işlenir
        } else {
          drvHandleText(txt);   // panelsiz sergi: ekran-içi sürücü işler
        }
      } else if (data && data.warning === 'blocked') {
        // YASAKLI SÖZ: sunucu metni HİÇ göndermedi (ekranda görünmez, uyarı da
        // verilmez — sansür olduğu belli edilmez). Yalnızca "anlamadım" repliği
        // okunur. Oyun motoruna girdi gitmediği için tur tüketilmez; çocuk aynı
        // soruya yeniden cevap verebilir, sayaç yerinde işler.
        console.info('VI: yasaklı girdi engellendi (ekrana yazılmadı)');
        if (!drvEndPending) {
          drvSend({
            type: 'ai_reply',
            jest_id: data.jest_id || 'anlamadim',
            yanit: data.yanit || 'Anlamadım, başka bir şey söyler misin?',
            yogunluk: data.yogunluk || 0.6,
          });
        }
      } else if (data && data.warning === 'no_speech') {
        // Ses vardı ama metin çıkmadı (uzak/kısık konuşma) — sessiz kalma,
        // görünür geri bildirim ver. Yankı ataması (tts_echo) kasıtlı sessizdir.
        viShowHint('🙉 Duyamadım — biraz yaklaşıp tekrar söyler misin?');
      }
    } catch (e) {
      console.warn('VI: transkripsiyon hatası', e);
    } finally {
      drvLastActivityAt = Date.now();  // uzun STT de boşta sayılmaz
      viBusyTranscribe = false;
      if (viPendingBlob) {       // sırada bekleyen söz varsa hemen işle
        const p = viPendingBlob; viPendingBlob = null;
        viTranscribeAndSend(
          p.blob, p.trimMs, p.overlapTts, p.speechStartAt
        );   // balon açık kalır
      } else {
        setSttWait(false);
      }
    }
  }

  // Yürürlükteki mutlak alt eşik: config'ten gelen değer ile kalibrasyonun
  // bulduğunun BÜYÜĞÜ. Kalibrasyon yoksa/reddedildiyse davranış eskisi gibi.
  function viEffAbsMin() {
    return Math.max(VI.absMinRms, viCalibAbsMin);
  }

  // Bir dizinin q'uncu yüzdeliği (dizi SIRALI gelmeli).
  function viPct(sorted, q) {
    if (!sorted.length) return 0;
    return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(sorted.length * q)))];
  }

  function viFloorReset() {
    viFloorCap = Math.max(40, Math.round(VI.floorWindowMs / 50));   // tick 50 ms
    viFloorBuf = new Float32Array(viFloorCap);
    viFloorHead = 0; viFloorLen = 0; viFloorTick = 0; viFloorTarget = 0;
  }

  // Canlı gürültü tabanı: pencereye örnek ekle, yüzdelik hedefe doğru yumuşat.
  function viFloorPush(rms) {
    if (!viFloorBuf) viFloorReset();
    viFloorBuf[viFloorHead] = rms;
    viFloorHead = (viFloorHead + 1) % viFloorCap;
    if (viFloorLen < viFloorCap) viFloorLen++;
    // Yüzdelik 500 ms'de bir hesaplanır — her tick sıralamak gereksiz.
    if (++viFloorTick >= 10 && viFloorLen >= 40) {
      viFloorTick = 0;
      // TypedArray.sort() varsayılan olarak SAYISAL sıralar (Array'in aksine).
      viFloorTarget = viPct(viFloorBuf.slice(0, viFloorLen).sort(), VI.floorPct);
    }
    if (viFloorTarget > 0) {
      // Yükselirken hızlı uy (ortam gürültülendi, hemen sağırlaşma), düşerken
      // yavaş in (anlık sessizlik eşiği dibe çekip gürültüyü konuşma sandırmasın).
      const k = viFloorTarget > viNoiseFloor ? 0.20 : 0.06;
      viNoiseFloor += (viFloorTarget - viNoiseFloor) * k;
    }
    viNoiseFloor = Math.min(VI_FLOOR_MAX_RMS, Math.max(VI_FLOOR_MIN_RMS, viNoiseFloor));
  }

  // Kalibrasyon sırasında ekranda görünen bildirim (ziyaretçi/operatör sussun).
  function viCalibNotice(msg) {
    if (!viCalibEl) {
      if (!msg) return;
      viCalibEl = document.createElement('div');
      viCalibEl.style.cssText =
        'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:70;' +
        'pointer-events:none;padding:10px 20px;border-radius:12px;' +
        'background:rgba(0,0,0,0.78);border:1px solid rgba(120,220,255,0.45);' +
        'font:600 16px/1.4 system-ui,sans-serif;color:#cfeaff;text-align:center;';
      document.body.appendChild(viCalibEl);
    }
    viCalibEl.textContent = msg || '';
    viCalibEl.style.display = msg ? 'block' : 'none';
  }

  function viCalibLoad() {
    try {
      const raw = localStorage.getItem(VI_CALIB_STORE_KEY);
      if (!raw) return false;
      const d = JSON.parse(raw);
      if (!d || typeof d.floor !== 'number' || typeof d.absMin !== 'number') return false;
      if (!d.at || (Date.now() - d.at) > VI_CALIB_TTL_MS) return false;
      viNoiseFloor = Math.min(VI_FLOOR_MAX_RMS, Math.max(VI_FLOOR_MIN_RMS, d.floor));
      viCalibAbsMin = d.absMin;
      viCalibState = 'done';
      console.info('VI: kayıtlı ortam kalibrasyonu kullanıldı — taban %s / alt eşik %s',
                   viNoiseFloor.toFixed(4), viEffAbsMin().toFixed(4));
      return true;
    } catch (_) { return false; }   // localStorage kapalı/bozuk → yeniden ölç
  }

  function viCalibSave() {
    try {
      localStorage.setItem(VI_CALIB_STORE_KEY, JSON.stringify(
        { floor: viNoiseFloor, absMin: viCalibAbsMin, at: Date.now() }));
    } catch (_) { /* kalıcı yazamadık — bu oturumda yine de geçerli */ }
  }

  // force=true (operatör 'k' tuşu): kayıtlı ölçümü yok say, yeniden ölç.
  function viCalibStart(force) {
    if (!VI.calibrationEnabled || !viActive) return;
    if (viCalibState === 'running') return;
    if (!force && viCalibLoad()) return;
    viCalibState = 'running';
    viCalibSamples = [];
    viCalibStartAt = performance.now();
    viCalibAbsMin = 0;                 // ölçüm bitene dek config eşiği geçerli
    viFloorReset();
    // Ölçüm boyunca kayıt açılmasın (mikrofon yalnız dinliyor).
    viHoldUntil = viCalibStartAt + VI.calibMs + 300;
    if (viRec && viRec.state === 'recording') viStopRecorder('discard');
    viSetListeningBadge(false);
    console.info('VI: ortam gürültüsü ölçülüyor (%d ms)', VI.calibMs);
  }

  // Her tick'te kalibrasyon adımı. true dönerse çağıran tick'i BİTİRİR
  // (ölçüm sürerken kayıt/VAD işletilmez).
  function viCalibStep(rms, now) {
    if (viCalibState !== 'running') return false;
    // TTS çalıyorsa ölçüm hoparlörün kendi sesini "ortam" sanır: örnek alma,
    // pencereyi kaydır. (Açılışta normalde ses çalmaz; güvenlik önlemi.)
    if (stSpeaking) {
      viCalibStartAt = now;
      viCalibSamples = [];
      viCalibNotice('🎤 Ortam ölçümü bekliyor (ses çalıyor)…');
      return true;
    }
    viCalibSamples.push(rms);
    const elapsed = now - viCalibStartAt;
    const left = Math.max(0, Math.ceil((VI.calibMs - elapsed) / 1000));
    viCalibNotice('🎤 Ortam sesi ölçülüyor — lütfen sessiz olun… ' + left);
    viDebugUpdate('KALİBRASYON (' + viCalibSamples.length + ' örnek)', rms, null);
    // Süre dolduysa ve yeterli örnek varsa bitir. AudioContext askıya alınıp
    // örnek toplanamadıysa süre uzar; 3 katı aşılırsa başarısız sayılır.
    if (elapsed >= VI.calibMs && viCalibSamples.length >= 40) { viCalibFinish(); return true; }
    if (elapsed >= VI.calibMs * 3) { viCalibFail('yeterli ölçüm alınamadı'); return true; }
    return true;
  }

  function viCalibFail(sebep) {
    viCalibSamples = [];
    viCalibAbsMin = 0;              // config'teki elle ayarlı eşiğe dön
    viCalibState = 'failed';
    viCalibNotice('');
    // Canlı yüzdelik taban çalışmayı sürdürür — sistem yine de ortama uyar.
    console.warn('VI: ortam kalibrasyonu başarısız (%s) — config eşikleri + canlı taban kullanılacak', sebep);
    viShowHint('Ortam ölçümü yapılamadı — varsayılan ayarlarla devam');
  }

  function viCalibFinish() {
    const s = viCalibSamples.slice().sort((a, b) => a - b);
    viCalibSamples = [];
    const p50 = viPct(s, 0.50);
    const p90 = viPct(s, 0.90);
    // Ölçüm boyunca konuşulduysa / mikrofon bozuksa medyan fırlar. Böyle bir
    // ölçüyü KABUL ETMEK eşiği tavana çakıp sistemi sağır ederdi — reddet.
    if (p50 > VI.calibMaxRms) {
      viCalibFail('ortam çok gürültülü ya da ölçüm sırasında konuşuldu (medyan '
                  + p50.toFixed(4) + ')');
      return;
    }
    viNoiseFloor = Math.min(VI_FLOOR_MAX_RMS, Math.max(VI_FLOOR_MIN_RMS, p50));
    viCalibAbsMin = p90 * VI.calibHeadroom;
    viCalibState = 'done';
    viFloorReset();
    viFloorTarget = viNoiseFloor;   // canlı taban ölçülen değerden devralsın
    viCalibSave();
    viCalibNotice('');
    console.info('VI: ortam kalibre edildi — medyan %s / p90 %s → taban %s, alt eşik %s',
                 p50.toFixed(4), p90.toFixed(4), viNoiseFloor.toFixed(4), viEffAbsMin().toFixed(4));
  }

  function viMonitorTick() {
    if (!viActive || !viAnalyser) return;
    // KRİTİK: AudioContext askıdaysa (arka plan sekmesi / autoplay politikası)
    // analyser SIFIR okur → RMS hep 0 → ne kadar bağırılsa da konuşma algılanmaz
    // ("mikrofon ses almıyor" hissi). Her tik'te canlı tutmayı dene; askıda
    // kaldıkça görünür uyarı ver (kiosk bayrakları yoksa sekmeyi öne al / tıkla).
    if (viCtx && viCtx.state === 'suspended') {
      viCtx.resume().catch(() => {});
      setMicWarn(true);
      viDebugUpdate('AudioContext ASKIDA (ekrana tıkla)', null, null);
      return;   // askıdayken ölçüm anlamsız
    }
    if (viMicWarnEl && viMicWarnEl.style.display === 'block') setMicWarn(false);
    const now = performance.now();

    // ——— RMS (ses seviyesi) ölç — barge-in kararı da buna bakar ———
    viAnalyser.getFloatTimeDomainData(viData);
    let sum = 0;
    for (let i = 0; i < viData.length; i++) sum += viData[i] * viData[i];
    const rms = Math.sqrt(sum / viData.length);

    // ——— Ortam kalibrasyonu / canlı gürültü tabanı ———
    // Ölçüm sürerken tick BURADA biter: kayıt açılmaz, VAD işletilmez.
    if (viCalibStep(rms, now)) return;
    // Canlı taban her tick güncellenir — TTS çalarken HARİÇ (hoparlör yankısı
    // tabanı şişirir). Konuşma sürerken de güncellenir: yüzdelik buna dayanıklı,
    // eski EMA'nın gürültülü ortamdaki kilitlenmesi böyle kırılır.
    if (VI.calibrationEnabled && !stSpeaking) viFloorPush(rms);

    const baseThr = Math.max(viEffAbsMin(), viNoiseFloor * VI.onsetMult);

    // SERT KAPI: yalnızca AI DÜŞÜNÜRKEN (sunucu meşgul, çalan ses YOK) → kaydı at.
    if (stThinking) {
      if (viRec && viRec.state === 'recording') viStopRecorder('discard');
      viWasGated = true;
      viSetListeningBadge(false);
      viDebugUpdate('AI düşünüyor — dinleme duraklatıldı', rms, baseThr);
      return;
    }

    // AI KONUŞURKEN (TTS çalıyor). İki mod:
    if (stSpeaking) {
      viWasSpeakingTick = true;                          // bitiş geçişi aşağıda yakalanır
      if (viRec && viRec.state === 'recording') viOverlapTts = true;  // yankı riski işareti
      const bThr = baseThr * VI.bargeInMult;   // ekranın kendi yankısının üstündeki eşik

      // ——— holdDuringSpeech: AI'yı KESME, söyleneni BİRİKTİR ———
      // Mikrofon açık; kayıt sürer ama GÖNDERİLMEZ. bThr üstünde gerçek konuşma
      // duyulursa viHadSpeech işaretlenir (yalnız echo ise işaretlenmez → gönderilmez).
      // stSpeaking false olunca (AI cümlesini bitirince) aşağıdaki normal
      // endpointing biriken kaydı transkribe edip cevap olarak işler.
      if (VI.holdDuringSpeech) {
        viWasGated = false;   // konuşma bitince cooldown ekleme → kayıt sürekliliği bozulmasın
        if ((!viRec || viRec.state !== 'recording') && !viStopping && now >= viHoldUntil) {
          viStartRecorder();  // yoksa başlat (echo dolu ama bThr geçilene dek viHadSpeech=false)
        }
        if (viRec && viRec.state === 'recording') {
          if (rms > bThr) {                     // ekranın yankısının üstünde → gerçek konuşma
            viLastLoudAt = now;
            if (!viHadSpeech) viSpeechStartAt = now;
            viHadSpeech = true;
          }
          const sinceStart = now - viRecStartAt;
          if (viHadSpeech && sinceStart >= VI.maxUtteranceMs) {
            viStopRecorder('send');             // güvenlik tavanı (çok uzun): yine de gönder
          } else if (!viHadSpeech && sinceStart >= VI_HOLD_REFRESH_MS) {
            viStopRecorder('discard');          // yalnız yankı birikti → sık tazele (blob kısa kalsın)
          }
        }
        viSetListeningBadge(false);
        viDebugUpdate(viHadSpeech ? 'AI konuşuyor — sözünüz bekletiliyor'
                                  : 'AI konuşuyor (dinliyor)', rms, bThr);
        return;                                 // TTS sürsün; AI kesilmez
      }

      // ——— BARGE-IN (holdDuringSpeech=false): kullanıcı araya girerse TTS'i kes ———
      if (VI.bargeIn && rms > bThr) {
        if (!viBargeStart) viBargeStart = now;
        if (now - viBargeStart >= VI.bargeInMinMs) {
          stopSpeech();               // AI'yı kes (çalan ses + kuyruk)
          viBargeStart = 0;
          viWasGated = false;         // barge-in: cooldown BEKLEME, hemen kaydet
          viHoldUntil = 0;
          // aşağı düş → normal kayıt başlasın (artık stSpeaking=false)
        } else {
          viSetListeningBadge(false);
          viDebugUpdate('AI konuşuyor — araya girme dinleniyor', rms, bThr);
          return;                     // henüz yeterli değil, TTS sürsün
        }
      } else {
        viBargeStart = 0;
        viSetListeningBadge(false);
        viDebugUpdate('AI konuşuyor (araya girmeye hazır)', rms, bThr);
        return;                       // TTS artığı/gürültü → dinle ama kaydetme
      }
    }

    // Gate yeni kalktıysa (düşünme/konuşma bitti): AI'nın son hecesini yakalamamak
    // için kısa bekle. (Barge-in ile geldiyse yukarıda viWasGated=false yapıldı.)
    if (viWasGated) { viWasGated = false; viHoldUntil = now + VI.cooldownMs; }

    // AI konuşması YENİ bitti ve biriken kayıtta gerçek söz yok → içerik salt
    // yankı/sessizlik. At ki sonraki cevap TERTEMİZ bir kayda girsin (yankının
    // Whisper'a gidip AI'nın kendi cümlesi olarak dönmesi = "yanlış alıyor").
    if (viWasSpeakingTick) {
      viWasSpeakingTick = false;
      if (viRec && viRec.state === 'recording' && !viHadSpeech) {
        viStopRecorder('discard');   // 1 tick (50 ms) sonra taze kayıt açılır
      }
    }

    const loud = rms > baseThr;
    viDebugUpdate(
      (viRec && viRec.state === 'recording')
        ? (viHadSpeech ? 'KAYIT — konuşma algılandı' : 'KAYIT — konuşma bekleniyor')
        : 'DİNLİYOR (boşta)',
      rms, baseThr);

    // Kayıt yoksa (ve bir stop işlenmiyorsa, cooldown bittiyse) başlat;
    // bu arada rozeti "dinliyor" yap.
    if (!viRec || viRec.state !== 'recording') {
      viSetListeningBadge(true);
      if (!viStopping && now >= viHoldUntil) viStartRecorder();
      // ESKİ yol (calibrationEnabled=false): yalnız sessiz tick'lerde EMA.
      if (!VI.calibrationEnabled && !loud) viNoiseFloor = viNoiseFloor * 0.95 + rms * 0.05;
      return;
    }

    if (loud) {
      viLastLoudAt = now;
      if (!viHadSpeech) viSpeechStartAt = now;
      viHadSpeech = true;
    } else if (!viHadSpeech && !VI.calibrationEnabled) {
      viNoiseFloor = viNoiseFloor * 0.95 + rms * 0.05;             // ESKİ yol: hâlâ sessizken taban
    }

    // ANLIK SELAM (test modu, panelsiz): boştayken ses duyulur duyulmaz —
    // çeviriyi BEKLEMEDEN — selamla + oyun sorusunu sor. Segment atılır;
    // içerik zaten kullanılmazdı (boşta her söz selama gider). Selam sonrası
    // phase='menu' olduğundan bu koşul (!drvGamePhase) tekrar sağlanmaz.
    if (viHadSpeech && (now - viSpeechStartAt) >= VI.minSpeechMs
        && testModeOn && !panelAlive() && !drvGamePhase && !drvBusyActive()
        && !drvEndPending) {   // oyun-sonu→göz geçişi beklerken selam tetiklenmez
      viStopRecorder('discard');
      drvInstantGreet();
      return;
    }

    const sinceStart = now - viRecStartAt;
    const sinceLoud = now - viLastLoudAt;

    if (viHadSpeech && sinceLoud >= viSilenceMs() && sinceStart >= viMinSpeechMs()) {
      viStopRecorder('send');        // kişi sustu → gönder
    } else if (viHadSpeech && sinceStart >= VI.maxUtteranceMs) {
      viStopRecorder('send');        // güvenlik tavanı
    } else if (!viHadSpeech && sinceStart >= viSilenceMs() * 4) {
      viStopRecorder('discard');     // sadece sessizlik birikti → tazele (taban güncel kalsın)
    }
  }

  // Dönüş: true = dinleme açıldı, false = açılamadı (çağıran tekrar dener).
  async function viEnable() {
    if (viActive) return true;
    if (!VI.enabled) return false;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia
        || typeof MediaRecorder === 'undefined' || !AudioCtx) {
      console.warn('VI: tarayıcı mikrofon/AudioContext API desteklemiyor');
      setMicWarn(true);
      return false;
    }
    try {
      viStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: VI.echoCancellation,
          noiseSuppression: VI.noiseSuppression,
          autoGainControl: VI.autoGain,
        },
      });
    } catch (e) {
      console.warn('VI: mikrofon reddedildi/yok —', e.name);
      setMicWarn(true);   // görünür uyarı; kendini-onaran döngü tekrar dener
      return false;
    }
    viMime = '';
    for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']) {
      if (MediaRecorder.isTypeSupported(m)) { viMime = m; break; }
    }
    try {
      viCtx = new AudioCtx();
      const src = viCtx.createMediaStreamSource(viStream);
      viAnalyser = viCtx.createAnalyser();
      // 2048 örnek @48kHz ≈ 43 ms pencere: 50 ms'lik tick'in neredeyse tamamı
      // ölçülür (1024=21 ms'de kısa/sessiz ünsüz başlangıçları kaçabiliyordu).
      viAnalyser.fftSize = 2048;
      viData = new Float32Array(viAnalyser.fftSize);
      src.connect(viAnalyser);       // destination'a BAĞLAMA → geri besleme yok
      if (viCtx.state === 'suspended') viCtx.resume().catch(() => {});
      if (viCtx.state === 'suspended') {
        // Jestsiz açılışta tarayıcı AudioContext'i askıda tutabilir (autoplay
        // politikası): analyser hep 0 okur, VAD sağır kalır. İlk etkileşimde
        // devam ettir — kiosk bayrağıyla açılan tarayıcıda bu duruma düşülmez.
        const viResumeCtx = () => { if (viCtx && viCtx.state === 'suspended') viCtx.resume().catch(() => {}); };
        window.addEventListener('pointerdown', viResumeCtx, { once: true });
        window.addEventListener('keydown', viResumeCtx, { once: true });
      }
    } catch (e) {
      console.warn('VI: AudioContext kurulamadı', e);
      viDisable();
      setMicWarn(true);
      return false;
    }
    viActive = true;
    viNoiseFloor = 0.01;
    viWasGated = false;
    viHoldUntil = performance.now() + 500;
    if (viMonitorId) clearInterval(viMonitorId);
    viMonitorId = setInterval(viMonitorTick, 50);
    setMicWarn(false);   // açıldı → uyarıyı kaldır
    // Ortam ölçümü: kayıtlı ve taze bir kalibrasyon varsa onu kullanır,
    // yoksa calibMs boyunca sessiz ortamı dinleyip eşikleri kendi kurar.
    if (VI.calibrationEnabled) {
      viCalibState = 'none';
      viFloorReset();
      viCalibStart(false);
    }
    console.info('VI: sürekli sesli giriş AÇIK');
    return true;
  }

  function viDisable() {
    viActive = false;
    if (viMonitorId) { clearInterval(viMonitorId); viMonitorId = null; }
    if (viRec && viRec.state === 'recording') { try { viRec.stop(); } catch (_) {} }
    viRec = null;
    if (viStream) { for (const t of viStream.getTracks()) { try { t.stop(); } catch (_) {} } viStream = null; }
    if (viCtx) { try { viCtx.close(); } catch (_) {} viCtx = null; }
    viAnalyser = null; viData = null;
    if (viCalibState === 'running') viCalibState = 'none';   // yarım ölçüm sayılmasın
    viCalibNotice('');
    viSetListeningBadge(false);
    console.info('VI: sürekli sesli giriş KAPALI');
  }

  // viWantOn: sürekli dinlemenin AÇIK OLMASI isteniyor mu? Kendini-onaran
  // döngü yalnız bu true iken tekrar dener; 'd' ile elle kapatınca döngü
  // mikrofonu inatla geri açmaz.
  let viWantOn = false;
  function viToggle() {
    if (viActive) { viWantOn = false; setMicWarn(false); viDisable(); }
    else { viWantOn = true; viEnable(); }
  }

  async function loadVoiceInputConfig() {
    try {
      const r = await fetch('/api/config');
      const d = await r.json();
      if (d && d.max_user_input_chars) drvMaxChars = d.max_user_input_chars;
      const v = d && d.voice_input;
      if (!v) return;
      VI.enabled = v.enabled !== false;
      VI.autostart = v.autostart !== false;
      if (typeof v.silence_ms === 'number') VI.silenceMs = v.silence_ms;
      if (typeof v.min_speech_ms === 'number') VI.minSpeechMs = v.min_speech_ms;
      if (typeof v.silence_ms_game === 'number') VI.silenceMsGame = v.silence_ms_game;
      if (typeof v.min_speech_ms_game === 'number') VI.minSpeechMsGame = v.min_speech_ms_game;
      if (typeof v.max_utterance_ms === 'number') VI.maxUtteranceMs = v.max_utterance_ms;
      if (typeof v.onset_mult === 'number') VI.onsetMult = v.onset_mult;
      if (typeof v.abs_min_rms === 'number') VI.absMinRms = v.abs_min_rms;
      if (typeof v.cooldown_ms === 'number') VI.cooldownMs = v.cooldown_ms;
      if (typeof v.echo_cancellation === 'boolean') VI.echoCancellation = v.echo_cancellation;
      if (typeof v.noise_suppression === 'boolean') VI.noiseSuppression = v.noise_suppression;
      if (typeof v.auto_gain === 'boolean') VI.autoGain = v.auto_gain;
      if (typeof v.barge_in === 'boolean') VI.bargeIn = v.barge_in;
      if (typeof v.barge_in_mult === 'number') VI.bargeInMult = v.barge_in_mult;
      if (typeof v.barge_in_min_ms === 'number') VI.bargeInMinMs = v.barge_in_min_ms;
      if (typeof v.hold_during_speech === 'boolean') VI.holdDuringSpeech = v.hold_during_speech;
      if (typeof v.calibration_enabled === 'boolean') VI.calibrationEnabled = v.calibration_enabled;
      if (typeof v.calib_ms === 'number') VI.calibMs = v.calib_ms;
      if (typeof v.calib_headroom === 'number') VI.calibHeadroom = v.calib_headroom;
      if (typeof v.calib_max_rms === 'number') VI.calibMaxRms = v.calib_max_rms;
      if (typeof v.floor_window_ms === 'number') VI.floorWindowMs = v.floor_window_ms;
      if (typeof v.floor_pct === 'number') VI.floorPct = v.floor_pct;
    } catch (e) {
      console.warn('VI: config alınamadı, varsayılanlar kullanılıyor', e);
    }
  }

  // Aynı /api/config yanıtından test modu durumunu da al (rozet açılışta doğru olsun).
  async function loadTestModeState() {
    try {
      const r = await fetch('/api/config');
      const d = await r.json();
      if (d && typeof d.test_mode === 'boolean') setTestBadge(d.test_mode);
    } catch (_) { /* rozet kapalı kalır */ }
  }

  // ——— Panelsiz sürücü (standalone) ————————————————————————————
  // Sergide yalnız BU EKRAN açıktır: kontrol paneli kapalıyken sesle gelen
  // metni panelin yaptığı gibi backend'e yönlendirir (selam → yeni oturum,
  // oyun → /api/game/*, sohbet → /api/send) ve sonuçları handleMessage ile
  // AYNI render yolundan geçirir. Panel açıksa (ping alınıyorsa) eski akış
  // sürer: metin panele gider, burada işlenmez — çift işleme olmaz. Kelime
  // oyunu geri sayım otoritesi ve boşta/attract oturum sıfırlama da panel
  // yokken buradadır (control.js'teki otoritenin birebir portu).
  let lastPanelMsgAt = 0;
  function panelAlive() { return (Date.now() - lastPanelMsgAt) < 6000; }

  const DRV_GREETING_RE = /\b(merhaba|merhabalar|selam|selamlar|gunaydin|naber)\b|\biyi (gunler|aksamlar)\b/;
  const DRV_NEW_SESSION_REPLY = 'Merhaba. Sohbet edebiliriz. Oyun için "oyun oynayalım" de.';
  const DRV_HOME = [
    { key: 'sohbet', label: 'Sohbet et' },
    { key: 'oyun', label: 'Oyun oynayalım' },
  ];
  const DRV_HOME_TEST = [
    { key: 'oyun', label: 'Oyun oynayalım' },
  ];
  let drvMaxChars = 240;         // /api/config max_user_input_chars ile güncellenir
  let drvGamePhase = null;       // null | 'menu' | 'kelime' | 'quiz' | ...
  let drvTurnId = null;          // son uygulanan payload'ın sunucu tur jetonu
  let drvInputGateAt = 0;        // performance.now(): Infinity=kapalı, 0=oyun dışında açık
  let drvApplySeq = 0;           // bekleyen TTS sonrası eski payload'ın sayaç açmasını önler
  let drvOptions = [];           // ekrandaki seçenek butonları (ses eşleşmesi için)
  let drvSentUserText = '';      // balona son yazılan kullanıcı girdisi (fuzzy düzeltme kıyası)
  let drvBusy = false;           // aynı anda tek metin işlensin
  // Sunucu isteği 15 sn, TTS bitiş sigortası 20 sn sürebilir; daktilo ve ağ payı
  // eklenince eski 15 sn eşiği meşru uzun quiz sorusunda kilidi erken açıyordu.
  // Yine de beklenmedik asılı promise sürücüyü sonsuza dek sağır bırakmasın.
  let drvBusyAt = 0;
  const DRV_BUSY_STALE_MS = 60000;
  function drvBusyActive() {
    if (!drvBusy) return false;
    if (Date.now() - drvBusyAt > DRV_BUSY_STALE_MS) {
      console.warn('DRV: busy bayatladı — sigorta kilidi açtı');
      drvBusy = false;
      return false;
    }
    return true;
  }
  let drvTimer = { id: null, who: null, endsAt: 0, seconds: 0 };
  let drvLastActivityAt = Date.now();
  let drvAttractOn = false;
  let drvCountdownId = null;
  let drvEndSeq = 0;      // oyun-sonu→göz geçişi bekleme jetonu (yeni etkileşim iptal eder)
  // Oyun-sonu→göz geçişi BEKLERKEN ses girdisi işlenmez: bitiş mesajının
  // yankısı ya da oda gürültüsü anlık selamı tetikleyip göz ekranını atlatmasın
  // (kural: gözler HER ZAMAN görünür; selam ancak gözler açıldıktan SONRA
  // duyulan sesle başlar). Bayrak drvEndToAttract'ın finally'sinde temizlenir.
  let drvEndPending = false;
  const DRV_ATTRACT_AFTER_MS = 60000;
  // OYUN AKTİFKEN (menü hariç) 60 sn'lik boşta sıfırlama DEVRE DIŞI: oyun
  // ortasında "ziyaretçi gitti" kararını boşta sayacı DEĞİL oyun kuralı verir
  // (art arda 2 soru cevapsız zaman aşımı → backend terk_edildi ile kapatır).
  // Bu süre o kuralın hiç işleyemeyeceği durumlara (örn. "başla" bekleyen hazır
  // ekranında hiç ses gelmemesi) karşı mutlak sessizlik SİGORTASIDIR.
  const DRV_GAME_IDLE_FUSE_MS = 300000;
  // Attract'a girerken oturum ZATEN sifirlanir (asagida) — ziyaretcinin
  // kaybedecegi bir sey kalmadigindan "Hala orada misin?" uyarisi kaldirildi.
  // Bu sure artik yalnizca sessiz reload'un (bellek sizintisi sigortasi)
  // gecikmesidir; sik reload attract davet metnini gereksiz yere kapatir.
  const DRV_RESET_PROMPT_AFTER_MS = 300000;
  // Test modu: oyun bitince bitiş mesajı okunup gösterilsin, sonra göz moduna dön.
  const DRV_TEST_END_LINGER_MS = 4000;

  function drvSend(payload) { return handleMessage(payload || {}); }

  async function drvFetchJson(url, body, timeoutMs) {
    const opts = { method: 'POST' };
    if (body) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    // Zaman aşımı ŞART: /api/game/input vb. sunucuda takılırsa yanıtsız fetch
    // thinking'i (mikrofon sert kapalı + bekle jesti) 45 sn güvenlik sayacına
    // dek açık bırakıyordu → "kum saati geldi, oyun kilitlendi" hissi. İptalde
    // çağıranın catch'i thinking'i kapatır, drvBusy finally ile açılır.
    const ctl = new AbortController();
    const tid = setTimeout(() => ctl.abort(), timeoutMs || 15000);
    opts.signal = ctl.signal;
    try {
      const r = await fetch(url, opts);
      return await r.json();
    } finally {
      clearTimeout(tid);
    }
  }

  function drvNoteActivity() {
    drvLastActivityAt = Date.now();
    if (drvCountdownId) { clearInterval(drvCountdownId); drvCountdownId = null; }
    drvAttractOn = false;
    drvEndSeq++;   // bekleyen oyun-sonu→göz geçişi varsa iptal: yeni etkileşim başladı
  }

  function drvIsGameTrigger(text) {
    const n = normChoice(text);
    if (n === 'oyun' || n === 'oyna' || n === 'oyun modu') return true;
    return /\boyun\s*oyna/.test(n);
  }

  // control.js selectedOptionKey portu: söylenen metni ekrandaki butonla eşle.
  function drvOptionKey(text, fallbackText) {
    const explicit = normChoice(text);
    for (const b of drvOptions) {
      const key = String((b && b.key) || '');
      if (explicit && explicit === normChoice(key)) return key;
    }
    const n = normChoice([text, fallbackText].filter(Boolean).join(' '));
    if (!n) return '';
    for (const b of drvOptions) {
      const key = String((b && b.key) || '');
      const label = normChoice([b && b.key, b && b.label].filter(Boolean).join(' '));
      if (n === normChoice(key) || label === n || label.includes(n) || n.includes(label)) {
        return key;
      }
    }
    return normChoice(text);
  }

  function drvPublishOptions(p) {
    const buttons = Array.isArray(p && p.buttons) ? p.buttons : [];
    drvOptions = buttons.slice();
    drvSend({
      type: 'game_options',
      visible: buttons.length > 0 || !!(p && p.hint),
      buttons: buttons,
      hint: (p && p.hint) || null,   // sesli yonlendirme balonu ("«Başla» de" vb.)
      phase: (p && p.phase) || null,
      game: (p && p.game) || null,
      kind: (p && p.kind) || null,
    });
  }
  function drvHomeOptions() {
    const opts = (testModeOn ? DRV_HOME_TEST : DRV_HOME).slice();
    drvOptions = opts;
    drvSend({
      type: 'game_options', visible: true, buttons: opts,
      hint: 'Söylemen yeterli',
      phase: 'idle', game: null, kind: 'home',
    });
  }

  // ——— Kelime/quiz geri sayım OTORİTESİ (panelsiz modda) ———
  function drvStartTimer(seconds, who) {
    drvStopTimer(false);
    drvTimer = { id: null, who: who, endsAt: Date.now() + seconds * 1000, seconds: seconds };
    drvSend({ type: 'timer_start', seconds: seconds, who: who });
    drvTimer.id = setInterval(() => {
      if (drvTimer.endsAt - Date.now() > 0) return;
      // Cevap YOLDAYSA "süre doldu" deme: süre içinde konuşulmuş ama STT/işleme
      // henüz bitmemiş cevap yanmasın (kilitlenme + haksız soru atlama şikâyeti).
      // Kapsam: kayıtta söz var / transkripsiyon sürüyor / sırada söz bekliyor /
      // sürücü işliyor. Tavan 30 sn (STT fetch 25 sn'de zaten iptal olur) —
      // asılı kalan bir istek sayacı sonsuza dek tutamasın.
      const answerInFlight = viBusyTranscribe || viPendingBlob
        || (viRec && viRec.state === 'recording' && viHadSpeech)
        || drvBusyActive();
      if (answerInFlight && Date.now() - drvTimer.endsAt < 30000) return;
      const wasUser = (drvTimer.who === 'user');
      drvStopTimer();
      if (wasUser) drvSubmitTimeout();
    }, 100);
  }
  function drvStopTimer(broadcast) {
    if (drvTimer.id) { clearInterval(drvTimer.id); drvTimer.id = null; }
    if (broadcast !== false) drvSend({ type: 'timer_stop' });
  }
  // Sunucu 409'unu (stale_input / game_active) ADOPT et: faz + tur jetonu + kapı
  // birlikte tazelenir. Jetonu almayı atlamak sessiz bir delik açıyordu — faz geri
  // yüklenip drvTurnId null kalınca sonraki cevap turn_id=null ile gidiyordu ve
  // sunucu (artık düzeltildi) onu doğrulamadan kabul edip yanlış soruyu tüketiyordu.
  function drvAdoptServerState(data) {
    if (!data) return;
    if (Number.isInteger(data.turn_id)) drvTurnId = data.turn_id;
    if (!data.phase) return;   // faz taşımayan hata: durum hakkında bilgi yok
    drvGamePhase = (data.phase !== 'idle') ? data.phase : null;
    // Kapıyı KAPALI bırakmayız: 409'dan sonra onu açacak yeni payload
    // GELMEYEBİLİR — kapalı kapı mikrofonu oyun boyunca sağır bırakır, ekran
    // 5 dk'lık sigortaya kadar ölü görünür. Açık kapı + sunucu jetonu birlikte
    // güvenli: yanlış soruyu tüketme riskini jeton zaten kesiyor.
    drvInputGateAt = drvGamePhase ? performance.now() : 0;
  }
  function drvRestoreInputAfterFailure(turnId, timer) {
    // İstek işlenmiş ama yanıt kaybolmuşsa aynı jetonlu tekrar sunucuda 409 olur;
    // işlenmemişse ziyaretçi aynı turu yeniden deneyebilir. Yalnız hâlâ aynı
    // turdaysak aç ki daha yeni payload'ın kapı/sayacını geri sarmayalım.
    if (drvTurnId !== turnId || !drvGamePhase || drvEndPending) return;
    drvInputGateAt = performance.now();
    if (timer && timer.seconds > 0 && timer.who) {
      drvStartTimer(timer.seconds, timer.who);
    }
  }
  async function drvSubmitTimeout() {
    drvInputGateAt = Infinity;
    const turnId = drvTurnId;
    const timerResume = (drvTimer.who === 'user' && drvTimer.seconds > 0)
      ? { who: drvTimer.who, seconds: drvTimer.seconds } : null;
    try {
      const data = await drvFetchJson('/api/game/input', { timeout: true, turn_id: turnId });
      if (data.error === 'stale_input') {
        // Bu istek beklerken daha yeni payload uygulandıysa onun açık kapısını
        // eski 409 ile kapatma; resenkron yalnız hâlâ istek turundaysak gerekir.
        if (drvTurnId === turnId) {
          // Faz + jeton + kapı birlikte tazelenir; ziyaretçinin sonraki sözü GÜNCEL
          // jetonla gider, sunucu işler, dönen payload istemciyi tam resenkronlar
          // (409 game_active'deki "kendiliğinden onarım" felsefesi).
          drvAdoptServerState(data);
          console.info('DRV: bayat timeout reddedildi — faz/jeton yeniden eşitlendi');
        }
        return;
      }
      if (data.error) {
        drvRestoreInputAfterFailure(turnId, timerResume);
        return;
      }
      await drvApplyPayload(data);
    } catch (e) {
      console.warn('DRV: timeout bildirilemedi', e);
      drvRestoreInputAfterFailure(turnId, timerResume);
    }
  }

  async function drvAiTurn() {
    try {
      const data = await drvFetchJson('/api/game/ai_turn');
      if (!data.error) await drvApplyPayload(data);
    } catch (e) { console.warn('DRV: AI turu alınamadı', e); }
  }

  // control.js applyGamePayload portu — render mesajları yerel handleMessage'a.
  async function drvApplyPayload(p) {
    if (!p) return;
    const applySeq = ++drvApplySeq;
    const payloadPhase = (p.phase && p.phase !== 'idle') ? p.phase : null;
    drvGamePhase = payloadPhase;
    if (Number.isInteger(p.turn_id)) drvTurnId = p.turn_id;
    const payloadTurnId = drvTurnId;
    // Yeni payload'ın sözü bitene kadar eski turun açık penceresi kullanılamaz.
    drvInputGateAt = drvGamePhase ? Infinity : 0;
    const isTimed = (p.game === 'kelime' || p.game === 'quiz');
    // Yeni sayaç TTS sonrasında başlayacak; o arada önceki turun sayacı ekranda
    // işlemeye ve gecikmiş timeout üretmeye devam etmesin.
    if (isTimed) drvStopTimer();
    // Kullanıcı metni typewriter'ı bitsin diye kısa tampon (panel ile aynı).
    let gap = (p.kind === 'round') ? 480
            : (p.game === 'kelime' && p.kind === 'ai_word') ? 320 : 260;
    // Bulanık kabul: cevap doğru sayıldıysa kullanıcı balonundaki ham STT metni
    // kabul edilen cevapla değiştirilir. gap yeniden yazmayı da kapsayacak kadar
    // uzar — yoksa ai_reply'ın daktilosu düzeltmeyi yarıda keser (tek activeTypewriter).
    if (p.user_display && normChoice(p.user_display) !== normChoice(drvSentUserText)) {
      drvSend({ type: 'user_text', text: p.user_display, speed: 14 });
      gap = Math.max(gap, p.user_display.length * 14 + 200);
    }
    await sleep(gap);
    const rep = drvSend({
      type: 'ai_reply',
      jest_id: p.jest_id,
      yanit: p.yanit || '',
      yogunluk: p.yogunluk,
      outcome: p.outcome || null,
      insist: !!p.insist,
    });
    if (p.score) drvSend({ type: 'game_score', score: p.score, active: true });
    drvPublishOptions(p);
    let endedToEyes = false;
    if (p.ended && !isTimed) {
      // Çıkış/terk_edildi: veda repliği okunsun, test modunda sonra göz moduna dön.
      drvGamePhase = null;
      drvInputGateAt = 0;
      drvSend({ type: 'game_exit' });
      endedToEyes = testModeOn;
    } else if (p.ended && testModeOn) {
      // Test modu: süreli oyun (quiz) bitti — bitiş mesajı okunsun, sonra göz moduna dön.
      drvGamePhase = null;
      drvInputGateAt = 0;
      setTimeout(() => { if (!drvGamePhase) drvSend({ type: 'game_exit' }); }, DRV_TEST_END_LINGER_MS);
      endedToEyes = true;
    }
    // Bitiş kararıyla birlikte ses girdisi kapatılır (typewriter/TTS daha
    // sürerken gelen gürültü bile selamı tetikleyemesin); göz geçişi bayrağı
    // kendi finally'sinde bırakır.
    if (endedToEyes) drvEndPending = true;
    try {
      await rep;
      // handleMessage içinde speak(), 180 ms'lik ilk await'ten sonra başlar;
      // bu yüzden idle kontrolü ancak rep daktilosu çözüldükten sonra güvenlidir.
      await whenSpeechDone();
      const stillCurrent = applySeq === drvApplySeq
        && drvGamePhase === payloadPhase
        && drvTurnId === payloadTurnId
        && !drvEndPending;
      if (!stillCurrent) return;
      // Menü/hazır/bitiş seçenekleri de ses girdisi bekler; yalnız AI kelime
      // turunda ziyaretçi penceresi açılmaz. Zaman tabanı viSpeechStartAt ile aynı.
      if (drvGamePhase && p.turn !== 'ai') drvInputGateAt = performance.now();
      else if (!drvGamePhase) drvInputGateAt = 0;
      if (isTimed && !p.ended && p.timer) {
        drvStartTimer(p.timer.seconds, p.timer.who);
      }
      // AI turu da önceki geri bildirimin sesi bittikten sonra ilerlesin.
      if (p.game === 'kelime' && !p.ended && p.turn === 'ai') drvAiTurn();
    } finally {
      // await ETME: drvHandleText'in busy kilidi açık kalsın istemiyoruz — geçiş
      // kendi içinde bitiş sesinin bitmesini bekler, yeni etkileşim onu iptal eder.
      if (endedToEyes) drvEndToAttract();
    }
  }

  // Test modunda oyun bitince (normal bitiş VEYA terk_edildi): bitiş mesajı sesli
  // okunup skor kısa süre ekranda kalsın, ardından 60 sn boşta sayacını BEKLEMEDEN
  // doğrudan gözlü bekleme (attract) ekranına geç. Oturum burada temizlenir;
  // sonraki ses anlık selam yoluyla YENİ ziyaretçi akışını (selam + menü) başlatır.
  // İKİ tetik: panelsiz sürücü (drvApplyPayload) VE panel ('end_to_eyes' mesajı).
  // Zamanlama her iki durumda da BURADA: TTS'in gerçekten ne zaman bittiğini
  // yalnız sergi sayfası bilir; panel yalnızca "oyun bitti" işaretini yollar.
  async function drvEndToAttract() {
    const seq = drvEndSeq;
    // Pencere boyunca ses girdisi işlenmez (viTranscribeAndSend + anlık selam
    // drvEndPending'e bakar): gözler görünmeden selam başlamasın.
    drvEndPending = true;
    try {
      const deadline = Date.now() + 60000;           // güvenlik tavanı
      let quiet = 0;  // ~900 ms kesintisiz sessizlik iste: TTS parça araları yanıltmasın
      while (Date.now() < deadline && quiet < 3) {   // bitiş replikleri bitsin
        await sleep(300);
        // Yeni etkileşim (panel operatörü vb.): hemen bırak ki finally bayrağı
        // temizlesin ve mikrofon uzun süre sağır kalmasın.
        if (seq !== drvEndSeq) return;
        quiet = (stSpeaking || stThinking || stTyping || drvBusyActive()) ? 0 : quiet + 1;
      }
      // Skor/veda okuma payı — iptal gelirse dilimler arasında hemen bırak.
      for (let beklenen = 0; beklenen < DRV_TEST_END_LINGER_MS; beklenen += 300) {
        await sleep(300);
        if (seq !== drvEndSeq) return;
      }
      // Bu arada yeni etkileşim başladıysa ya da durum değiştiyse sessizce vazgeç.
      if (seq !== drvEndSeq || drvGamePhase || drvBusyActive() || drvAttractOn
          || attractActive || !testModeOn) return;
      // Pencere içinde birikmiş (gürültü/yankı) kayıt varsa at: selamı ancak
      // gözler açıldıktan SONRA duyulan YENİ bir ses tetikleyebilir.
      if (viRec && viRec.state === 'recording') viStopRecorder('discard');
      drvAttractOn = true;
      drvOptions = [];
      drvStopTimer(false);
      drvSend({ type: 'session_reset' });
      drvFetchJson('/api/session/new', { reason: 'end_to_eyes' }).catch(() => {});  // backend: geçmiş + oyun temiz
      // Panel açıksa durumunu eşitle (boşta sayacı / oyun fazı geride kalmasın).
      if (bc && panelAlive()) bc.postMessage({ type: 'attract_sync' });
      drvSend({ type: 'attract_on' });
      drvLastActivityAt = Date.now();
    } finally {
      drvEndPending = false;
    }
  }

  async function drvStartGame(triggerText) {
    drvHomeOptions();
    drvSend({ type: 'game_option_select', key: 'oyun', text: triggerText || 'Oyun oynayalım' });
    drvSend({ type: 'user_text', text: triggerText || 'Oyun oynayalım' });
    drvSend({ type: 'thinking', on: true, jest: false });
    try {
      const data = await drvFetchJson('/api/game/start');
      if (data.error) {
        // 409 game_active: sunucu ortadaki oyunu korudu — faz VE tur jetonunu geri
        // yükle ki sonraki söz oyuna GEÇERLİ turla aksın (desync'ten kendiliğinden
        // çıkış). Jeton alınmazsa cevap turn_id=null ile gidiyor ve reddediliyordu.
        drvAdoptServerState(data);
        drvSend({ type: 'thinking', on: false });
        console.warn('DRV: oyun başlatılamadı (' + data.error + ')');
        return;
      }
      await drvApplyPayload(data);
    } catch (e) {
      console.warn('DRV: oyun başlatılamadı', e);
      drvSend({ type: 'thinking', on: false });
    }
  }

  async function drvGameInput(text, displayText) {
    drvInputGateAt = Infinity;
    const turnId = drvTurnId;
    drvSentUserText = displayText || text;
    drvSend({ type: 'game_option_select', key: drvOptionKey(text, displayText), text: drvSentUserText });
    drvSend({ type: 'user_text', text: drvSentUserText });
    drvSend({ type: 'thinking', on: true, jest: false });
    // Cevap gelince geri sayımı HEMEN durdur (yanlış "süre doldu" yarışını önle).
    const wasUserWordTurn = (drvGamePhase === 'kelime' && drvTimer.who === 'user' && !!drvTimer.id);
    const timerResume = drvTimer.id ? {
      who: drvTimer.who,
      seconds: Math.max(1, Math.ceil((drvTimer.endsAt - Date.now()) / 1000)),
    } : null;
    drvStopTimer();
    let thinkId = null;
    if (wasUserWordTurn) {
      thinkId = setTimeout(() => drvSend({ type: 'thinking', on: true, label: 'Hmm, bakıyorum…' }), 450);
    }
    try {
      const data = await drvFetchJson('/api/game/input', { text: text, turn_id: turnId });
      if (thinkId) { clearTimeout(thinkId); thinkId = null; }
      if (data.blocked) {
        // Yasaklı girdi motora hiç girmedi: tur/soru TÜKETİLMEDİ. Sayaç geri
        // yüklenir, yalnız "anlamadım" repliği okunur. (Sesli yolda bu noktaya
        // gelinmez — /api/transcribe metni zaten göndermez.)
        drvSend({ type: 'thinking', on: false });
        drvSend({
          type: 'ai_reply',
          jest_id: data.jest_id || 'anlamadim',
          yanit: data.yanit || 'Anlamadım, başka bir şey söyler misin?',
          yogunluk: data.yogunluk || 0.6,
        });
        drvRestoreInputAfterFailure(turnId, timerResume);
        return;
      }
      if (data.error) {
        if (data.error === 'stale_input') {
          // Daha yeni payload geldiyse eski 409'un faz/kapı durumunu geri sarmasına izin verme.
          if (drvTurnId === turnId) {
            drvAdoptServerState(data);
            console.info('DRV: bayat cevap reddedildi — faz/jeton yeniden eşitlendi');
          } else {
            return;
          }
        }
        drvSend({ type: 'thinking', on: false });
        if (data.error !== 'stale_input') drvRestoreInputAfterFailure(turnId, timerResume);
        return;
      }
      await drvApplyPayload(data);
    } catch (e) {
      if (thinkId) clearTimeout(thinkId);
      console.warn('DRV: oyun girdisi işlenemedi', e);
      drvSend({ type: 'thinking', on: false });
      drvRestoreInputAfterFailure(turnId, timerResume);
    }
  }

  // Test modu (panelsiz): ses duyulur duyulmaz, çeviri beklemeden selamla.
  // viMonitorTick tetikler; drvBusy eşzamanlı ikinci tetiği/çeviriyi keser.
  async function drvInstantGreet() {
    if (drvBusyActive()) return;
    drvBusy = true;
    drvBusyAt = Date.now();
    drvNoteActivity();
    noteInteraction();
    try {
      await drvNewSession('');
    } catch (e) {
      console.warn('DRV: anlık selam başarısız', e);
    } finally {
      drvBusy = false;
    }
  }

  async function drvNewSession(text) {
    // ÖNCE sunucuya sor, SONRA ekranı boz. /api/session/new aktif oyunu 409 ile
    // koruyabilir (örn. sayfa yenilendi, istemci oyunu unuttu ama sunucuda
    // yarışma sürüyor). Eski sıra ekranı silip ⏳ (bekle) jestini basıyor,
    // 409 gelince öylece bırakıyordu — sahada "kum saati + her seste yeniden
    // silinen ekran" takılması. Şimdi 409'da HİÇBİR görsel yıkım yok; sürücü
    // fazı sunucudan geri öğrenir (kendiliğinden onarım) ve sonraki söz
    // normal oyun girdisi olarak akar. session/new LLM'siz/hızlıdır — fetch'i
    // öne almak görünür gecikme yaratmaz.
    try {
      const data = await drvFetchJson('/api/session/new', { reason: 'greet' });
      if (data.error) {
        // Faz ile BİRLİKTE tur jetonu da geri yüklenir: ziyaretçi ortadaki oyuna
        // cevap vermeye devam edecek, jetonsuz gönderim ise reddedilir.
        drvAdoptServerState(data);
        console.warn('DRV: yeni oturum reddedildi (' + data.error + ') — faz geri yüklendi: '
          + (drvGamePhase || 'idle'));
        return;
      }
      drvGamePhase = null;
      drvStopTimer(false);
      drvSend({ type: 'session_reset' });
      if (text) drvSend({ type: 'user_text', text: text });
      if (data.phase === 'menu') {
        // Test modu: selamlama + oyun menüsü tek payload olarak gelir.
        await drvApplyPayload(data);
        return;
      }
      const rep = drvSend({
        type: 'ai_reply',
        jest_id: data.jest_id || 'selamlama',
        yanit: data.yanit || DRV_NEW_SESSION_REPLY,
        yogunluk: data.yogunluk || 0.8,
      });
      drvHomeOptions();
      await rep;
    } catch (e) {
      console.warn('DRV: yeni oturum açılamadı', e);
    }
  }

  // Ana giriş: sesle (viTranscribeAndSend) gelen metin — panelin
  // handleVoiceInput + handleSend yolunun birebir karşılığı.
  async function drvHandleText(text) {
    text = (text || '').trim();
    if (!text || drvBusyActive()) return;
    if (text.length > drvMaxChars) return;
    drvBusy = true;
    drvBusyAt = Date.now();
    drvNoteActivity();
    noteInteraction();
    try {
      // ——— TEST MODU: yalnizca oyun (sohbet yok). Bosta/goz modunda HERHANGI bir
      // ses selamlar + oyun menusunu acar; oyun/menu aktifken girdi secim/cevaptir.
      if (testModeOn) {
        if (drvGamePhase) await drvGameInput(text, null);
        else await drvNewSession(text);   // goz modundan: her ses en basa doner (selam+menu)
        return;
      }
      // OYUN AKTIFKEN her soz (selam dahil) OYUN GIRDISIDIR. Selamin "temiz
      // baslangic" acmasi yalniz bosta gecerli: oyun ortasinda ikinci bir
      // cocugun "merhaba"si (ya da STT'nin gurultuden selam uretmesi) surucuyu
      // greet'e sokuyor, sunucu 409 ile reddedince istemci fazi kaybediyordu
      // (sahadaki "kum saati + surekli yenilenen ekran" takilmasinin koku).
      // Kural: aktif oyunu yalniz oyun kurallari bitirir (2 cevapsiz zaman
      // asimi / buton) — backend /api/session/new korumasiyla ayni felsefe.
      if (drvGamePhase) {
        await drvGameInput(text, null);
        return;
      }
      if (DRV_GREETING_RE.test(normChoice(text))) {
        await drvNewSession(text);
        return;
      }
      if (drvIsGameTrigger(text)) {
        await drvStartGame(text);
        return;
      }
      // Serbest sohbet (yalnizca normal mod; test modu yukarida ele alindi)
      drvHomeOptions();
      drvSend({ type: 'game_option_select', key: 'sohbet', text: text });
      drvSend({ type: 'user_text', text: text });
      drvSend({ type: 'thinking', on: true });
      // LLM soğuk başlangıçta yavaş olabilir — sohbete geniş tavan (45 sn).
      const data = await drvFetchJson('/api/send', { text: text }, 45000);
      if (data.error) { drvSend({ type: 'thinking', on: false }); return; }
      await drvSend({
        type: 'ai_reply',
        jest_id: data.jest_id,
        yanit: data.yanit || '',
        yogunluk: data.yogunluk,
      });
    } catch (e) {
      console.warn('DRV: metin işlenemedi', e);
      drvSend({ type: 'thinking', on: false });
    } finally {
      drvBusy = false;
    }
  }

  // ——— Boşta/attract OTORİTESİ (panelsiz modda; control.js portu) ———
  // Süreli tur, aktif işleme veya süren konuşma kaydı boşta sayılmaz.
  // NOT: attract girişi oturumu aninda sıfırlar; görünür geri sayım yok
  // (attract_countdown mesajı panel/control.js yolunda hâlâ kullanılır).
  async function drvIdleReset() {
    if (drvCountdownId) { clearInterval(drvCountdownId); drvCountdownId = null; }
    drvAttractOn = false;
    drvLastActivityAt = Date.now();
    drvGamePhase = null;
    drvStopTimer(false);
    // Önce backend oturumu tazele, SONRA sayfayı yenile (istek yarım kalmasın).
    try { await drvFetchJson('/api/session/new', { reason: 'idle_reset' }); } catch (_) {}
    drvSend({ type: 'session_reset', reload: true });
  }
  setInterval(() => {
    if (panelAlive()) { drvLastActivityAt = Date.now(); return; }  // otorite panelde
    // BOŞTA sayılmayan durumlar: süren konuşma kaydı, soru zamanlayıcısı, aktif
    // işleme, AI KONUŞMASI/DÜŞÜNMESİ/YAZMASI ve süren transkripsiyon. Sayaç
    // yalnızca GERÇEK sessizlikte (ne ziyaretçiden ses ne AI'dan etkinlik) işler.
    const recording = !!(viRec && viRec.state === 'recording' && viHadSpeech);
    if (recording || drvTimer.id || drvBusyActive()
        || stSpeaking || stThinking || stTyping || viBusyTranscribe) {
      drvLastActivityAt = Date.now(); return;
    }
    if (drvCountdownId) return;   // geri sayım kendi zamanlayıcısında
    // OYUN AKTİFKEN (kurallar/hazır/soru — menü hariç) boşta sıfırlama 60 sn'de
    // DEĞİL, yalnızca 5 dk'lık mutlak sessizlik sigortasında devreye girer.
    // Oyun ortasında ayrılma tespiti oyun kuralının işi: art arda 2 soru cevapsız
    // zaman aşımına uğrarsa backend oyunu kapatır, bitiş akışı göz moduna döner.
    const drvInGame = !!(drvGamePhase && drvGamePhase !== 'menu');
    const attractAfterMs = drvInGame ? DRV_GAME_IDLE_FUSE_MS : DRV_ATTRACT_AFTER_MS;
    const idleMs = Date.now() - drvLastActivityAt;
    if (!drvAttractOn && idleMs >= attractAfterMs) {
      drvAttractOn = true;
      // Ziyaretci GITTI say: mesaj balonlarini/HUD'u temizle, oyun ve sohbet
      // durumunu sifirla — sonraki ses YENI ziyaretci gibi en bastan (selam +
      // menu) karsilanir. session_reset ayrica calan sesi de durdurur.
      drvGamePhase = null;
      drvOptions = [];
      drvStopTimer(false);
      drvSend({ type: 'session_reset' });
      drvFetchJson('/api/session/new', { reason: 'attract' }).catch(() => {});  // backend: gecmis + oyun temiz
      drvSend({ type: 'attract_on' });
    } else if (drvAttractOn && idleMs >= DRV_ATTRACT_AFTER_MS + DRV_RESET_PROMPT_AFTER_MS) {
      // Oturum attract girisinde temizlendi; bu nokta yalnizca bellek
      // sigortasidir — geri sayim gostermeden sessizce yenile.
      drvIdleReset();
    }
  }, 1000);

  // ——— Kontrol paneli ile haberlesme ———————————————————————
  // Panelden gelen ve "yeni etkileşim başladı" anlamı taşıyan mesaj tipleri:
  // bekleyen oyun-sonu→göz geçişini (drvEndToAttract) iptal ederler.
  const PANEL_INTERACTION = new Set([
    'user_text', 'thinking', 'ai_reply', 'game_option_select',
    'manual_gesture', 'timer_start',
  ]);
  function initChannel() {
    try {
      bc = new BroadcastChannel('aibody');
    } catch (e) {
      console.warn('BroadcastChannel desteklenmiyor', e);
      return;
    }
    bc.onmessage = (e) => {
      const d = e.data || {};
      // Panel canlılığı yalnız PANELİN gönderdiği mesajlarla ölçülür (panel 2 sn'de
      // bir 'ping' atar + gerçek kontrol mesajları). 'display_ready' bir SERGİ
      // EKRANI mesajıdır: açık unutulmuş ikinci bir sergi sekmesi panel sanılırsa
      // bu ekran otoriteyi ona devreder, ses girdisi boşluğa düşer (sağır kiosk).
      if (d.type !== 'display_ready') lastPanelMsgAt = Date.now();
      // Panelden gelen GERÇEK etkileşim, bekleyen oyun-sonu→göz geçişini iptal
      // eder (drvNoteActivity yalnız panelsiz yolda çağrılır; panel yolu burada).
      // 'game_exit'/'game_options' gibi bitiş-temizlik mesajları BİLEREK dışarıda:
      // panel oyun bitince +4 sn'de game_exit atar, geçişi iptal etmemeli.
      if (PANEL_INTERACTION.has(d.type)) drvEndSeq++;
      handleMessage(d);
    };
    bc.postMessage({ type: 'display_ready', mode: panel ? panel.mode : 'desen' });
    setInterval(() => bc.postMessage({
      type: 'display_ready', mode: panel ? panel.mode : 'desen',
    }), 4000);
  }

  // Panelden VEYA panelsiz sürücüden (drv*) gelen mesajların ORTAK işleyicisi.
  // Sürücü doğrudan çağırır; böylece render/TTS/rozet yolu iki modda da aynıdır.
  async function handleMessage(d) {
      // Herhangi bir gerçek etkileşim mesajı attract modunu anında kapatır.
      if (ATTRACT_CANCEL.has(d.type)) attractHide();
      if (d.type === 'ping') {
        bc.postMessage({ type: 'display_ready', mode: panel ? panel.mode : 'desen' });
      } else if (d.type === 'set_mode') {
        applyMode(d.mode);
      } else if (d.type === 'user_text') {
        // Ziyaretci mesaj yazdi — eye idle'i hemen kapat (jest sonra gelecek)
        noteInteraction();
        if (els.leftPlaceholder) els.leftPlaceholder.style.display = 'none';
        if (els.rightPlaceholder) els.rightPlaceholder.style.display = 'none';
        if (els.aiText) els.aiText.textContent = '';
        els.gestureBadge.classList.add('hidden');
        fitSpeechText(els.userText, d.text || '');  // uzun mesaj: kaydirma yerine kucult
        // speed: fuzzy düzeltme yeniden yazımı daha hızlı aksın diye geçilebilir
        await typeInto(els.userText, d.text || '', (typeof d.speed === 'number') ? d.speed : 26);
      } else if (d.type === 'ai_reply') {
        setThinking(false);                        // "Düşünüyorum…" göstergesini kapat
        if (d.jest_id) {
          triggerGesture(d.jest_id, { intensity: d.yogunluk });
        }
        // AI tur kazandıysa ekranı sarıya boğ (triggerGesture'dan SONRA override).
        if (d.outcome === 'ai_win') triggerWinFlash();
        // Kullanıcı metni typewriter'ı bitsin diye kısa tampon (Faz 3'te 350→180 ms).
        await sleep(180);
        if (els.rightPlaceholder) els.rightPlaceholder.style.display = 'none';
        if (d.yanit) {
          // Cevap balonu girişi: fade + translateY (yalnız transform/opacity)
          els.aiText.classList.remove('reply-in');
          void els.aiText.offsetWidth;
          els.aiText.classList.add('reply-in');
          speak(d.yanit, d.jest_id, d.yogunluk);   // sesi yaziyla paralel baslat
          fitSpeechText(els.aiText, d.yanit);      // uzun cevap: kaydirma yerine kucult
          await typeInto(els.aiText, d.yanit);     // hız: metin uzunluğuna adaptif
        }
        // AI "bir daha oynayalım" diye ısrar ediyorsa metni hafifçe nabızlat.
        if (d.insist && els.aiText) {
          els.aiText.classList.remove('insist');
          void els.aiText.offsetWidth;
          els.aiText.classList.add('insist');
          setTimeout(() => els.aiText.classList.remove('insist'), 2400);
        }
      } else if (d.type === 'manual_gesture') {
        if (els.leftPlaceholder) els.leftPlaceholder.style.display = 'none';
        if (d.jest_id) triggerGesture(d.jest_id);
      } else if (d.type === 'clear') {
        stopSpeech();            // ses kuyrugu da temizlensin
        setThinking(false);
        resetSpeechPanels();
        hideGameOptions();
      } else if (d.type === 'session_reset') {
        // Oturum sıfırlanırken bekleyen eski payload TTS sonrasında kapı/sayaç açmasın.
        drvGamePhase = null;
        drvTurnId = null;
        drvInputGateAt = 0;
        drvApplySeq++;
        stopSpeech();
        if (d.reload) {
          // Boşta-sıfırlama (attract zaman aşımı): sayfa oturum-tabanlı olduğundan
          // reload ziyaretçiye görünmez; bellek sızıntısı sigortasıdır.
          location.reload();
          return;
        }
        setThinking(false);
        updateGameHud(false, null);
        stopDisplayTimer();
        hideGameOptions();
        resetSpeechPanels();
      } else if (d.type === 'stop') {
        stopSpeech();            // calan ses + bekleyen parcalar iptal
        setThinking(false);
        const idle = gestureMap.has('huzur') ? 'huzur' : 'meditatif';
        if (gestureMap.has(idle)) triggerGesture(idle, { duration: 99999999 });
      } else if (d.type === 'thinking') {
        setThinking(d.on !== false, d.label, d.jest);
      } else if (d.type === 'listening') {
        stListening = (d.on !== false);
        if (stListening) noteInteraction();
        updateStateBadge();
      } else if (d.type === 'end_to_eyes') {
        // Panel (test modu): oyun bitti — bitiş mesajı TTS'i bitince göz moduna
        // geç (bekleme + iptal mantığı drvEndToAttract'ta; panelsiz yolla ortak).
        drvEndToAttract();
      } else if (d.type === 'attract_on') {
        attractShow();
      } else if (d.type === 'attract_off') {
        attractHide();
      } else if (d.type === 'attract_countdown') {
        attractCountdownTick(d.seconds);
      } else if (d.type === 'game_score') {
        updateGameHud(d.active, d.score);
      } else if (d.type === 'game_options') {
        renderGameOptions(d);
      } else if (d.type === 'game_option_select') {
        selectGameOption(d);
      } else if (d.type === 'timer_start') {
        startDisplayTimer(d.seconds, d.who);
      } else if (d.type === 'timer_stop') {
        stopDisplayTimer();
      } else if (d.type === 'stt_wait') {
        setSttWait(!!d.on);      // panel mikrofonu: STT sürerken "bekle" balonu
      } else if (d.type === 'game_exit') {
        setThinking(false);
        updateGameHud(false, null);
        stopDisplayTimer();
        hideGameOptions();
        if (els.userText) els.userText.textContent = '';
      } else if (d.type === 'test_mode') {
        setTestBadge(!!d.on);   // kontrol panelinden 'g' ile değişti
      } else if (d.type === 'immersive') {
        setImmersive(!!d.on);   // kontrol panelinden tam ekran göz modu
      }
  }

  async function loadEmojiManifest() {
    try {
      const r = await fetch('/api/emoji_manifest');
      const data = await r.json();
      if (panel) panel.setEmojiManifest(data.frames || {}, data.fps || 12, data.varyantlar || null);
    } catch (e) {
      console.warn('emoji manifest yuklenemedi:', e);
    }
  }

  // ——— Tam ekran (immersive) göz modu ————————————————————————————
  // Kontrol panelinden ('immersive' mesajı) ya da 'i' tuşuyla açılır. #stage'e
  // .immersive sınıfı eklenir (CSS: şeritler + yan yazı kutuları + çerçeve süsleri
  // gizlenir) ve LED göz panel.resize ile NET büyütülür; kapanınca normale döner.
  // Tercih localStorage'da tutulur (kontrol paneliyle paylaşımlı, reload'da korunur).
  function setImmersive(on) {
    on = !!on;
    immersiveOn = on;
    const stage = document.getElementById('stage');
    if (stage) stage.classList.toggle('immersive', on);
    if (panel) panel.resize(on ? LED_IMMERSIVE_SIZE : ledBaseSize);
    try { localStorage.setItem('aibody.immersive', on ? '1' : '0'); } catch (_) {}
  }

  // ——— Klavye kisayollari ——————————————————————————————————
  document.addEventListener('keydown', (e) => {
    if (e.repeat) return;   // tuş basılı tutulunca tekrar tetiklenmesin
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === 't' || e.key === 'T') {
      if (els.testPanel) els.testPanel.classList.toggle('open');
    }
    if (e.key === 'f' || e.key === 'F') {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
    if (e.key === 'd' || e.key === 'D') {
      viToggle();   // sürekli sesli giriş (dinleme) aç/kapa
    }
    if (e.key === 'm' || e.key === 'M') {
      viDebugToggle();   // mikrofon seviye göstergesi (canlı RMS/eşik)
    }
    if (e.key === 'k' || e.key === 'K') {
      // Ortam gürültüsünü YENİDEN ölç (salon doldu/boşaldı, mikrofon yeri değişti).
      // Kayıtlı ölçüm yok sayılır; 4 sn sessizlik gerekir.
      if (!VI.calibrationEnabled) viShowHint('Kalibrasyon config\'ten kapalı');
      else if (!viActive) viShowHint('Önce dinlemeyi açın (d)');
      else viCalibStart(true);
    }
    if (e.key === 'g' || e.key === 'G') {
      toggleTestModeFromDisplay();   // test modu: 2 oyun + sohbet kapalı
    }
    if (e.key === 's' || e.key === 'S') {
      ttsEnabled = !ttsEnabled;
      if (!ttsEnabled) stopSpeech();   // calan ses + kuyruk + bekleyen parcalar
      if (els.statusText) els.statusText.textContent = ttsEnabled ? 'BAGLI' : 'BAGLI · SES KAPALI';
    }
    if (e.key === 'i' || e.key === 'I' || e.key === 'ı' || e.key === 'İ') {
      setImmersive(!immersiveOn);   // tam ekran göz modu aç/kapa
    }
  });

  // ——— Init ————————————————————————————————————————————————
  async function loadGestures() {
    try {
      const r = await fetch('/api/gestures');
      const data = await r.json();
      gestures = data.jestler || [];
      gestureMap = new Map(gestures.map((g) => [g.id, g]));
    } catch (err) {
      console.error('Jest listesi yuklenemedi:', err);
      if (els.statusText) els.statusText.textContent = 'JEST LISTESI YOK';
    }
  }

  async function init() {
    const size = els.canvas && els.canvas.width ? els.canvas.width : 560;
    ledBaseSize = size;
    panel = new LEDPanel(els.canvas, { size });

    initStars();
    await loadGestures();
    await loadEmojiManifest();
    applyMode(loadStoredMode());
    // Kalıcı tam ekran (immersive) tercihi (localStorage; kontrol paneliyle paylaşımlı)
    try { if (localStorage.getItem('aibody.immersive') === '1') setImmersive(true); } catch (_) {}
    buildTestPanel();
    initChannel();
    checkTtsStatus();
    await loadVoiceInputConfig();
    await loadTestModeState();
    // Rozet/attract metinleri sunucu durumuyla senkron kalsın: açılış fetch'i
    // başarısız olsa ya da mod başka yerden değişse ~10 sn'de kendini onarır.
    setInterval(loadTestModeState, 10000);
    // Autoplay kilidini ilk etkilesimde ac (kiosk: gorevli bir kez tiklar/tusa basar)
    window.addEventListener('pointerdown', primeAudio, { once: true });
    window.addEventListener('keydown', primeAudio, { once: true });
    // Surekli sesli giris: sayfa acilir ACILMAZ dene — kiosk tarayicisi
    // (--use-fake-ui-for-media-stream) izni otomatik verir, normal tarayicida da
    // izin daha once "her zaman" verildiyse jest gerekmez. ILK denemede izin/
    // AudioContext/cihaz nedeniyle acilamazsa SESSIZCE PES ETMEZ: her etkilesimde
    // ve periyodik olarak acilana kadar tekrar dener (bu arada gorunur uyari
    // gosterir). 'd' ile elle ac/kapa (viWantOn ile döngü niyeti korunur).
    if (VI.enabled && VI.autostart) {
      viWantOn = true;
      const tryStartVI = () => { if (viWantOn && !viActive) viEnable(); };
      // Her dokunma/tus denemeyi tetikler (once DEGIL: ilk denemeler basarisiz
      // olsa da sonraki etkilesimler yeniden dener). Basarili olunca no-op.
      window.addEventListener('pointerdown', tryStartVI);
      window.addEventListener('keydown', tryStartVI);
      // Sekme öne gelince (arka plandayken askıya alınan) mikrofonu/AudioContext'i
      // hemen canlandır — test sırasında sergi sekmesi arkadaysa öne alınca düzelir.
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;
        if (viCtx && viCtx.state === 'suspended') viCtx.resume().catch(() => {});
        tryStartVI();
      });
      // Etkilesim olmasa bile (kiosk: kimse dokunmuyor) izin sonradan verilir
      // ya da cihaz serbest kalirsa kendiliginden yakalar.
      setInterval(tryStartVI, 3000);
      viEnable();
    }

    if (els.controls) els.controls.style.display = 'none';

    els.statusDot.classList.add('ok');
    els.statusText.textContent = 'BAGLI';

    const opener = gestureMap.has('huzur') ? 'huzur'
                : (gestureMap.has('meditatif') ? 'meditatif' : null);
    if (opener) {
      setTimeout(() => triggerGesture(opener), 200);
    }
    // Acilis sonrasi eye idle sayacini baslat (30 sn etkilesim yoksa gozler cikar)
    noteInteraction();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
