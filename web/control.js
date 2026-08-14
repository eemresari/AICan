// Kontrol Paneli — operator arayuzu
// Gercek backend (Python/Flask) + sergi ekrani (BroadcastChannel) ile konusur.

(function () {
  const HIZ = {
    cok_yavas: 0.45, yavas: 0.7, orta: 1.0, hizli: 1.4, cok_hizli: 1.9,
  };

  const $ = (q) => document.querySelector(q);

  const els = {
    canvas: $('#led-canvas'),                 // panelde LED canvas yok ama olabilir
    prompt: $('#prompt-input'),
    sendBtn: $('#send-btn'),
    stopBtn: $('#stop-btn'),
    aiResponse: $('#ai-response'),
    eventLog: $('#event-log'),
    activeGesture: $('#active-gesture'),
    modelSelect: $('#model-select'),
    newModelInput: $('#new-model-input'),
    activateBtn: $('#activate-model'),
    refreshBtn: $('#refresh-models'),
    downloadBtn: $('#download-model'),
    activeModel: $('#active-model'),
    activeNote: $('#active-note'),
    lastGesture: $('#last-gesture'),
    lastIntensity: $('#last-intensity'),
    lastDuration: $('#last-duration'),
    statThink: $('#stat-think'),
    statLoad: $('#stat-load'),
    statTokens: $('#stat-tokens'),
    statRate: $('#stat-rate'),
    gestureGrid: $('#gesture-grid'),
    connDot: $('#conn-dot'),
    connText: $('#conn-text'),
    clock: $('#clock'),
    modeToggle: $('#mode-toggle'),
    immersiveToggle: $('#immersive-toggle'),
    testToggle: $('#test-toggle'),
    micBtn: $('#mic-btn'),
    micStatus: $('#mic-status'),
    charCount: $('#char-count'),
    gameStartBtn: $('#game-start-btn'),
    gameButtons: $('#game-buttons'),
    gameScore: $('#game-score'),
    gameTheme: $('#game-theme'),
    wordTimer: $('#word-timer'),
  };

  let currentMode = 'desen'; // 'desen' | 'emoji'
  const NEW_SESSION_REPLY = 'Merhaba. Sohbet edebiliriz. Oyun için "oyun oynayalım" de.';
  const GREETING_RE = /\b(merhaba|merhabalar|selam|selamlar|gunaydin|naber)\b|\biyi (gunler|aksamlar)\b/;
  // Test modu: oyun bitince bitiş mesajı okunup gösterilsin, sonra göz moduna dön.
  const TEST_END_LINGER_MS = 4000;
  const HOME_OPTIONS = [
    { key: 'sohbet', label: 'Sohbet et' },
    { key: 'oyun', label: 'Oyun oynayalım' },
  ];
  const HOME_OPTIONS_TEST = [
    { key: 'oyun', label: 'Oyun oynayalım' },
  ];
  let displayOptionButtons = [];

  // ——— Test modu (sergi test günü) ———————————————————————————
  // 'g' tuşu / POST /api/test_mode: menüde yalnız Eş/Zıt + Atasözü, sohbet kapalı,
  // "merhaba" doğrudan oyun menüsü açar. Durum backend'de (config.json'da kalıcı).
  let testMode = false;
  let testBadgeEl = null;

  function ensureTestBadge() {
    if (testBadgeEl) return testBadgeEl;
    const div = document.createElement('div');
    div.id = 'test-mode-badge';
    div.style.cssText =
      'position:fixed;bottom:14px;right:14px;z-index:998;display:none;' +
      'padding:6px 12px;border-radius:8px;font-family:"JetBrains Mono",monospace;' +
      'font-size:12px;letter-spacing:1px;font-weight:700;color:#131022;' +
      'background:#ffd166;box-shadow:0 0 14px rgba(255,209,102,0.45);';
    div.textContent = 'TEST MODU · 2 OYUN · SOHBET KAPALI';
    document.body.appendChild(div);
    testBadgeEl = div;
    return div;
  }

  function applyTestMode(on, broadcast) {
    const changed = testMode !== !!on;
    testMode = !!on;
    ensureTestBadge().style.display = testMode ? 'block' : 'none';
    if (els.testToggle) {
      els.testToggle.textContent = 'TEST: ' + (testMode ? 'AÇIK' : 'KAPALI');
      els.testToggle.classList.toggle('on', testMode);
    }
    // Test modu: bas-konuş YOK — giriş yalnızca sergi ekranının sürekli
    // dinlemesiyle olur. KONUŞ butonunu ve "basılı tut" durum satırını gizle.
    // Normal modda bas-konuş fallback'i geri gelir.
    if (els.micBtn) els.micBtn.style.display = testMode ? 'none' : '';
    if (els.micStatus) els.micStatus.style.display = testMode ? 'none' : '';
    if (changed) {
      // Backend oyun durumunu sıfırladı — panelde eski butonlar kalmasın.
      gamePhase = null;
      hideGameUI();
      log('sys', 'test modu: ' + (testMode
        ? 'AÇIK (yalnız Eş/Zıt + Atasözü, sohbet kapalı)' : 'KAPALI'));
    }
    if (broadcast) sendToDisplay({ type: 'test_mode', on: testMode });
  }

  let testToggleBusy = false;
  async function toggleTestMode() {
    if (testToggleBusy) return;    // tuş basılı tutulursa istek seli olmasın
    testToggleBusy = true;
    noteActivity();
    try {
      // Kör toggle yerine hedef durumu gönder: tekrar/yarış durumlarında yakınsar.
      const r = await fetch('/api/test_mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ on: !testMode }),
      });
      const d = await r.json();
      applyTestMode(!!d.on, true);
    } catch (e) {
      log('sys', 'test modu değiştirilemedi: ' + e.message);
    } finally {
      testToggleBusy = false;
    }
  }

  // ——— Sergi koruma sınırları (backend'den /api/config ile gelir)
  let MAX_CHARS = 240;
  let MAX_RECORD_MS = 30000;

  // ——— Mikrofon (Whisper STT) durumu ————————————————————
  let micStream = null;
  let mediaRecorder = null;
  let recChunks = [];
  let recStartedAt = 0;
  let recAutoStopTimer = null;
  let whisperReady = false;
  let micEnabled = false;

  let panel;
  let bc;
  let gestures = [];
  let gestureMap = new Map();
  let lastDisplayPing = 0;

  // ——— Yardimcilar ————————————————————————————————————
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  function nowStamp() {
    const d = new Date();
    return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }
  function tickClock() { if (els.clock) els.clock.textContent = nowStamp(); }
  setInterval(tickClock, 1000); tickClock();

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
  function humanName(id) {
    if (!id) return '';
    return id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // ——— Olay log ————————————————————————————————————
  function log(type, msg, data) {
    if (!els.eventLog) return;
    const wrap = document.createElement('div');
    wrap.className = 'log-row log-' + type;
    const stamp = '<span class="log-stamp">' + nowStamp() + '</span>';
    const tag = '<span class="log-tag log-tag-' + type + '">[' + type + ']</span>';
    wrap.innerHTML = stamp + tag + '<span class="log-msg"></span>';
    wrap.querySelector('.log-msg').textContent = msg;
    if (data) {
      const detail = document.createElement('div');
      detail.className = 'log-detail';
      detail.textContent = data;
      wrap.appendChild(detail);
    }
    els.eventLog.appendChild(wrap);
    els.eventLog.scrollTop = els.eventLog.scrollHeight;
    while (els.eventLog.children.length > 200) els.eventLog.firstChild.remove();
  }

  // ——— Sergi ekrani kanali ——————————————————————————
  function initChannel() {
    try {
      bc = new BroadcastChannel('aibody');
      bc.onmessage = (e) => {
        const d = e.data || {};
        if (d.type === 'display_ready') {
          lastDisplayPing = Date.now();
          if (els.connDot && !els.connDot.classList.contains('ok')) {
            els.connDot.classList.add('ok');
            els.connText.textContent = 'SERGI EKRANI BAGLI';
            log('sys', 'sergi ekrani bagli');
          }
        } else if (d.type === 'voice_input') {
          handleVoiceInput(d.text || '');
        } else if (d.type === 'test_mode') {
          applyTestMode(!!d.on, false);   // sergi ekranından 'g' ile değişti
        } else if (d.type === 'attract_sync') {
          // Sergi oyun-sonunda göz (attract) moduna geçti; backend oturumunu da
          // orası sıfırladı. Panel durumu eşitlenir ki boşta sayacı/oyun fazı
          // geride kalmasın ve sonraki ses yeni ziyaretçi selamına gitsin.
          cancelResetCountdown();
          attractOn = true;
          lastActivityAt = Date.now();
          gamePhase = null;
          stopWordTimer();
          hideGameUI();
          if (els.prompt) { els.prompt.value = ''; updateCharCount(); }
          if (els.aiResponse) {
            els.aiResponse.textContent = 'yanıt bekleniyor';
            els.aiResponse.classList.add('empty');
          }
          log('sys', 'oyun bitti → göz modu (sergi bildirdi, oturum temiz)');
        }
      };
      bc.postMessage({ type: 'ping' });
      log('sys', 'kanal acildi (aibody)');
    } catch (e) {
      log('sys', 'BroadcastChannel desteklenmiyor');
    }
    // her 2 sn'de ping at; 6 sn cevapsiz kalirsa kopuk goster
    let testSyncTick = 0;
    setInterval(() => {
      if (!bc) return;
      bc.postMessage({ type: 'ping' });
      if (Date.now() - lastDisplayPing > 6000 && els.connDot && els.connDot.classList.contains('ok')) {
        els.connDot.classList.remove('ok');
        els.connText.textContent = 'SERGI EKRANI ARANIYOR';
        log('sys', 'sergi ekrani kopuk');
      }
      // Test modu durumunu ~10 sn'de bir sunucudan doğrula: harici POST/curl ya da
      // kaçırılmış broadcast kaynaklı senkron kaybını kendiliğinden onarır.
      if (++testSyncTick % 5 === 0) {
        fetch('/api/test_mode').then((r) => r.json()).then((d) => {
          if (d && typeof d.on === 'boolean' && d.on !== testMode) applyTestMode(d.on, true);
        }).catch(() => {});
      }
    }, 2000);
  }
  function sendToDisplay(payload) {
    if (bc) bc.postMessage(payload);
  }

  // Sergi ekranındaki sürekli mikrofondan sesle gelen prompt. Metni kutuya
  // yazıp handleSend()'e sokarız: selam algılama, oyun tetikleyici ve oyun
  // yönlendirmesi (submitGameInput) — hepsi yeniden kullanılır. voiceBusy
  // yanıt dönene kadar art arda tetiklemeyi engeller (ekran da stThinking'te
  // mikrofonu kapatır; çift koruma).
  let voiceBusy = false;
  async function handleVoiceInput(text) {
    text = (text || '').trim();
    if (!text || voiceBusy) return;
    voiceBusy = true;
    noteActivity();
    log('user', '🎤 ' + text);
    if (els.prompt) { els.prompt.value = text; updateCharCount(); }
    try {
      await handleSend();
    } catch (err) {
      log('sys', 'sesli giriş işlenemedi: ' + err.message);
    } finally {
      voiceBusy = false;
    }
  }

  // Sergiye "düşünüyorum" durumunu yayınla — gösterge ai_reply gelince temizlenir.
  // jest=false: yalnız metin göstergesi (hızlı yerel oyun yanıtlarında jest titremesin).
  function sendThinking(on, label, jest) {
    sendToDisplay({
      type: 'thinking',
      on: on !== false,
      label: label || null,
      jest: jest !== false,
    });
  }

  // ——— Attract / boşta modu + otomatik oturum sıfırlama ————————————
  // Zamanlayıcı OTORİTESİ burada (girdi bu panelden gelir). İki aşama:
  //  1) 60 sn etkileşimsiz -> attract_on (sergi dönüşümlü davet metinleri gösterir)
  //  2) +30 sn -> "Hâlâ orada mısın?" + 10 sn görünür geri sayım (iki ekranda)
  //     dokunulmazsa: session_reset(reload:true) + POST /api/session/new.
  // Aktif OYUN veya süren mikrofon kaydı sırasında zamanlayıcılar ÇALIŞMAZ.
  // Sergi tarafındaki 30sn göz-idle / 120sn uyku zamanlayıcılarına DOKUNMAZ;
  // attract onların üzerine biner (gözler sürer, uyku attract'tan sonra da çalışır).
  const ATTRACT_AFTER_MS = 60000;
  const RESET_PROMPT_AFTER_MS = 30000;
  const RESET_COUNTDOWN_S = 10;
  let lastActivityAt = Date.now();
  let attractOn = false;
  let resetCountdownId = null;
  let idleBannerEl = null;

  function noteActivity() {
    lastActivityAt = Date.now();
    const wasIdle = attractOn || !!resetCountdownId;
    cancelResetCountdown();
    attractOn = false;
    if (wasIdle) sendToDisplay({ type: 'attract_off' });
  }

  // Kontrol paneline "Hâlâ orada mısın?" bandını JS ile enjekte et
  // (Kontrol_Paneli.html'e dokunmadan; tema renkleriyle uyumlu).
  function ensureIdleBanner() {
    if (idleBannerEl) return idleBannerEl;
    const div = document.createElement('div');
    div.id = 'idle-reset-banner';
    div.style.cssText =
      'position:fixed;top:18px;left:50%;transform:translateX(-50%);z-index:999;' +
      'display:none;align-items:center;gap:14px;padding:12px 22px;' +
      'background:rgba(18,14,38,0.94);border:1px solid rgba(110,230,255,0.5);' +
      'border-radius:12px;font-family:"JetBrains Mono",monospace;font-size:14px;' +
      'color:#E8E8F0;box-shadow:0 0 24px rgba(110,230,255,0.25);backdrop-filter:blur(8px);';
    const span = document.createElement('span');
    span.innerHTML = 'Hâlâ orada mısın? Oturum <b id="idle-reset-num">' +
      RESET_COUNTDOWN_S + '</b> sn içinde sıfırlanacak.';
    const btn = document.createElement('button');
    btn.textContent = 'Buradayım';
    btn.style.cssText =
      'padding:6px 14px;background:rgba(110,230,255,0.14);' +
      'border:1px solid rgba(110,230,255,0.6);color:#E8E8F0;border-radius:8px;' +
      'cursor:pointer;font-family:inherit;font-size:13px;';
    btn.addEventListener('click', noteActivity);
    div.appendChild(span);
    div.appendChild(btn);
    document.body.appendChild(div);
    idleBannerEl = div;
    return div;
  }

  function startResetCountdown() {
    if (resetCountdownId) return;
    const banner = ensureIdleBanner();
    banner.style.display = 'flex';
    let left = RESET_COUNTDOWN_S;
    const paint = () => {
      const numEl = document.getElementById('idle-reset-num');
      if (numEl) numEl.textContent = String(left);
      sendToDisplay({ type: 'attract_countdown', seconds: left });
    };
    paint();
    log('sys', 'oturum sıfırlama geri sayımı (' + RESET_COUNTDOWN_S + ' sn)');
    resetCountdownId = setInterval(() => {
      left--;
      if (left <= 0) { performIdleReset(); return; }
      paint();
    }, 1000);
  }

  function cancelResetCountdown() {
    if (resetCountdownId) { clearInterval(resetCountdownId); resetCountdownId = null; }
    if (idleBannerEl) idleBannerEl.style.display = 'none';
  }

  // /api/session/new çağrısı — startNewVisitorSession ile ortak yardımcı.
  // reason session.log'a düşer; nedensiz çağrı "eski_istemci" (hayalet istemci
  // teşhis işareti) sayıldığından panel her zaman gerçek nedenini bildirir.
  async function postNewSession(reason) {
    const res = await fetch('/api/session/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || 'panel' }),
    });
    return res.json();
  }

  async function performIdleReset() {
    cancelResetCountdown();
    attractOn = false;
    lastActivityAt = Date.now();
    log('sys', 'etkileşimsizlik: oturum otomatik sıfırlanıyor');
    gamePhase = null;
    hideGameUI();
    if (els.prompt) { els.prompt.value = ''; updateCharCount(); }
    if (els.aiResponse) {
      els.aiResponse.textContent = 'yanıt bekleniyor';
      els.aiResponse.classList.add('empty');
    }
    // Sergi ekranı sayfayı yeniler (bellek sızıntısı sigortası; sayfa oturum-tabanlı).
    sendToDisplay({ type: 'session_reset', reload: true });
    try {
      const data = await postNewSession('idle_reset');
      if (data && data.error) log('sys', 'yeni oturum hatası: ' + data.error);
      else log('sys', 'yeni ziyaretçi oturumu hazır (otomatik)');
    } catch (e) {
      log('sys', 'yeni oturum ağ hatası: ' + e.message);
    }
  }

  setInterval(() => {
    // Yalnız SÜRELİ tur (geri sayım dönerken) veya mikrofon kaydı boşta sayılmaz.
    // Menü / hazır / bitiş ekranları boşta SAYILIR ki terk edilmiş kioskta
    // attract + otomatik oturum sıfırlama çalışsın (test modunda her etkileşim
    // bir oyun fazında bittiği için bu şart; eski 'gamePhase' koşulu kioskun
    // bayat menüde sonsuza dek donmasına yol açıyordu).
    const recording = mediaRecorder && mediaRecorder.state === 'recording';
    const timedTurn = !!wordTimer.id;
    if (timedTurn || recording) { lastActivityAt = Date.now(); return; }
    if (resetCountdownId) return;   // geri sayım kendi zamanlayıcısında ilerliyor
    const idleMs = Date.now() - lastActivityAt;
    if (!attractOn && idleMs >= ATTRACT_AFTER_MS) {
      attractOn = true;
      sendToDisplay({ type: 'attract_on' });
      log('sys', 'attract modu açıldı (' + (ATTRACT_AFTER_MS / 1000) + ' sn etkileşimsiz)');
    } else if (attractOn && idleMs >= ATTRACT_AFTER_MS + RESET_PROMPT_AFTER_MS) {
      startResetCountdown();
    }
  }, 1000);

  // ——— Jest tetikle (kontrol panelinde onizleme + sergiye yolla) ——
  // Varsayilan duration: Infinity — jest, yeni bir jest gelene kadar oynar.
  function triggerGesture(gestureId, opts = {}) {
    const g = gestureMap.get(gestureId);
    if (!g) {
      log('sys', 'bilinmeyen jest: ' + gestureId);
      return;
    }
    const primary = primaryFor(g);
    const secondary = secondaryFor(g);
    const speed = (opts.speed != null) ? opts.speed : speedFor(g);
    const intensity = (opts.intensity != null) ? opts.intensity
                    : (g.animasyon.yogunluk_varsayilan != null ? g.animasyon.yogunluk_varsayilan : 0.85);
    const duration = (opts.duration != null) ? opts.duration : Number.POSITIVE_INFINITY;
    const isEmoji = (g.gorsel_tipi === 'emoji');

    if (panel) {
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
        primary, secondary,
        speed: 0.6, intensity: 0.7,
        gestureId: null, isEmoji: false,
      });
    }

    if (els.activeGesture) {
      const rgb = 'rgb(' + primary.join(',') + ')';
      els.activeGesture.innerHTML =
        '<span class="dot" style="background:' + rgb + '; box-shadow: 0 0 12px ' + rgb + '"></span>' + humanName(g.id);
    }
    if (els.lastGesture) els.lastGesture.textContent = g.id;
    if (els.lastIntensity) els.lastIntensity.textContent = intensity.toFixed(2);
    if (els.lastDuration) {
      els.lastDuration.textContent = isFinite(duration) ? (duration / 1000).toFixed(1) + ' sn' : 'süresiz';
    }
  }

  // ——— Mod (emoji/desen) ————————————————————————————————
  function applyMode(mode, broadcast) {
    currentMode = (mode === 'emoji') ? 'emoji' : 'desen';
    if (panel) panel.setMode(currentMode);
    if (els.modeToggle) {
      els.modeToggle.textContent = 'GÖRSEL: ' + (currentMode === 'emoji' ? 'EMOJI' : 'DESEN');
      els.modeToggle.classList.toggle('emoji', currentMode === 'emoji');
    }
    try { localStorage.setItem('aibody.mode', currentMode); } catch (_) {}
    if (broadcast) {
      sendToDisplay({ type: 'set_mode', mode: currentMode });
      log('sys', 'görsel modu: ' + currentMode);
    }
  }
  function loadStoredMode() {
    try { return localStorage.getItem('aibody.mode') || 'desen'; } catch (_) { return 'desen'; }
  }
  function toggleMode() {
    applyMode(currentMode === 'emoji' ? 'desen' : 'emoji', true);
  }

  // ——— Tam ekran (immersive) göz modu — sergi ekranını yönetir ————
  // Açıkken sergi ekranında yalnız LED göz kalır (yazılar/çerçeveler gizli).
  // Tercih localStorage'da (sergi ekranıyla paylaşımlı); butonla ya da I tuşuyla.
  let immersive = false;
  function applyImmersive(on, broadcast) {
    immersive = !!on;
    if (els.immersiveToggle) {
      els.immersiveToggle.textContent = 'TAM EKRAN: ' + (immersive ? 'AÇIK' : 'KAPALI');
      els.immersiveToggle.classList.toggle('on', immersive);
    }
    try { localStorage.setItem('aibody.immersive', immersive ? '1' : '0'); } catch (_) {}
    if (broadcast) {
      sendToDisplay({ type: 'immersive', on: immersive });
      log('sys', 'tam ekran göz modu: ' + (immersive ? 'açık' : 'kapalı'));
    }
  }
  function loadStoredImmersive() {
    try { return localStorage.getItem('aibody.immersive') === '1'; } catch (_) { return false; }
  }
  function toggleImmersive() { applyImmersive(!immersive, true); }

  // ——— Mikrofon (bas-bırak) ————————————————————————————
  function setMicStatus(text, cls) {
    if (!els.micStatus) return;
    els.micStatus.textContent = text;
    els.micStatus.classList.remove('recording', 'busy', 'error', 'ok');
    if (cls) els.micStatus.classList.add(cls);
  }

  async function pollWhisperReady() {
    try {
      const r = await fetch('/api/transcribe/status');
      const d = await r.json();
      if (d.ready) {
        whisperReady = true;
        // micEnabled ilk basışa kadar false'tur — bu "erişim yok" demek DEĞİL
        // (izin ilk basışta istenir/kiosk'ta otomatiktir). Yanıltıcı kırmızı
        // "mikrofon erisimi yok" yerine hazır mesajı göster; gerçek ret zaten
        // ensureMicStream'de "mikrofon reddedildi / yok" olarak raporlanır.
        setMicStatus('mikrofon hazır — basılı tut, konuş', 'ok');
        log('sys', 'whisper modeli hazır (' + d.model + ')');
        return true;
      }
      if (d.status === 'hata') {
        setMicStatus('model hatası: ' + (d.detail || '').slice(0, 60), 'error');
        if (els.micBtn) els.micBtn.disabled = true;
        return true; // poll'u kes
      }
      setMicStatus('model yükleniyor...', 'busy');
      return false;
    } catch (e) {
      setMicStatus('whisper durumu alınamadı', 'error');
      return false;
    }
  }

  async function initMic() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia
        || typeof MediaRecorder === 'undefined') {
      setMicStatus('tarayıcı mikrofon API desteklemiyor', 'error');
      if (els.micBtn) els.micBtn.disabled = true;
      return;
    }
    if (els.micBtn) els.micBtn.disabled = true;
    setMicStatus('whisper modeli yükleniyor...', 'busy');

    // Whisper hazir olana kadar yokla (her 2 sn)
    const tick = async () => {
      const done = await pollWhisperReady();
      if (!done) setTimeout(tick, 2000);
    };
    tick();

    // Mikrofon izni butona ilk basısta istenecek (kullanıcı jestiyle).
    // Burada sadece dinleyicileri kur.
    if (!els.micBtn) return;
    els.micBtn.addEventListener('pointerdown', onMicDown);
    els.micBtn.addEventListener('pointerup', onMicUp);
    els.micBtn.addEventListener('pointerleave', onMicUp);
    els.micBtn.addEventListener('pointercancel', onMicUp);
    // Sağ tık veya context menu kaydı bozmasın
    els.micBtn.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  async function ensureMicStream() {
    if (micStream && micStream.active) return micStream;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      micEnabled = true;
      return micStream;
    } catch (e) {
      micEnabled = false;
      setMicStatus('mikrofon reddedildi / yok', 'error');
      log('sys', 'mikrofon erisimi alınamadı: ' + e.name);
      if (els.micBtn) els.micBtn.disabled = true;
      return null;
    }
  }

  async function onMicDown(e) {
    e.preventDefault();
    if (!whisperReady) {
      setMicStatus('model hazır değil', 'busy');
      return;
    }
    if (mediaRecorder && mediaRecorder.state === 'recording') return;
    const stream = await ensureMicStream();
    if (!stream) return;

    // Tarayıcı destekli en iyi opus mime tipini seç
    let mime = '';
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
    for (const m of candidates) {
      if (MediaRecorder.isTypeSupported(m)) { mime = m; break; }
    }
    try {
      mediaRecorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
    } catch (err) {
      setMicStatus('kayıt başlatılamadı', 'error');
      log('sys', 'MediaRecorder hata: ' + err.message);
      return;
    }
    recChunks = [];
    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) recChunks.push(ev.data);
    };
    mediaRecorder.onstop = onRecStop;
    mediaRecorder.start();
    recStartedAt = performance.now();
    noteActivity();
    sendToDisplay({ type: 'listening', on: true });   // sergi: "Dinliyorum…" rozeti
    setMicStatus('dinliyorum... (bırakınca durur, max ' + (MAX_RECORD_MS / 1000) + ' sn)', 'recording');
    if (els.micBtn) els.micBtn.classList.add('recording');
    // Sergi koruma: kayit MAX_RECORD_MS uzerine cikmasin (uzun ses Whisper'i kilitler)
    if (recAutoStopTimer) clearTimeout(recAutoStopTimer);
    recAutoStopTimer = setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        log('sys', 'kayit ' + (MAX_RECORD_MS / 1000) + ' sn sinirinda otomatik durduruldu');
        try { mediaRecorder.stop(); } catch (_) {}
        if (els.micBtn) els.micBtn.classList.remove('recording');
        sendToDisplay({ type: 'listening', on: false });
      }
    }, MAX_RECORD_MS);
  }

  function onMicUp(e) {
    if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
    e && e.preventDefault && e.preventDefault();
    if (recAutoStopTimer) { clearTimeout(recAutoStopTimer); recAutoStopTimer = null; }
    try { mediaRecorder.stop(); } catch (_) {}
    if (els.micBtn) els.micBtn.classList.remove('recording');
    sendToDisplay({ type: 'listening', on: false });
  }

  async function onRecStop() {
    sendToDisplay({ type: 'listening', on: false });  // güvence (idempotent)
    const dur = (performance.now() - recStartedAt) / 1000;
    if (recChunks.length === 0 || dur < 0.3) {
      setMicStatus('çok kısa — tekrar dene', 'error');
      return;
    }
    const mime = (mediaRecorder && mediaRecorder.mimeType) || 'audio/webm';
    const blob = new Blob(recChunks, { type: mime });
    setMicStatus('çevriliyor... (' + dur.toFixed(1) + ' sn)', 'busy');
    sendToDisplay({ type: 'stt_wait', on: true });   // sergi: "bekle" balonu
    const fd = new FormData();
    fd.append('audio', blob, 'rec.webm');
    try {
      const r = await fetch('/api/transcribe', { method: 'POST', body: fd });
      const data = await r.json();
      if (data.error) {
        setMicStatus('hata: ' + data.error, 'error');
        log('sys', 'transkripsiyon hatasi: ' + data.error);
        return;
      }
      const txt = (data.text || '').trim();
      if (data.warning === 'blocked') {
        // Yasaklı söz: metin sunucudan hiç gelmedi. Kutuya yazılmaz, sergiye
        // yalnız "anlamadım" repliği gider (uyarı/sansür mesajı YOK).
        setMicStatus('anlaşılmadı — tekrar dene', 'error');
        log('sys', 'yasaklı girdi engellendi (ekrana yazılmadı)');
        sendToDisplay({
          type: 'ai_reply',
          jest_id: data.jest_id || 'anlamadim',
          yanit: data.yanit || 'Anlamadım, başka bir şey söyler misin?',
          yogunluk: data.yogunluk || 0.6,
        });
        return;
      }
      if (!txt) {
        setMicStatus('anlaşılmadı — tekrar dene', 'error');
        return;
      }
      // Mevcut metnin sonuna ekle (varsa) veya kutuyu doldur — MAX_CHARS sin
      if (els.prompt) {
        const cur = (els.prompt.value || '').trim();
        let combined = cur ? (cur + ' ' + txt) : txt;
        if (combined.length > MAX_CHARS) {
          combined = combined.slice(0, MAX_CHARS);
        }
        els.prompt.value = combined;
        els.prompt.focus();
        updateCharCount();
      }
      const langProb = data.meta && data.meta.language_prob;
      const truncNote = data.truncated ? ' (kırpıldı)' : '';
      setMicStatus(
        'çevrildi' + truncNote + ' (' + (langProb ? Math.round(langProb * 100) + '%) tr' : 'tr') + ' — enter ile gönder',
        data.truncated ? 'busy' : 'ok'
      );
      log('sys', 'STT' + truncNote + ': ' + txt);
    } catch (e) {
      setMicStatus('ag hatasi: ' + e.message, 'error');
    } finally {
      sendToDisplay({ type: 'stt_wait', on: false });
    }
  }

  async function loadEmojiManifest() {
    try {
      const r = await fetch('/api/emoji_manifest');
      const data = await r.json();
      if (panel) panel.setEmojiManifest(data.frames || {}, data.fps || 12, data.varyantlar || null);
    } catch (e) {
      log('sys', 'emoji manifest yuklenemedi: ' + e.message);
    }
  }

  // ——— Karakter sayacı ————————————————————————————————
  function updateCharCount() {
    if (!els.charCount || !els.prompt) return;
    const n = (els.prompt.value || '').length;
    els.charCount.textContent = n + ' / ' + MAX_CHARS;
    els.charCount.classList.toggle('warn', n > MAX_CHARS * 0.8 && n < MAX_CHARS);
    els.charCount.classList.toggle('full', n >= MAX_CHARS);
  }

  async function loadServerConfig() {
    try {
      const r = await fetch('/api/config');
      const d = await r.json();
      if (d.max_user_input_chars) {
        MAX_CHARS = d.max_user_input_chars;
        if (els.prompt) els.prompt.maxLength = MAX_CHARS;
      }
      if (d.max_record_seconds) MAX_RECORD_MS = d.max_record_seconds * 1000;
      if (typeof d.test_mode === 'boolean') applyTestMode(d.test_mode, true);
      updateCharCount();
    } catch (_) { /* varsayilanlar kalir */ }
  }

  function isNewSessionGreeting(text) {
    return GREETING_RE.test(normalizeTr(text));
  }

  async function startNewVisitorSession(text) {
    log('user', '> ' + text);
    els.prompt.value = '';
    updateCharCount();
    if (els.sendBtn) els.sendBtn.disabled = true;

    try {
      // ÖNCE sunucuya sor, SONRA ekranı sıfırla: /api/session/new aktif oyunu
      // 409 ile koruyabilir — eski sıra ekranı silip ⏳ (bekle) jestini basıyor,
      // ret gelince öylece bırakıyordu. 409'da görsel yıkım yok; faz sunucudan
      // geri yüklenir, sonraki girdi oyuna akar.
      const data = await postNewSession('greet');
      if (data.error) {
        adoptServerGameState(data);   // faz + tur jetonu birlikte geri yüklenir
        log('sys', 'yeni oturum reddedildi: ' + data.error
          + (data.phase ? ' (faz: ' + data.phase + ')' : ''));
        return;
      }
      if (els.statThink) els.statThink.textContent = '0.00 sn';
      if (els.statTokens) els.statTokens.textContent = '0 → 0';
      if (els.statRate) els.statRate.textContent = '— tok/s';
      if (els.statLoad) els.statLoad.textContent = '0.0 sn';
      gamePhase = null;
      stopWordTimer();
      hideGameUI();
      sendToDisplay({ type: 'session_reset' });
      sendToDisplay({ type: 'user_text', text });
      if (data.phase === 'menu') {
        // Test modu: selamlama + oyun menüsü tek payload olarak gelir.
        log('sys', 'yeni ziyaretçi oturumu (test modu: selamlama + oyun menüsü)');
        await applyGamePayload(data);
        return;
      }
      const yanit = data.yanit || NEW_SESSION_REPLY;
      log('sys', 'yeni ziyaretçi oturumu açıldı');
      log('jest', data.jest_id + ' yog=' + (data.yogunluk || 0.8).toFixed(2));
      log('yanit', "'" + yanit + "'");
      sendToDisplay({
        type: 'ai_reply',
        jest_id: data.jest_id || 'selamlama',
        yanit: yanit,
        yogunluk: data.yogunluk || 0.8,
      });
      publishHomeOptions();
      triggerGesture(data.jest_id || 'selamlama', { intensity: data.yogunluk || 0.8 });
      if (els.aiResponse) {
        els.aiResponse.textContent = yanit;
        els.aiResponse.classList.remove('empty');
      }
    } catch (e) {
      log('sys', 'yeni oturum ağ hatası: ' + e.message);
    } finally {
      if (els.sendBtn) els.sendBtn.disabled = false;
      els.prompt.focus();
    }
  }

  // ——— Gercek backend cagirisi ——————————————————————
  // Yasaklı kelime filtresi (sunucu tek kaynak): söz sergi ekranına YAZILMADAN
  // önce sorulur. Ağ hatasında engellemez — sunucu tarafı /api/send ve
  // /api/game/input'ta zaten ikinci kapıdır.
  async function filterCheck(text) {
    try {
      const r = await fetch('/api/filter_check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      return await r.json();
    } catch (_) {
      return null;
    }
  }

  async function handleSend() {
    const text = (els.prompt.value || '').trim();
    if (!text) return;
    noteActivity();
    if (text.length > MAX_CHARS) {
      log('sys', 'iptal: prompt ' + text.length + ' / ' + MAX_CHARS + ' karakter sınırını aşıyor');
      return;
    }

    // Yasaklı girdi: sergiye ne metin ne uyarı gider — yalnız "anlamadım".
    // (Sesli yolda /api/transcribe zaten keser; burası panel/yazı kapısı.)
    const flt = await filterCheck(text);
    if (flt && flt.blocked) {
      els.prompt.value = '';
      updateCharCount();
      log('sys', 'yasaklı girdi engellendi (ekrana yazılmadı)');
      sendToDisplay({
        type: 'ai_reply',
        jest_id: flt.jest_id || 'anlamadim',
        yanit: flt.yanit || 'Anlamadım, başka bir şey söyler misin?',
        yogunluk: flt.yogunluk || 0.6,
      });
      if (els.aiResponse) {
        els.aiResponse.textContent = flt.yanit || '';
        els.aiResponse.classList.remove('empty');
      }
      els.prompt.focus();
      return;
    }

    // ——— TEST MODU: yalnızca oyun (sohbet yok). Boşta/göz modunda HERHANGİ bir
    // girdi selamlar + oyun menüsünü açar; oyun/menü aktifken girdi seçim/cevaptır.
    if (testMode) {
      if (gamePhase) {
        log('user', '> ' + text);
        els.prompt.value = '';
        updateCharCount();
        await submitGameInput(text, null);
        els.prompt.focus();
      } else {
        await startNewVisitorSession(text);   // göz modundan: her girdi en başa (selam+menü)
      }
      return;
    }

    // ——— Oyun modu yönlendirmesi ———
    // OYUN AKTİFKEN her girdi (selam dahil) OYUNA gider. Selamın "temiz
    // başlangıç" açması yalnız boşta geçerli: oyun ortasında duyulan "merhaba"
    // (ikinci çocuk / STT gürültüsü) aktif yarışmayı bırakıp greet'e gidiyor,
    // backend 409 ile koruyunca panel fazı kaybediyordu (kum saati döngüsü).
    if (gamePhase) {
      log('user', '> ' + text);
      els.prompt.value = '';
      updateCharCount();
      await submitGameInput(text, null);
      els.prompt.focus();
      return;
    }

    // Yeni ziyaretçi selamı (yalnız boşta): temiz başlangıç açar.
    if (isNewSessionGreeting(text)) {
      await startNewVisitorSession(text);
      return;
    }

    // "OYUN OYNAYALIM" hazır komutu oyunu başlatır.
    if (isGameTrigger(text)) {
      log('user', '> ' + text);
      els.prompt.value = '';
      updateCharCount();
      await startGame(text);
      els.prompt.focus();
      return;
    }

    log('user', '> ' + text);
    els.prompt.value = '';
    updateCharCount();
    els.sendBtn.disabled = true;
    if (els.statThink) els.statThink.textContent = 'dusunuyor...';

    publishHomeOptions();
    selectDisplayOption('sohbet', text);

    // sergiye soruyu yansit (typewriter) + hemen "düşünüyorum" göstergesi
    // (girdiden <400ms içinde görsel tepki: bekle jesti + nabızlanan rozet)
    sendToDisplay({ type: 'user_text', text });
    sendThinking(true);

    log('llm', 'prompt baslatildi', 'model: ' + (els.activeModel.textContent || '-'));

    try {
      const res = await fetch('/api/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (data.error) {
        let msg = data.error;
        if (data.error === 'too_long') {
          msg = 'metin çok uzun (' + data.len + ' > ' + data.max + ' karakter)';
        }
        log('sys', 'HATA: ' + msg);
        sendThinking(false);
        if (els.statThink) els.statThink.textContent = '— sn';
        if (els.aiResponse) {
          els.aiResponse.textContent = 'Hata: ' + msg;
          els.aiResponse.classList.remove('empty');
        }
        return;
      }

      const meta = data.meta || {};
      const wall = meta.wall_s || 0;
      const promptTok = meta.prompt_tokens || 0;
      const evalTok = meta.eval_tokens || 0;
      const rate = meta.tok_per_s || 0;
      const loadMs = meta.load_ms || 0;

      log('llm', 'prompt ' + wall.toFixed(2) + 's  yanit ' + evalTok + 'tok @ ' + rate.toFixed(1) + ' tok/s');
      log('jest', data.jest_id + ' yog=' + (data.yogunluk || 0).toFixed(2));
      if (meta.mirror_override) log('sys', 'mirror override uygulandi');
      if (meta.sanitized) log('sys', 'yanit metni sanitize edildi');
      if (meta.fallback_used) log('sys', 'fallback jest kullanildi');
      log('yanit', "'" + (data.yanit || '') + "'");

      if (els.statThink) els.statThink.textContent = wall.toFixed(2) + ' sn';
      if (els.statTokens) els.statTokens.textContent = promptTok + ' → ' + evalTok;
      if (els.statRate) els.statRate.textContent = rate.toFixed(1) + ' tok/s';
      if (els.statLoad) els.statLoad.textContent = (loadMs / 1000).toFixed(1) + ' sn';

      // sergiye yaniti yolla
      sendToDisplay({
        type: 'ai_reply',
        jest_id: data.jest_id,
        yanit: data.yanit || '',
        yogunluk: data.yogunluk,
      });
      // kontrol panelinde onizle
      triggerGesture(data.jest_id, { intensity: data.yogunluk });
      if (els.aiResponse) {
        els.aiResponse.textContent = data.yanit || '';
        els.aiResponse.classList.remove('empty');
      }
    } catch (err) {
      log('sys', 'ag hatasi: ' + err.message);
      sendThinking(false);
      if (els.statThink) els.statThink.textContent = '— sn';
    } finally {
      els.sendBtn.disabled = false;
      els.prompt.focus();
    }
  }

  function handleStop() {
    noteActivity();
    if (gamePhase) {
      // Oyundayken DURDUR -> oyundan çık (sohbet moduna dön)
      gamePhase = null;
      stopWordTimer();
      fetch('/api/game/exit', { method: 'POST' }).catch(() => {});
      sendToDisplay({ type: 'game_exit' });
      hideGameUI();
    }
    sendToDisplay({ type: 'stop' });
    const idle = gestureMap.has('huzur') ? 'huzur'
              : (gestureMap.has('meditatif') ? 'meditatif' : null);
    if (idle) triggerGesture(idle, { duration: 99999999 });
    log('sys', 'durduruldu');
  }

  // ——— Oyun modu —————————————————————————————————————————
  // Oyun mantığı backend'de (game_engine.py). Burası ince yönlendirici:
  // hazır komutu yakalar, /api/game/* çağırır, sergiye yansıtır, dokunmatik buton render eder.
  let gamePhase = null; // null | 'menu' | 'rps'
  // Son uygulanan payload'ın jetonu, panel girdisinin hangi tura ait olduğunu kanıtlar.
  let gameTurnId = null;
  // 409 (game_active / stale_input) sonrası sunucu durumunu adopt et. Jetonu almayı
  // atlamak sessiz bir delik açıyordu: faz geri yüklenip gameTurnId null kalınca
  // sonraki girdi turn_id=null ile gidiyor, sunucu da (eskiden) onu doğrulamadan
  // kabul edip yanlış soruyu tüketiyordu.
  function adoptServerGameState(data) {
    if (!data) return;
    if (Number.isInteger(data.turn_id)) gameTurnId = data.turn_id;
    if (data.phase) gamePhase = (data.phase !== 'idle') ? data.phase : null;
  }
  let sentUserText = ''; // sergi balonuna son yazılan kullanıcı girdisi (fuzzy düzeltme kıyası)

  function normalizeTr(s) {
    s = (s || '')
      .replace(/[İI]/g, 'i').replace(/Ç/g, 'c').replace(/Ğ/g, 'g')
      .replace(/Ö/g, 'o').replace(/Ş/g, 's').replace(/Ü/g, 'u')
      .toLowerCase()
      .replace(/[çğıöşü âîû]/g, (c) => (
        { 'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'â': 'a', 'î': 'i', 'û': 'u', ' ': ' ' }[c] || c
      ));
    return s.replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim();
  }
  function isGameTrigger(text) {
    const n = normalizeTr(text);
    if (n === 'oyun' || n === 'oyna' || n === 'oyun modu') return true;
    return /\boyun\s*oyna/.test(n);
  }

  async function startGame(triggerText) {
    noteActivity();
    publishHomeOptions();
    selectDisplayOption('oyun', triggerText || 'Oyun oynayalım');
    sendToDisplay({ type: 'user_text', text: triggerText || 'Oyun oynayalım' });
    sendThinking(true, null, false);   // hızlı yerel yanıt: jestsiz, yalnız gösterge
    log('sys', 'oyun modu başlatılıyor');
    try {
      const r = await fetch('/api/game/start', { method: 'POST' });
      const data = await r.json();
      if (data.error) {
        // 409 game_active: backend ortadaki oyunu korudu — faz + jetonu geri yükle.
        adoptServerGameState(data);
        sendThinking(false);
        log('sys', 'oyun başlatılamadı: ' + data.error
          + (data.phase ? ' (faz: ' + data.phase + ')' : ''));
        return;
      }
      await applyGamePayload(data);
    } catch (e) {
      sendThinking(false);
      log('sys', 'oyun başlatılamadı: ' + e.message);
    }
  }

  // Kelime doğrulaması/AI beklerken sergiye ara geri bildirim.
  // Genel 'thinking' mekanizmasını özel etiketle kullanır (bekle jesti + gösterge);
  // eski sahte ai_reply yolu kaldırıldı (TTS'e gitmesin, sadece görsel dursun).
  function showThinking(msg) {
    sendThinking(true, msg, true);
    if (gestureMap.has('bekle')) triggerGesture('bekle', { intensity: 0.6 });
    if (els.aiResponse) {
      els.aiResponse.textContent = msg;
      els.aiResponse.classList.remove('empty');
    }
  }

  async function submitGameInput(text, displayText, isButton) {
    noteActivity();
    selectDisplayOption(text, displayText || text);
    sentUserText = displayText || text;
    sendToDisplay({ type: 'user_text', text: sentUserText });
    sendThinking(true, null, false);   // anında görsel tepki (jestsiz)
    // Kullanıcı cevap verince geri sayımı HEMEN durdur: yanlış "süre doldu" tetiklenmesini
    // ve istek-yarışını önler (doğrulama LLM'e giderse sayaç dönmeye devam etmemeli).
    const wasUserWordTurn = (gamePhase === 'kelime' && wordTimer.who === 'user' && !!wordTimer.id);
    stopWordTimer();
    // Doğrulama yerel sözlükte yoksa LLM'e gidebilir; >450ms sürerse ekranda
    // "bakıyorum" + bekle jesti göster (ziyaretçi ekranı donmuş sanmasın).
    let thinkTimer = null;
    if (wasUserWordTurn) {
      thinkTimer = setTimeout(() => showThinking('Hmm, bakıyorum…'), 450);
    }
    const turnId = gameTurnId;
    try {
      const r = await fetch('/api/game/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // button: panel butonu sesli girdiden ayrilir — backend cikis komutlarini
        // aktif quiz'de yalnizca butondan kabul eder (STT gurultu korumasi).
        body: JSON.stringify({ text: text, button: !!isButton, turn_id: turnId }),
      });
      const data = await r.json();
      if (thinkTimer) { clearTimeout(thinkTimer); thinkTimer = null; }
      if (data.error) {
        // Bayat panel isteği oyunu ilerletmez; sonraki girdi güncel faz/jetonla gider.
        // Arada daha yeni payload geldiyse eski 409 onun jetonunu geri sarmamalı.
        if (data.error === 'stale_input' && gameTurnId === turnId) {
          adoptServerGameState(data);
        } else if (data.error === 'stale_input') {
          return;
        }
        sendThinking(false);
        log('sys', 'oyun hatası: ' + data.error);
        return;
      }
      await applyGamePayload(data);
    } catch (e) {
      if (thinkTimer) { clearTimeout(thinkTimer); thinkTimer = null; }
      sendThinking(false);
      log('sys', 'oyun ağ hatası: ' + e.message);
    }
  }

  async function applyGamePayload(p) {
    if (!p) return;
    gamePhase = (p.phase && p.phase !== 'idle') ? p.phase : null;
    if (Number.isInteger(p.turn_id)) gameTurnId = p.turn_id;
    const isWord = (p.game === 'kelime');
    const isTimed = (p.game === 'kelime' || p.game === 'quiz');

    // Sergi ekranında kullanıcı hamlesinin typewriter'ı bitsin diye kısa bekle
    // (aynı anda ai-text yazılırsa user-text kesilir) — ayrıca "düşünme" hissi verir.
    // Kullanıcı metni typewriter'ı (kısa oyun girdisi) bitsin diye küçük tampon;
    // bekleme hissini azaltmak için Faz 3'te kısaltıldı.
    let gap = (p.kind === 'round') ? 480
            : (isWord && p.kind === 'ai_word') ? 320 : 260;
    // Bulanık kabul: cevap doğru sayıldıysa sergideki kullanıcı balonuna ham STT
    // yerine kabul edilen cevap yeniden yazılır; gap yeniden yazımı kapsar
    // (yoksa ai_reply daktilosu düzeltmeyi yarıda keser — sergi tek activeTypewriter).
    if (p.user_display && normalizeTr(p.user_display) !== normalizeTr(sentUserText)) {
      sendToDisplay({ type: 'user_text', text: p.user_display, speed: 14 });
      gap = Math.max(gap, p.user_display.length * 14 + 200);
    }
    await new Promise((res) => setTimeout(res, gap));

    sendToDisplay({
      type: 'ai_reply',
      jest_id: p.jest_id,
      yanit: p.yanit || '',
      yogunluk: p.yogunluk,
      outcome: p.outcome || null,   // sergi: AI kazaninca sari isik
      insist: !!p.insist,           // sergi: "bir daha oynayalim" israri vurgusu
    });
    if (p.jest_id) triggerGesture(p.jest_id, { intensity: p.yogunluk });
    if (els.aiResponse) {
      els.aiResponse.textContent = p.yanit || '';
      els.aiResponse.classList.remove('empty');
    }

    if (p.score) {
      sendToDisplay({ type: 'game_score', score: p.score, active: true });
      updateGameScoreUI(p.score);
    }
    renderGameButtons(p.buttons || []);
    publishGameOptions(p);
    if (els.gameTheme) {
      const adlar = { edebiyat: 'Edebiyat', tarih: 'Tarih', bilim: 'Bilim', genel: 'Genel' };
      els.gameTheme.textContent = p.category ? ('Tema: ' + (adlar[p.category] || p.category)) : '';
    }
    if (p.game === 'quiz' && els.gameScore) {
      els.gameScore.textContent = p.quiz_progress || '—';
    }

    if (p.kind === 'round') {
      log('jest', 'oyun: ' + p.outcome + ' → ' + p.jest_id
        + (p.insist ? ' (ısrar)' : '')
        + ' | BEN ' + p.score.ai + ' - ' + p.score.user + ' SEN');
    } else if (isWord) {
      log('jest', 'kelime: ' + p.kind
        + (p.required_letter ? " → '" + p.required_letter + "'" : '')
        + (p.outcome ? ' | ' + p.outcome : ''));
    } else if (p.game === 'quiz') {
      log('jest', 'bilgi: ' + p.kind
        + (p.dogru_mu === true ? ' ✓' : p.dogru_mu === false ? ' ✗' : '')
        + (p.user_display ? ' | kabul: ' + p.user_display : ''));
    } else {
      log('sys', 'oyun: ' + p.kind);
    }

    if (p.ai_error) {
      log('sys', '⚠ Ollama erişilemedi — AI gerçek pes etmedi, kontrol et (model/servis)');
    }

    // ——— Kelime oyunu: zaman barı + otomatik AI turu ———
    if (isTimed) {
      if (p.ended || !p.timer) stopWordTimer();
      else startWordTimer(p.timer.seconds, p.timer.who);
      // Yalniz kelime modunda AI turu otomatik istenir (esanlam tek yonlu).
      if (p.game === 'kelime' && !p.ended && p.turn === 'ai') requestAiTurn();
    }

    if (p.ended) {
      if (testMode) {
        // Test modu: her oyun bitişinde göz moduna dön (bitiş mesajı okunsun, sonra).
        // gamePhase hemen boşalır ki bu sırada gelen girdi en başa (selam+menü) gitsin.
        stopWordTimer();
        gamePhase = null;
        // Sergi ekranı bitiş TTS'i bitince göz moduna geçer (zamanlama orada —
        // sesin ne zaman bittiğini yalnız sergi bilir) ve 'attract_sync' ile
        // panel durumunu eşitler. Bitiş ekranı 60 sn boşta sayacını beklemez.
        sendToDisplay({ type: 'end_to_eyes' });
        setTimeout(() => {
          if (!gamePhase) { sendToDisplay({ type: 'game_exit' }); hideGameUI(); }
        }, TEST_END_LINGER_MS);
      } else if (isTimed) {
        // Normal: Kelime/Eş-Zıt maçı bitti — timer dur, "Yeni oyun/Çıkış" + skor kalır.
        stopWordTimer();
      } else {
        gamePhase = null;
        sendToDisplay({ type: 'game_exit' });
        hideGameUI();
      }
    }
  }

  // ——— Kelime oyunu: AI turu + zaman barı ————————————————————
  async function requestAiTurn() {
    try {
      const r = await fetch('/api/game/ai_turn', { method: 'POST' });
      const data = await r.json();
      if (data.error) { log('sys', 'kelime AI hatası: ' + data.error); return; }
      await applyGamePayload(data);
    } catch (e) {
      log('sys', 'kelime AI ağ hatası: ' + e.message);
    }
  }

  async function submitGameTimeout() {
    log('sys', 'kelime: süre doldu');
    const turnId = gameTurnId;
    try {
      const r = await fetch('/api/game/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timeout: true, turn_id: turnId }),
      });
      const data = await r.json();
      if (data.error === 'stale_input') {
        // Eski sayacın timeout'u yeni turu tüketmez; panel sunucuyla yeniden eşitlenir.
        // (Aktif tur yokken gelen geç timeout'u da backend bu hatayla reddediyor.)
        if (gameTurnId === turnId) adoptServerGameState(data);
        return;
      }
      if (!data.error) await applyGamePayload(data);
    } catch (e) {
      log('sys', 'kelime timeout ağ hatası: ' + e.message);
    }
  }

  // control.js geri sayım otoritesi: sergiye timer_start/stop yansıtır;
  // yalnız kullanıcı turunda süre dolunca backend'e timeout bildirir.
  let wordTimer = { id: null, who: null, endsAt: 0, total: 0 };
  function startWordTimer(seconds, who) {
    stopLocalTimer();
    wordTimer = { id: null, who: who, endsAt: Date.now() + seconds * 1000, total: seconds };
    sendToDisplay({ type: 'timer_start', seconds: seconds, who: who });
    renderControlTimer(seconds, seconds, who);
    wordTimer.id = setInterval(() => {
      const remain = Math.max(0, (wordTimer.endsAt - Date.now()) / 1000);
      renderControlTimer(remain, wordTimer.total, who);
      if (remain <= 0) {
        const wasUser = (wordTimer.who === 'user');
        stopLocalTimer();
        if (els.wordTimer) els.wordTimer.classList.add('hidden');
        if (wasUser) submitGameTimeout();
      }
    }, 100);
  }
  function stopLocalTimer() {
    if (wordTimer.id) { clearInterval(wordTimer.id); wordTimer.id = null; }
  }
  function stopWordTimer() {
    stopLocalTimer();
    sendToDisplay({ type: 'timer_stop' });
    if (els.wordTimer) els.wordTimer.classList.add('hidden');
  }
  function renderControlTimer(remain, total, who) {
    const el = els.wordTimer;
    if (!el) return;
    el.classList.remove('hidden');
    el.classList.toggle('ai', who === 'ai');
    const label = el.querySelector('.wt-label');
    const num = el.querySelector('.wt-num');
    const fill = el.querySelector('.wt-fill');
    if (label) label.textContent = (who === 'ai') ? 'AICAN düşünüyor…' : 'SEN — cevap ver';
    if (num) num.textContent = Math.ceil(remain) + ' sn';
    if (fill) {
      fill.style.width = (total > 0 ? (remain / total) * 100 : 0) + '%';
      fill.classList.toggle('low', remain <= 5);
    }
  }

  function renderGameButtons(buttons) {
    if (!els.gameButtons) return;
    els.gameButtons.innerHTML = '';
    buttons.forEach((b) => {
      const btn = document.createElement('button');
      btn.className = 'btn game-move' + (b.key === 'cikis' ? ' danger' : '');
      btn.textContent = b.label;
      btn.addEventListener('click', () => submitGameInput(b.key, b.label, true));
      els.gameButtons.appendChild(btn);
    });
  }
  function publishGameOptions(payload) {
    const p = payload || {};
    const buttons = Array.isArray(p.buttons) ? p.buttons : [];
    displayOptionButtons = buttons.slice();
    sendToDisplay({
      type: 'game_options',
      visible: buttons.length > 0 || !!p.hint,
      buttons: buttons,
      hint: p.hint || null,   // sesli yonlendirme balonu ("«Başla» de" vb.)
      phase: p.phase || null,
      game: p.game || null,
      kind: p.kind || null,
    });
  }
  function publishHomeOptions() {
    const opts = testMode ? HOME_OPTIONS_TEST : HOME_OPTIONS;   // test modunda 'Sohbet et' yok
    displayOptionButtons = opts.slice();
    sendToDisplay({
      type: 'game_options',
      visible: true,
      buttons: opts,
      hint: 'Söylemen yeterli',
      phase: 'idle',
      game: null,
      kind: 'home',
    });
  }
  function optionTextForMatch(button) {
    return normalizeTr([
      button && button.key,
      button && button.label,
    ].filter(Boolean).join(' '));
  }
  function selectedOptionKey(text, fallbackText) {
    const explicit = normalizeTr(text);
    for (const b of displayOptionButtons) {
      const key = String((b && b.key) || '');
      if (explicit && explicit === normalizeTr(key)) return key;
    }
    const n = normalizeTr([text, fallbackText].filter(Boolean).join(' '));
    if (!n) return '';
    for (const b of displayOptionButtons) {
      const key = String((b && b.key) || '');
      const label = optionTextForMatch(b);
      if (n === normalizeTr(key) || label === n || label.includes(n) || n.includes(label)) {
        return key;
      }
    }
    return normalizeTr(text);
  }
  function selectDisplayOption(text, label) {
    const key = selectedOptionKey(text, label);
    sendToDisplay({
      type: 'game_option_select',
      key: key,
      text: label || text || key,
    });
  }
  function hideGameOptions() {
    displayOptionButtons = [];
    sendToDisplay({ type: 'game_options', visible: false, buttons: [] });
  }
  function updateGameScoreUI(score) {
    if (els.gameScore) {
      els.gameScore.textContent = 'BEN ' + score.ai + ' · ' + score.user + ' SEN'
        + (score.draw ? ' · ' + score.draw + ' berabere' : '');
    }
  }
  function hideGameUI() {
    if (els.gameButtons) els.gameButtons.innerHTML = '';
    if (els.gameScore) els.gameScore.textContent = '—';
    if (els.gameTheme) els.gameTheme.textContent = '';
    hideGameOptions();
    stopWordTimer();
  }

  // ——— Hizli jest grid ——————————————————————————————
  function buildGestureGrid() {
    if (!els.gestureGrid) return;
    els.gestureGrid.innerHTML = '';
    gestures.forEach((g) => {
      const btn = document.createElement('button');
      btn.className = 'gesture-chip';
      const rgb = 'rgb(' + primaryFor(g).join(',') + ')';
      btn.innerHTML =
        '<span class="chip-swatch" style="background:' + rgb +
        '; box-shadow: 0 0 6px ' + rgb + '"></span>' +
        '<span class="chip-name">' + humanName(g.id) + '</span>';
      btn.title = g.id + ' (' + g.animasyon.desen + ')';
      btn.addEventListener('click', () => {
        noteActivity();
        triggerGesture(g.id);
        sendToDisplay({ type: 'manual_gesture', jest_id: g.id });
        log('sys', 'manuel jest: ' + g.id);
      });
      els.gestureGrid.appendChild(btn);
    });
  }

  // ——— Gercek model yonetimi ————————————————————————
  async function loadGestures() {
    try {
      const r = await fetch('/api/gestures');
      const data = await r.json();
      gestures = data.jestler || [];
      gestureMap = new Map(gestures.map((g) => [g.id, g]));
    } catch (e) {
      log('sys', 'jest listesi yuklenemedi: ' + e.message);
    }
  }

  async function refreshModels() {
    try {
      const r = await fetch('/api/models');
      const data = await r.json();
      const models = data.models || [];
      if (els.modelSelect) {
        els.modelSelect.innerHTML = '';
        models.forEach((m) => {
          const opt = document.createElement('option');
          opt.value = m.name;
          opt.textContent = m.name + '  (' + m.size_gb.toFixed(1) + ' GB)';
          els.modelSelect.appendChild(opt);
        });
        // aktif modeli secili goster
        if (data.active) {
          for (let i = 0; i < els.modelSelect.options.length; i++) {
            if (els.modelSelect.options[i].value === data.active) {
              els.modelSelect.selectedIndex = i;
              break;
            }
          }
        }
      }
      if (data.active && els.activeModel) els.activeModel.textContent = data.active;
      log('sys', 'model listesi yenilendi (' + models.length + ')');
    } catch (e) {
      log('sys', 'model listesi alinamadi: ' + e.message);
    }
  }

  async function activateModel() {
    if (!els.modelSelect || !els.modelSelect.value) return;
    const name = els.modelSelect.value;
    try {
      const r = await fetch('/api/model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await r.json();
      if (data.error) {
        if (els.activeNote) els.activeNote.textContent = 'hata: ' + data.error;
        log('sys', 'model degisim HATA: ' + data.error);
        return;
      }
      if (els.activeModel) els.activeModel.textContent = name;
      if (els.activeNote) els.activeNote.textContent = data.changed ? 'aktif edildi' : 'zaten aktif';
      log('sys', 'aktif model: ' + name);
    } catch (e) {
      if (els.activeNote) els.activeNote.textContent = 'ag hatasi';
      log('sys', 'model degisim ag hatasi: ' + e.message);
    }
  }

  async function downloadModel() {
    const name = (els.newModelInput.value || '').trim();
    if (!name) return;
    log('sys', 'indirme baslatildi: ' + name);
    if (els.activeNote) els.activeNote.textContent = 'indiriliyor...';
    try {
      const r = await fetch('/api/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await r.json();
      if (data.error) {
        log('sys', 'indirme HATA: ' + data.error);
        if (els.activeNote) els.activeNote.textContent = 'indirme hatasi';
        return;
      }
      log('sys', 'indirme tamam: ' + name);
      if (els.activeNote) els.activeNote.textContent = 'indirildi';
      els.newModelInput.value = '';
      refreshModels();
    } catch (e) {
      log('sys', 'indirme ag hatasi: ' + e.message);
      if (els.activeNote) els.activeNote.textContent = 'ag hatasi';
    }
  }

  // ——— Init ————————————————————————————————————————
  async function init() {
    if (els.canvas && typeof LEDPanel !== 'undefined') {
      panel = new LEDPanel(els.canvas, { size: els.canvas.width });
    }
    await loadGestures();
    await loadEmojiManifest();
    await loadServerConfig();
    applyMode(loadStoredMode(), false);
    applyImmersive(loadStoredImmersive(), false);   // buton metnini kalıcı tercihe göre kur
    buildGestureGrid();
    initChannel();
    refreshModels();

    if (els.prompt) {
      els.prompt.addEventListener('input', updateCharCount);
      els.prompt.addEventListener('input', noteActivity);   // yazmak = etkileşim
      updateCharCount();
    }

    if (els.sendBtn) els.sendBtn.addEventListener('click', handleSend);
    if (els.stopBtn) els.stopBtn.addEventListener('click', handleStop);
    if (els.gameStartBtn) els.gameStartBtn.addEventListener('click', () => startGame('Oyun oynayalım'));
    if (els.prompt) els.prompt.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });
    if (els.activateBtn) els.activateBtn.addEventListener('click', activateModel);
    if (els.refreshBtn) els.refreshBtn.addEventListener('click', refreshModels);
    if (els.downloadBtn) els.downloadBtn.addEventListener('click', downloadModel);
    if (els.modeToggle) els.modeToggle.addEventListener('click', toggleMode);
    if (els.immersiveToggle) els.immersiveToggle.addEventListener('click', toggleImmersive);
    if (els.testToggle) els.testToggle.addEventListener('click', toggleTestMode);

    initMic();

    // M tusu: mod toggle · G tusu: test modu (input dışındayken)
    document.addEventListener('keydown', (e) => {
      if (e.repeat) return;   // tuş basılı tutulunca tekrar tetiklenmesin
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
      if (e.key === 'm' || e.key === 'M') toggleMode();
      if (e.key === 'g' || e.key === 'G') toggleTestMode();
      if (e.key === 'i' || e.key === 'I' || e.key === 'ı' || e.key === 'İ') toggleImmersive();
    });

    // Sergi ekranı bağlandığında mevcut mod + tam ekran durumunu ona da gönder (geç açılırsa)
    setTimeout(() => {
      sendToDisplay({ type: 'set_mode', mode: currentMode });
      sendToDisplay({ type: 'immersive', on: immersive });
    }, 800);

    log('sys', 'kontrol paneli hazir');
    log('sys', 'enter ile gonder · m ile mod degis · g ile test modu · i ile tam ekran');

    if (els.statThink) els.statThink.textContent = '— sn';
    if (els.statLoad) els.statLoad.textContent = '— sn';
    if (els.statTokens) els.statTokens.textContent = '0 → 0';
    if (els.statRate) els.statRate.textContent = '— tok/s';
  }

  document.addEventListener('DOMContentLoaded', init);
})();
