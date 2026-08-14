"""AI Body — yeni web arayuzu icin Flask HTTP koprusu.

- Statik: /web/ altindan AI_Body_v2.html ve Kontrol_Paneli.html sunar.
- /api/send  : kullanici metnini LLMBridge ile Ollama'ya gonderir, jest sonucunu doner.
- /api/gestures : ai/gestures.json icerigi.
- /api/models : Ollama lokal model listesi.
- /api/model  : aktif modeli degistir.
- /api/pull   : yeni model indir (basit, blocking).
- /api/health : Ollama canli mi.

Calistirma: python orchestrator/web_server.py (veya run_web.py)
Cekirdek dosyalar (llm_bridge.py, gestures.json, system_prompt.txt) DEGISTIRILMEZ.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from game_engine import GameEngine
from llm_bridge import LLMBridge
from sergi_logger import SergiLogger
from session_logger import SessionLogger
import yasakli_filtre

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("web_server")

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent


def _config_yolu() -> Path:
    """Hangi config dosyasi? AICAN_CONFIG verilmisse o, yoksa config.json.

    config.sergi*.json dosyalarinin aciklama satirlari bu ortam degiskenini
    yillardir tarif ediyordu ama KOD OKUMUYORDU: profil secmek icin
    AICAN_CONFIG ayarlayan biri sessizce LAPTOP profiliyle calisiyordu.
    Yeni sergi PC'sinde bunun bedeli buyuk — laptop profili int8_float16
    ister, RTX 5090 (sm_120) INT8 desteklemez, sistem CPU'ya duser ve
    "calisiyor ama yavas" halde sergiye cikardi. Simdi gercekten okunuyor.

    Yol goreli verilirse once proje kokune, sonra orchestrator/ altina
    bakilir (belge 'orchestrator/config.sergi.json' diyor, kisa hali de
    'config.sergi.json' calissin). Dosya YOKSA sessizce config.json'a
    dusmek ayni tuzagi kurar -> gurultulu uyari basip devam ederiz."""
    ham = os.environ.get("AICAN_CONFIG", "").strip()
    varsayilan = BASE_DIR / "config.json"
    if not ham:
        return varsayilan
    aday = Path(ham)
    for p in ([aday] if aday.is_absolute() else [ROOT_DIR / aday, BASE_DIR / aday]):
        if p.is_file():
            return p
    log.warning("AICAN_CONFIG='%s' bulunamadi — config.json kullaniliyor. "
                "Profil BEKLEDIGINIZ GIBI OLMAYABILIR.", ham)
    return varsayilan


CONFIG_PATH = _config_yolu()
WEB_DIR = ROOT_DIR / "web"
ASSETS_DIR = ROOT_DIR / "assets"
EMOJI_BASE_DIR = ASSETS_DIR / "emojis"
EMOJI_FPS = 12  # gesture_engine.EMOJI_FPS ile esit kalmali

# Whisper (ses-metin) varsayilanlari. config.json anahtarlari ile ezilir:
#   whisper_model_size / whisper_device / whisper_compute_type / whisper_initial_prompt
# Laptop profili CPU'da kalir cunku 4GB VRAM zaten aktif LLM ile dolu;
# sergi PC'sinde (16GB) config.sergi.json cuda/float16 secer.
WHISPER_MODEL_SIZE = "small"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_LANGUAGE = "tr"

# Cozumlemeyi sergi sozlugune yonlendiren baglam cumlesi (bias). Whisper bunu
# "onceki metin" sanir; alan kelimelerinin dogru yazilmasini saglar.
WHISPER_INITIAL_PROMPT = (
    "Bilim merkezinde çocuklarla Türkçe sohbet. Merhaba aican, oyun oynayalım, "
    "başla, evet, hayır, eş anlam, zıt anlam, atasözü, doğru, yanlış."
)

# Oyun modunda (/api/transcribe form alani context=game) kisa komut sozlugu:
# cevaplar tek kelime oldugu icin bias'i komutlara daraltmak ilk denemede
# dogru tanima oranini artirir (yanlis hamle -> tekrar turu = en buyuk gecikme).
# Sohbet promptundan ayri tutulur ki gunluk konusma komutlara cekilmesin.
# config.json "whisper_initial_prompt_game" ile ezilebilir.
WHISPER_GAME_PROMPT = (
    "Bilim merkezinde çocuklarla sesli oyun. Başla, hazırım, tamam, menü, çıkış, "
    "tekrar, atasözü, eş anlam, zıt anlam, doğru, yanlış, kelime, bir, iki, üç, dört."
)

# Whisper'in gurultuye/sessizlige uydurdugu klasik Turkce halusinasyonlar
# (YouTube altyazi kaliplari). Normalize edilmis segment bunlardan birini
# ICERIYORSA segment atilir. Kisa gercek cumleleri yakalamayacak kadar ozgul tut.
WHISPER_HALLUCINATION_PHRASES = (
    "izlediginiz icin tesekkur",
    "video icin tesekkur",
    "abone olmayi unutmayin",
    "abone olun",
    "kanalima abone",
    "begenmeyi unutmayin",
    "iyi seyirler",
    "thank you for watching",
    "subtitles by",
)

# Tek basina gecmesi bile halusinasyon sayilan kelimeler: sergide kimse
# "altyazı" demez; Whisper sessizlige en sik bunu uydurur. Eski "altyazi m k"
# KALIP eslesmesi K'siz varyantlari ("Altyazı M", "Altyazı: ...") KACIRIYORDU —
# sahada her soz "Altyazı M" diye donuyordu. Kelime bazli kontrol hepsini yakalar.
WHISPER_HALLUCINATION_WORDS = frozenset({"altyazi", "altyazilar", "altyazili", "amara"})

_TR_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def _stt_normalize(text: str) -> str:
    """Kucult + Turkce karakterleri sadelestir + noktalamayi at (kara liste kiyasi).
    'İ'.lower() 'i'+birlesen nokta (U+0307) uretir ve kelimeyi boler — once sadelestir.
    """
    t = text.replace("İ", "i").replace("I", "i").lower().translate(_TR_FOLD)
    t = t.replace("̇", "")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _stt_is_hallucination(text: str) -> bool:
    norm = _stt_normalize(text)
    if any(p in norm for p in WHISPER_HALLUCINATION_PHRASES):
        return True
    return bool(WHISPER_HALLUCINATION_WORDS & set(norm.split()))


# ——— Gurultu bastirma (denoise) — STT ONCESI opsiyonel on-isleme ———————————
# Gurultulu sergi ortami icin: Whisper'a girmeden ONCE ses 16 kHz'e cozulup
# spektral gating ile temizlenir (noisereduce — saf CPU, CEVRIMDISI, KREDI
# HARCAMAZ). ElevenLabs Voice Isolator'un aksine yerel: her cumlede bulut
# gidis-donusu / kredi yok. Config'ten acilir (whisper_denoise_enabled);
# kutuphane yoksa ya da hata olursa SESSIZCE ham sesle devam edilir (sergi
# asla susmaz). NOT: asiri denoise Whisper'i BOZABILIR — prop_decrease olculu
# tutulmali ve whisper_debug_save_audio ile A/B test edilmeli.
_NR = {"tried": False, "mod": None}


def _noisereduce():
    """noisereduce modulunu bir kez lazy yukle; yoksa None (yalnizca bir kez uyar)."""
    if not _NR["tried"]:
        _NR["tried"] = True
        try:
            import noisereduce as nr
            _NR["mod"] = nr
        except Exception as e:  # noqa: BLE001 — kutuphane yoksa denoise atlanir
            log.warning("noisereduce yuklenemedi — denoise devre disi: %s", e)
    return _NR["mod"]


def _prepare_audio(audio_bytes: bytes, config: dict, trim_ms: int = 0):
    """Ham ses bytes -> (float32 np.array @16kHz | None, denoise_ms, trim uygulanan ms).

    Iki on-isleme tek decode ile: (1) TRIM — istemci konusma baslangicini bildirir
    (trim_ms); oncesindeki sessizlik/TTS yankisi atilir. Kayit surekli acik oldugundan
    blob'un basinda saniyelerce alakasiz ses birikebilir: Whisper'in AI'nin kendi
    cumlesini "duymasinin" (yanlis girdi) ve bosuna uzun cozumlemesinin ana kaynagi.
    (2) DENOISE — spektral gating (mevcut davranis).

    None donerse cagiran HAM bytes'i Whisper'a verir (davranis degismez). Model
    KILIDI DISINDA cagrilmali — bu CPU isi, kilidi bosuna tutmasin."""
    want_denoise = bool(config.get("whisper_denoise_enabled", False))
    trim_ms = max(0, int(trim_ms or 0))
    if not want_denoise and trim_ms <= 0:
        return None, 0, 0
    try:
        import numpy as np
        from faster_whisper.audio import decode_audio
        t = time.perf_counter()
        y = decode_audio(io.BytesIO(audio_bytes), sampling_rate=16000)
        trimmed = 0
        if trim_ms > 0:
            cut = int(trim_ms * 16)  # 16 ornek/ms @16kHz
            # Guvenlik: kirpma sonrasi en az 0.35 sn kalmali (istemci payi zaten
            # ~350 ms erken keser); kalmiyorsa kirpma atlanir, ses oldugu gibi gider.
            if len(y) - cut >= int(0.35 * 16000):
                y = y[cut:]
                trimmed = trim_ms
        if want_denoise:
            nr = _noisereduce()
            if nr is not None:
                y = nr.reduce_noise(
                    y=y, sr=16000,
                    prop_decrease=float(config.get("whisper_denoise_prop_decrease", 0.75)),
                    stationary=bool(config.get("whisper_denoise_stationary", False)),
                )
        # ctranslate2 icin bitisik float32 dizi
        y = np.ascontiguousarray(y, dtype=np.float32)
        return y, int((time.perf_counter() - t) * 1000), trimmed
    except Exception as e:  # noqa: BLE001 — hata olursa ham sesle devam
        log.warning("Ses on-isleme hatasi — ham ses kullanilacak: %s", e)
        return None, 0, 0


def _stt_is_tts_echo(text: str, echo_text: str) -> bool:
    """Transkript, az once calan TTS metninin yankisi mi?

    Istemci yalnizca AI konusurken/konusma bitisinde baslamis kayitlar icin
    echo_text gonderir (bos gelirse hic bakilmaz). Cocuklar mesru olarak AI'nin
    cumlesindeki KELIMELERI tekrar eder ("atasözü" secimi, quiz cevabi) — bu
    yuzden tek/iki kelime asla yankı sayilmaz: en az 4 kelime VE kelimelerin
    >=%80'i TTS metninde geciyorsa yankidir."""
    if not text or not echo_text:
        return False
    words = _stt_normalize(text).split()
    if len(words) < 4:
        return False
    echo_words = set(_stt_normalize(echo_text).split())
    if not echo_words:
        return False
    hit = sum(1 for w in words if w in echo_words)
    return (hit / len(words)) >= 0.8


# TTS varsayilanlari — QW-5: tek kaynak. Birincil motor edge oldugundan varsayilan
# ses de edge sesi olmali (eski "tr_TR-dfki-medium" fallback'i Piper ses adiydi).
DEFAULT_TTS_VOICE = "tr-TR-EmelNeural"

# Acilis edge erisilebilirlik probu: motor yuklendikten sonra BIR KEZ kucuk bir
# sentez denenir; basarisizsa motor bastan Piper'a sabitlenir (FallbackEngine'in
# her istekte edge deneyip timeout beklemesi yerine).
EDGE_PROBE_TEXT = "merhaba"
EDGE_PROBE_TIMEOUT_S = 5.0

# /api/session/new sabit selamlamasi — on-isitma ayni metin/jest/yogunluk kullanir
# ki onbellek anahtarlari birebir isabet etsin.
SESSION_GREETING_TEXT = 'Merhaba. Sohbet edebiliriz. Oyun için "oyun oynayalım" de.'
SESSION_GREETING_JEST = "selamlama"
SESSION_GREETING_YOGUNLUK = 0.8

# ——— TEST MODU (sergi test gunu) ———————————————————————————————
# 'g' tusu / POST /api/test_mode ile acilip kapanir; config.json'da kalicidir.
# Acikken: menude yalnizca TEST_OYUNLAR, sohbet (/api/send LLM yolu) kapali,
# "merhaba" selamlamasi dogrudan oyun menusunu acar.
TEST_OYUNLAR = ("eszit", "atasozu")
# Sesli-yalniz sergi akisi: dokunma fiili yok (ekranda buton dokunmatik degil).
# Selam sabit soru formu — TEST_OYUNLAR sabit oldugu icin menuden turetme gereksiz.
TEST_GREETING_TEXT = "Merhaba, hoş geldin! Atasözü mü oynamak istersin, Eş/Zıt Anlam mı?"
TEST_SOHBET_KAPALI_TEXT = "Bugün oyun günü! Hangisini oynayalım — söyle."


def _test_greeting_yanit() -> str:
    """Test modunda selam yaniti. Tek kaynak: /api/session/new ve on-isitma
    ayni metni uretir (cache isabeti)."""
    return TEST_GREETING_TEXT


def _test_mode_texts() -> list:
    """Test modu sabit replikleri (on-isitma icin) — gecici sinirli motorla birebir."""
    from game_engine import GameEngine
    g = GameEngine(bridge=None)
    g.izinli_oyunlar = TEST_OYUNLAR
    g.voice_only = True   # menu/ready metinleri canli test modu ile birebir olsun (cache isabeti)
    menu = g._menu_payload()
    return [_test_greeting_yanit(), menu["yanit"],
            g._menu_payload(reprompt=True)["yanit"], TEST_SOHBET_KAPALI_TEXT]

# game_engine icindeki inline kural/hazirlik metinlerinin birebir kopyalari
# (game_engine'e dokunmadan). Metin orada degisirse on-isitma sadece iska gecer — hata olmaz.
KELIME_KURAL_TEXT = ("Kelime türetme oynayalım! Ben bir kelime söylerim. Sen de son "
                     "harfiyle başlayan yeni bir kelime söyle. Sırayla devam ederiz. "
                     "Aynı kelimeyi iki kez kullanamayız. Her tur için 20 saniyen var. "
                     "Hazırsan 'başla' de!")
HAZIR_BEKLE_TEXT = "Hazır olunca 'başla' de ya da butona dokun :)"


def load_config() -> dict:
    # utf-8-sig: elle duzenlenen config Notepad/PowerShell'den BOM'lu kaydedilse de okunur.
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


class WhisperState:
    """Lazy yuklenmis Whisper modeli + durum. Tek instance, tum istekler paylasir."""

    def __init__(self) -> None:
        self.model = None        # faster_whisper.WhisperModel | None
        self.status = "yok"      # "yok" | "yukleniyor" | "hazir" | "hata"
        self.error = ""
        self.device = ""         # fiilen yuklenen cihaz (cuda fallback izlenebilsin)
        self.compute_type = ""
        self._lock = threading.Lock()  # transcribe re-entrancy guard

    def is_ready(self) -> bool:
        return self.model is not None and self.status == "hazir"


def _add_cuda_dll_dirs() -> None:
    """pip ile kurulan nvidia-* wheel'larinin (cublas/cudnn) DLL klasorlerini
    Windows DLL arama yoluna ekler.

    KRITIK: ctranslate2 cublas64_12.dll / cudnn dll'lerini GEC yukler — model
    CUDA'ya sorunsuz 'yuklenir' (status=hazir) ama ILK transkripsiyonda
    "Library cublas64_12.dll is not found" ile coker. Sistem CUDA Toolkit'i
    kurulu degilse bile pip'teki nvidia-cublas-cu12 + nvidia-cudnn-cu12
    yeterlidir; burada onlarin bin/ klasorlerini hem add_dll_directory hem
    PATH'e ekleriz (ct2 PATH uzerinden LoadLibrary yapar)."""
    if os.name != "nt":
        return
    import site
    import sysconfig
    roots = set()
    try:
        roots.update(site.getsitepackages())
    except Exception:  # noqa: BLE001 — venv/embedded python'da olmayabilir
        pass
    roots.add(sysconfig.get_paths().get("purelib", ""))
    added = []
    for root in roots:
        if not root:
            continue
        nv = Path(root) / "nvidia"
        if not nv.is_dir():
            continue
        for bin_dir in sorted(nv.glob("*/bin")):
            try:
                os.add_dll_directory(str(bin_dir))
            except Exception:  # noqa: BLE001
                pass
            added.append(str(bin_dir))
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")
        log.info("CUDA DLL yollari eklendi: %s", "; ".join(added))


def _whisper_probe(model) -> None:
    """Kucuk GERCEK transkripsiyon calistirir (1 sn'lik ton).

    Model yuklemesi basarili gorunse de CUDA calisma kutuphaneleri eksik/bozuksa
    hata ancak ilk encode'da patlar; sergi o ana kadar 'hazir' sanip sahada
    sagir kalirdi. Probe hatasi cagirana yukselir -> CPU denemesine gecilir.
    vad_filter KAPALI: sesin konusma sayilmamasi encode'u atlatmasin."""
    import math
    import struct
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = bytearray()
        for i in range(16000):  # 1 saniye, 440 Hz dusuk genlikli ton
            frames += struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 16000)))
        w.writeframes(bytes(frames))
    buf.seek(0)
    segments, _info = model.transcribe(buf, language=WHISPER_LANGUAGE,
                                       beam_size=1, vad_filter=False)
    for _seg in segments:  # generator'i tuket — encode fiilen calissin
        pass


def _load_whisper_async(state: WhisperState, model_size: str,
                        device: str, compute_type: str) -> None:
    """Modeli arka planda yukler — HTTP yanit vermeyi gec birakmaz.
    CUDA istenip yuklenemez ya da CALISTIRILAMAZSA (cublas/cuDNN eksik)
    CPU int8'e geri duser; sergi makinesi STT'siz kalmasin.
    """
    state.status = "yukleniyor"
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # noqa: BLE001
        state.status = "hata"
        state.error = str(e)
        log.warning("faster_whisper import edilemedi: %s", e)
        return
    if device != "cpu":
        _add_cuda_dll_dirs()
    attempts = [(device, compute_type)]
    if device != "cpu":
        # ARA BASAMAK — GPU'yu birakmadan once float16'yi dene.
        # Blackwell (RTX 50xx / sm_120): CTranslate2 4.6.2 INT8'i bu mimaride
        # kapatti; int8 / int8_float16 CUBLAS_STATUS_NOT_SUPPORTED ile coker.
        # Bu satir olmadan yanlis config'li bir 5090 dogrudan CPU'ya duser ve
        # sergi "calisiyor ama STT 3-4 sn" halinde sessizce yavaslar. float16
        # her CUDA kartinda gecerli, dolayisiyla eski sergi PC'sinde de zararsiz.
        if "int8" in compute_type:
            attempts.append((device, "float16"))
        attempts.append(("cpu", "int8"))
    for dev, ct in attempts:
        try:
            log.info("Whisper yukleniyor: %s (%s, %s)", model_size, dev, ct)
            model = WhisperModel(model_size, device=dev, compute_type=ct)
            # Yukleme yetmez — kucuk gercek transkripsiyonla dogrula (cublas/cudnn
            # eksikligi ancak burada gorunur). Basarisizsa siradaki denemeye gec.
            _whisper_probe(model)
            state.model = model
            state.device = dev
            state.compute_type = ct
            state.status = "hazir"
            log.info("Whisper hazir (%s, %s).", dev, ct)
            return
        except Exception as e:  # noqa: BLE001 — model calismadi ama sergi devam etsin
            state.status = "hata"
            state.error = str(e)
            log.warning("Whisper yuklenemedi/calismadi (%s, %s): %s", dev, ct, e)


class TTSState:
    """Tembel yuklenmis TTS motoru + durum. Whisper ile ayni desen."""

    def __init__(self) -> None:
        self.engine = None       # tts.engine_base.TTSEngine | None
        self.status = "yok"      # "yok" | "yukleniyor" | "hazir" | "hata"
        self.error = ""
        self._lock = threading.Lock()  # tek model -> seri sentez

    def is_ready(self) -> bool:
        return self.engine is not None and self.status == "hazir"


def _probe_edge_or_pin_fallback(engine):
    """Edge'in erisilebilirligini BIR KEZ dener (kucuk sentez, sinirli sure).

    Basarili -> engine aynen doner (mevcut davranis). Basarisiz/timeout -> yedek
    Piper motoru doner; boylece FallbackEngine her istekte edge'i deneyip timeout
    beklemez. Yalnizca FallbackEngine (edge+piper) icin anlamlidir.
    """
    from tts.engine_base import FallbackEngine
    if not isinstance(engine, FallbackEngine):
        return engine
    result: dict = {}

    def _try():
        try:
            result["audio"] = engine.primary.synthesize(EDGE_PROBE_TEXT, None, 0.7)
        except Exception as e:  # noqa: BLE001 — ag hatasi = prob basarisiz
            result["error"] = e

    t = threading.Thread(target=_try, daemon=True)
    t.start()
    t.join(EDGE_PROBE_TIMEOUT_S)
    if t.is_alive():
        log.warning("TTS edge probu %.0fs icinde donmedi — motor Piper'a sabitlendi.",
                    EDGE_PROBE_TIMEOUT_S)
        return engine.fallback
    if result.get("error") is not None or not result.get("audio"):
        log.warning("TTS edge probu basarisiz (%s) — motor Piper'a sabitlendi.",
                    result.get("error", "bos ses"))
        return engine.fallback
    log.info("TTS edge probu OK (%d bayt).", len(result["audio"]))
    return engine


# Cumle sinirlari: .!?… + bosluk. web/app.js splitSentences ile BIREBIR ayni
# mantik olmali — on-isitma anahtarlari frontend parcalariyla eslessin.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")

_SESSIZ_WAV = None


def _sessiz_wav() -> bytes:
    """20 ms sessizlik (22050 Hz mono 16-bit).

    Sadece emoji/isaretten olusan bir parca normalize edilince BOSALIR (bkz
    tts/text_norm). Hata donersek istemci kalan parcalari da birakir
    (app.js speak(): `if (!url) return;`) -> cumlenin geri kalani susardi.
    Sessiz WAV ile o parca atlanir, akis devam eder."""
    global _SESSIZ_WAV
    if _SESSIZ_WAV is None:
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x00" * (2 * 441))
        _SESSIZ_WAV = buf.getvalue()
    return _SESSIZ_WAV


def _split_sentences_tr(text: str, min_len: int = 10) -> list:
    """Metni cumle parcalarina boler; kisa parca (<min_len) sonrakiyle birlesir,
    artan kisa kuyruk son parcaya eklenir. Tek cumlede [metin] doner."""
    parts = [p.strip() for p in _SENT_SPLIT_RE.split((text or "").strip()) if p.strip()]
    out = []
    buf = ""
    for p in parts:
        buf = (buf + " " + p) if buf else p
        if len(buf) >= min_len:
            out.append(buf)
            buf = ""
    if buf:
        if out:
            out[-1] += " " + buf
        else:
            out.append(buf)
    return out


def _cache_jest(engine, jest_id, yogunluk):
    """Onbellek anahtarindaki jest bileseni. ElevenLabs motoru KABA duygu imzasi
    kullanir (benzer jest'ler tek anahtar -> rastgele-jest pre-gen ile uyumlu).
    Diger motorlar (edge/piper) jest_id'yi oldugu gibi kullanir (mevcut davranis)."""
    sig_fn = getattr(engine, "cache_signature", None)
    if sig_fn is None and hasattr(engine, "primary"):   # FallbackEngine -> primary'yi ac
        sig_fn = getattr(engine.primary, "cache_signature", None)
    return sig_fn(jest_id, yogunluk) if sig_fn else jest_id


def _tts_synth_cached(state: "TTSState", cache, config: dict, text: str,
                      jest_id=None, yogunluk: float = 0.7):
    """Onbellek anahtari turetimi + sentez — api_speak ve on-isitma AYNI yolu
    kullanir (varsayilanlar api_speak ile ayni: jest_id=None, yogunluk=0.7)."""
    # SES metni != EKRAN metni: emoji/":)"/"Es/Zit" sese girmeden temizlenir
    # (bkz tts/text_norm.py). Anahtar TEMIZLENMIS metinden turetilir ki
    # on-uretim (gen_batch_elevenlabs) ile birebir ayni anahtar cikssin.
    from tts.text_norm import seslendirme_metni
    text = seslendirme_metni(text)
    if not text:
        return b""       # yalnizca emoji/isaretten ibaret parca — seslendirilecek sey yok
    voice = config.get("tts_voice", DEFAULT_TTS_VOICE)
    key = cache.make_key(text, _cache_jest(state.engine, jest_id, yogunluk), yogunluk, voice)
    audio = cache.get(key)
    if audio is None:
        with state._lock:  # tek model -> seri sentez
            audio = state.engine.synthesize(text, jest_id, yogunluk)
        if audio:
            # ONBELLEK ZEHIRLENME KORUMASI: yedege dusen sentez (ornegin
            # ElevenLabs anahtari yokken edge) birincil motorun anahtari altina
            # YAZILMAZ — yoksa ucretsiz ses, on-uretilmis ElevenLabs seslerinin
            # yerini kalici alir ve anahtar eklendikten sonra bile calinirdi.
            src = getattr(state.engine, "last_engine", None)
            intended = getattr(getattr(state.engine, "primary", state.engine), "name", None)
            if src is None or intended is None or src == intended:
                cache.put(key, audio)
    return audio


def _warm_texts(config: dict | None = None) -> list:
    """On-isitilacak sabit replikler: (metin, jest_id, yogunluk) uclusu.

    jest/yogunluk degerleri metnin GERCEKTE seslendirildigi payload'larla birebir
    ayni tutuldu (anahtar isabeti icin). Bilinmeyenlerde api_speak varsayilanlari.
    """
    items = []
    # 1) Guard guvenli-yanit sablonlari (llm_bridge) — jest = sablon anahtari.
    try:
        from llm_bridge import _SAFE_RESPONSE_TEMPLATES
        for jest_key, metin in _SAFE_RESPONSE_TEMPLATES.items():
            jest = None if jest_key == "sicaklik_default" else jest_key
            items.append((metin, jest, 0.7))  # yogunluk: api_speak varsayilani
    except Exception as e:  # noqa: BLE001 — isitma eksik kalsin, sergi calissin
        log.warning("On-isitma: guvenli sablonlar alinamadi: %s", e)
    # 2) Sergi selamlamasi (/api/session/new sabiti).
    items.append((SESSION_GREETING_TEXT, SESSION_GREETING_JEST, SESSION_GREETING_YOGUNLUK))
    # 2a) Yasakli kelime repligi: SABIT metin, sik duyulabilir. Acilista bir kez
    # ElevenLabs ile sentezlenip onbellege alinir -> sahada anlik calar ve her
    # engellemede yeniden kredi harcanmaz. jest/yogunluk, /api/transcribe'in
    # dondugu payload ile BIREBIR ayni (onbellek anahtari tutsun).
    items.append((yasakli_filtre.yanit_metni(config or {}),
                  yasakli_filtre.VARSAYILAN_JEST, 0.6))
    # 2b) Test modu replikleri ('g' ile sinirli menu) — acildiginda beklenmesin.
    try:
        for metin in _test_mode_texts():
            items.append((metin, SESSION_GREETING_JEST, SESSION_GREETING_YOGUNLUK))
    except Exception as e:  # noqa: BLE001
        log.warning("On-isitma: test modu replikleri alinamadi: %s", e)
    # 2c) Test modu quiz hazirlik replikleri — voice_only kapanislari ("butona
    # dokun" yok) ElevenLabs batch'inde bulunmaz; ilk ziyaretcide miss olmasin.
    try:
        from game_engine import GameEngine, _JEST as _GJ
        g = GameEngine(bridge=None)
        g.voice_only = True
        for oyun in TEST_OYUNLAR:
            g.quiz_provider = oyun
            hazir_yanit = g._start_quiz()["yanit"]
            for jest in _GJ.get("kel_intro", []):                 # random.choice ikisini de secebilir
                items.append((hazir_yanit, jest, 0.8))
        items.append((g._handle_quiz_ready("hmm")["yanit"], "bekle", 0.6))
    except Exception as e:  # noqa: BLE001
        log.warning("On-isitma: test quiz replikleri alinamadi: %s", e)
    # 3) Oyun kural/hazirlik replikleri (game_engine sabitleri — en sik kullanilanlar).
    try:
        from game_engine import _JEST as _GJ, _TXT as _GT
        items.append((_GT["exit"][0], _GJ["exit"], 0.6))
        for jest in _GJ.get("kel_intro", []):                     # random.choice ikisini de secebilir
            items.append((KELIME_KURAL_TEXT, jest, 0.8))          # game.start() = dogrudan kelime kurali
        items.append((HAZIR_BEKLE_TEXT, "bekle", 0.6))
    except Exception as e:  # noqa: BLE001
        log.warning("On-isitma: oyun replikleri alinamadi: %s", e)
    return items


def _warm_tts_cache(state: "TTSState", cache, config: dict) -> None:
    """Sik sabit metinleri cumle parcalari halinde onbellege isit.

    Frontend (app.js speak) metni cumlelere bolup POST ettigi icin isitma da ayni
    bolme ile parca parca yapilir. 3 hatadan sonra birakilir (motor coktu demektir).
    """
    if cache is None or not getattr(cache, "enabled", False) or not state.is_ready():
        return
    hazir = 0
    hata = 0
    for metin, jest, yog in _warm_texts(config):
        for parca in _split_sentences_tr(metin):
            if hata >= 3:
                log.warning("TTS on-isitma birakildi (ust uste hata; %d parca isindi).", hazir)
                return
            try:
                audio = _tts_synth_cached(state, cache, config, parca, jest, yog)
            except Exception as e:  # noqa: BLE001
                hata += 1
                log.warning("TTS on-isitma parca hatasi (%r): %s", parca[:30], e)
                continue
            if audio:
                hazir += 1
            else:
                hata += 1
    log.info("TTS on-isitma tamam: %d parca onbellekte.", hazir)


def _load_tts_async(state: "TTSState", config: dict, cache=None) -> None:
    """TTS motorunu arka planda yukler — HTTP yanitlarini geciktirmez.
    use_cuda=False: 4GB VRAM aktif LLM (Ollama) ile dolu; TTS CPU'da kalir
    (Piper RTF ~0.05, gercek-zamandan cok hizli).
    Yukleme sonrasi (ayni thread): edge erisilebilirlik probu + onbellek on-isitmasi."""
    state.status = "yukleniyor"
    try:
        def _make_piper(voice_key: str):
            from tts.engine_piper import PiperEngine
            return PiperEngine(
                voice=config.get(voice_key, "tr_TR-dfki-medium"),
                use_cuda=False,
                pitch_enabled=bool(config.get("tts_pitch_enabled", True)),
            )

        engine_name = config.get("tts_engine", "piper")
        if engine_name == "edge":
            # Birincil: edge-tts (cevrimici). Yedek: Piper (cevrimdisi) — internet
            # kesilirse sergi susmasin diye FallbackEngine otomatik gecer.
            from tts.engine_edge import EdgeEngine
            from tts.engine_base import FallbackEngine
            primary = EdgeEngine(voice=config.get("tts_voice", DEFAULT_TTS_VOICE))
            if config.get("tts_fallback_enabled", True):
                engine = FallbackEngine(primary, _make_piper("tts_fallback_voice"))
                # Acilis probu: edge erisilemiyorsa motor BASTAN Piper'a sabitlenir.
                engine = _probe_edge_or_pin_fallback(engine)
                state.engine = engine
                if isinstance(engine, FallbackEngine):
                    log.info("TTS hazir (edge=%s + cevrimdisi yedek piper=%s).",
                             primary.voice_name, engine.fallback.voice_name)
                else:
                    log.info("TTS hazir (Piper, %s — edge probu basarisiz, motor sabitlendi).",
                             engine.voice_name)
            else:
                state.engine = primary
                log.info("TTS hazir (edge=%s, yedek yok).", primary.voice_name)
        elif engine_name == "elevenlabs":
            # Birincil: ElevenLabs (bulut, KOTALI — her sentez kredi harcar).
            # Yedek zinciri: edge (ucretsiz online) -> Piper (offline). Kredi tavani
            # dolar ya da anahtar/ag yoksa ElevenLabs b"" doner; FallbackEngine
            # otomatik ucretsiz yedege gecer (sergi susmaz, butce asilmaz).
            from tts.engine_elevenlabs import ElevenLabsEngine
            from tts.engine_edge import EdgeEngine
            from tts.engine_base import FallbackEngine
            primary = ElevenLabsEngine(
                voice=config.get("tts_voice", ""),
                api_key=(config.get("tts_elevenlabs_api_key")
                         or os.environ.get("ELEVENLABS_API_KEY", "")),
                model=config.get("tts_elevenlabs_model", "eleven_flash_v2_5"),
                language=config.get("tts_elevenlabs_language", "tr"),
                monthly_cap=config.get("tts_elevenlabs_monthly_credit_cap", 32000),
                usage_path=BASE_DIR / "tts" / "elevenlabs_usage.json",
            )
            if config.get("tts_fallback_enabled", True):
                # 3 katman: elevenlabs -> edge -> piper.
                offline = FallbackEngine(
                    EdgeEngine(voice=config.get("tts_elevenlabs_edge_fallback_voice",
                                                DEFAULT_TTS_VOICE)),
                    _make_piper("tts_fallback_voice"))
                state.engine = FallbackEngine(primary, offline)
                log.info("TTS hazir (elevenlabs=%s + yedek: edge -> piper).",
                         primary.voice_name)
            else:
                state.engine = primary
                log.info("TTS hazir (elevenlabs=%s, yedek yok).", primary.voice_name)
        else:
            if engine_name != "piper":
                log.warning("Bilinmeyen tts_engine '%s' — piper'a dusuluyor.", engine_name)
            state.engine = _make_piper("tts_voice")
            log.info("TTS hazir (Piper, %s).", state.engine.voice_name)
        state.status = "hazir"
    except Exception as e:  # noqa: BLE001 — TTS yuklenemese de sergi devam etsin
        state.status = "hata"
        state.error = str(e)
        log.warning("TTS yuklenemedi: %s", e)
        return
    # On-isitma: motor hazir olduktan sonra AYNI arka plan thread'inde —
    # ilk ziyaretci selamlamayi/menu repliklerini sentez beklemeden duysun.
    try:
        _warm_tts_cache(state, cache, config)
    except Exception as e:  # noqa: BLE001 — isitma hatasi sergiyi durdurmaz
        log.warning("TTS on-isitma hatasi: %s", e)


def create_app(config: dict) -> Flask:
    app = Flask(__name__, static_folder=None)
    app_start = time.monotonic()  # /api/health uptime_s icin

    bridge = LLMBridge(config, BASE_DIR)
    game = GameEngine(bridge=bridge)  # TKM deterministik; kelime turetme (ileride) LLM kullanir
    # Test modu durumu (config.json'dan; 'g' tusu / POST /api/test_mode degistirir).
    test_mode = {"on": bool(config.get("test_mode", False))}
    if test_mode["on"]:
        game.izinli_oyunlar = TEST_OYUNLAR
        game.voice_only = True
    # Flask threaded=True; tek GameEngine instance'i paylasiliyor. Sure-doldu ile
    # manuel cevap/AI-turu ayni anda gelirse durum makinesi bozulmasin diye seri kilit.
    game_lock = threading.Lock()
    # Aktif oyuna en son girdi gelen an: /api/session/new'in "canli oyunu koruma"
    # karari bunu kullanir (sayfa yenilenip oyun sahipsiz kaldiysa eskimis sayilir).
    game_last_input = {"t": 0.0}
    gestures_path = (BASE_DIR / config["gestures_path"]).resolve()
    log_path = (BASE_DIR / config.get("session_log_path", "../logs/session.log")).resolve()
    logger = SessionLogger(log_path, config["ollama_url"], bridge.model)
    logger.start()
    log.info("Oturum logu: %s", log_path)
    # Oyun baslangic/bitis ozetleri de ayni oturum loguna yazilsin (gozlem).
    game.session_logger = logger
    # SERGI ZIYARETCI LOGU: ziyaretci bazli olcum (sure, oyun, skor, anlamsiz
    # cevap, yarida birakma). Ziyaretci yasam dongusu yalniz sergi/test modunda
    # baslatilir (session/new greet); panel/gelistirme kullanimi kayit uretmez.
    sergi_dir = (BASE_DIR / config.get("sergi_log_dir", "../logs/sergi")).resolve()
    sergi = SergiLogger(sergi_dir)
    game.sergi_logger = sergi
    log.info("Sergi ziyaretci logu: %s", sergi_dir)

    # YASAKLI KELIME FILTRESI: kufur/nefret/yasak konu iceren ziyaretci sozu
    # ekrana HIC yazilmaz. Uyari da verilmez — yalnizca "anlamadim" replikleri.
    # Liste ACILISTA yuklenir (ilk sozde gecikme/surpriz olmasin).
    yasakli_acik = yasakli_filtre.filtre_acik(config)
    if yasakli_acik:
        _f = yasakli_filtre.get_filtre(config)
        if not _f.hazir:
            log.error("Yasakli kelime filtresi YUKLENEMEDI — sergi acilmadan once "
                      "ai/yasakli_kelimeler_tr_en.json kontrol edilmeli!")
    else:
        log.warning("Yasakli kelime filtresi KAPALI (yasakli_filtre_enabled=false)")

    def _yasakli_kontrol(text: str, izinli=None):
        """Girdi yasakli mi? Eslesme ya da None. Filtre kapaliysa hep None."""
        if not yasakli_acik or not text:
            return None
        try:
            return yasakli_filtre.get_filtre(config).kontrol(text, izinli=izinli)
        except Exception as e:  # noqa: BLE001 — filtre hatasi sergiyi durdurmasin
            log.warning("Yasakli filtre hatasi (girdi gecirildi): %s", e)
            return None

    def _yasakli_yanit(esl, nereden: str) -> dict:
        """Ziyaretciye donen tek payload. Yasakli metin PAYLOAD'A KONMAZ;
        istemci onu hicbir yerde gostermez. Loga da yalniz kategori yazilir."""
        log.info("Yasakli girdi engellendi [%s]: %s", nereden, esl.sebep())
        logger.log_event(f"Yasakli girdi engellendi ({nereden}): {esl.sebep()}")
        sergi.yasakli(esl.kategori, esl.severity)
        return {
            "blocked": True,
            "yanit": yasakli_filtre.yanit_metni(config),
            "jest_id": yasakli_filtre.VARSAYILAN_JEST,
            "yogunluk": 0.6,
        }

    # Tek seferlik warmup arka planda
    if config.get("warmup_on_start", True):
        def _warm():
            ok = bridge.warmup()
            log.info("Warmup: %s", "OK" if ok else "fail")
        threading.Thread(target=_warm, daemon=True).start()

    # Whisper modeli arka planda yuklensin — HTTP istekleri bunu beklemez.
    whisper_state = WhisperState()
    whisper_size = config.get("whisper_model_size", WHISPER_MODEL_SIZE)
    whisper_device = config.get("whisper_device", WHISPER_DEVICE)
    whisper_compute = config.get("whisper_compute_type", WHISPER_COMPUTE_TYPE)
    if config.get("whisper_enabled", True):
        threading.Thread(
            target=_load_whisper_async,
            args=(whisper_state, whisper_size, whisper_device, whisper_compute),
            daemon=True,
        ).start()

    # TTS motoru arka planda yuklensin — HTTP istekleri bunu beklemez.
    from tts.cache import WavCache
    tts_state = TTSState()
    tts_cache = WavCache(
        BASE_DIR / "tts" / "cache",
        max_files=int(config.get("tts_cache_max", 500)),
        enabled=bool(config.get("tts_cache_enabled", True)),
    )
    if config.get("tts_enabled", True):
        threading.Thread(
            target=_load_tts_async,
            args=(tts_state, config, tts_cache),
            daemon=True,
        ).start()

    @app.route("/")
    def index():
        return send_from_directory(str(WEB_DIR), "AI_Body_v2.html")

    @app.route("/control")
    @app.route("/kontrol")
    def control_panel():
        return send_from_directory(str(WEB_DIR), "Kontrol_Paneli.html")

    @app.get("/api/gestures")
    def api_gestures():
        return send_from_directory(str(gestures_path.parent), gestures_path.name)

    @app.get("/api/emoji_manifest")
    def api_emoji_manifest():
        """Her jest_id icin emoji kare sayilari.

        frames     : {jest_id: kare_sayisi} — ana emoji (geriye donuk uyum).
        varyantlar : {jest_id: [{dizin, kare}, ...]} — ana emoji ("" dizin) + v01, v02 ...
                     Istemci ayni jest tekrar geldiginde farkli bir varyant oynatir
                     (bkz led-panel.js _pickVariant) — ayni duygu hep ayni yuzle cikmasin.
        """
        manifest = {}
        varyantlar = {}
        if EMOJI_BASE_DIR.is_dir():
            for jest_dir in sorted(EMOJI_BASE_DIR.iterdir()):
                if not jest_dir.is_dir():
                    continue
                kayitlar = []
                ana = len(list(jest_dir.glob("frame_*.png")))
                if ana:
                    kayitlar.append({"dizin": "", "kare": ana})
                for alt in sorted(jest_dir.glob("v[0-9][0-9]")):
                    if not alt.is_dir():
                        continue
                    n = len(list(alt.glob("frame_*.png")))
                    if n:
                        kayitlar.append({"dizin": alt.name, "kare": n})
                if kayitlar:
                    manifest[jest_dir.name] = kayitlar[0]["kare"]
                    varyantlar[jest_dir.name] = kayitlar
        resp = jsonify({"fps": EMOJI_FPS, "frames": manifest, "varyantlar": varyantlar})
        # Kiosk tarayicisi profilini gunler boyu tasiyor: bayat manifest,
        # yeni indirilen varyantlarin hic gorunmemesi demek olurdu.
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/assets/<path:filename>")
    def static_assets(filename):
        return send_from_directory(str(ASSETS_DIR), filename)

    @app.get("/api/health")
    def api_health():
        """Watchdog/izleme icin: Ollama canli mi + TTS hazir mi + sunucu uptime."""
        return jsonify({
            "ollama": bridge.is_alive(),
            "model": bridge.model,
            "tts": tts_state.is_ready(),
            "tts_status": tts_state.status,
            "uptime_s": round(time.monotonic() - app_start, 1),
        })

    @app.get("/api/config")
    def api_config():
        """Frontend'in bilmesi gereken sergi sınırları + sesli giriş ayarları."""
        return jsonify({
            "max_user_input_chars": int(config.get("max_user_input_chars", 240)),
            "max_record_seconds": int(config.get("max_record_seconds", 30)),
            "test_mode": test_mode["on"],
            # Sergi ekranindaki surekli sesli giris (VAD) ayarlari. Sergide JS'e
            # dokunmadan config.json'dan ayarlanabilsin diye burada aciga cikarilir.
            "voice_input": {
                "enabled": bool(config.get("voice_input_enabled", True)),
                "autostart": bool(config.get("voice_input_autostart", True)),
                "silence_ms": int(config.get("voice_input_silence_ms", 1000)),
                "min_speech_ms": int(config.get("voice_input_min_speech_ms", 350)),
                # Oyun modu: cevaplar tek kelime ("tas", "bir") — cumle-bitti
                # karari daha erken verilebilir, tur basina ~400 ms kazanc.
                "silence_ms_game": int(config.get("voice_input_silence_ms_game", 600)),
                "min_speech_ms_game": int(config.get("voice_input_min_speech_ms_game", 250)),
                "max_utterance_ms": int(config.get("voice_input_max_utterance_ms", 12000)),
                "onset_mult": float(config.get("voice_input_onset_mult", 2.2)),
                "abs_min_rms": float(config.get("voice_input_abs_min_rms", 0.012)),
                "cooldown_ms": int(config.get("voice_input_cooldown_ms", 400)),
                # Barge-in: AI konusurken (TTS) mikrofon acik kalir; kullanici
                # yeterince yuksek + surekli konusursa TTS kesilip kayit baslar.
                # barge_in_mult: konusma esigi TTS sirasinda bu katsayiyla yukseltilir
                # (echo-cancel artigi AI'yi kendi kendine kesmesin). min_ms: kesme icin
                # gereken surekli yuksek-ses suresi.
                "barge_in": bool(config.get("voice_input_barge_in", True)),
                "barge_in_mult": float(config.get("voice_input_barge_in_mult", 2.2)),
                "barge_in_min_ms": int(config.get("voice_input_barge_in_min_ms", 280)),
                # hold_during_speech=true: AI konusurken KESILMEZ; sirasinda soylenen
                # (bThr ustundeki gercek konusma) biriktirilir, AI cumlesini bitirince
                # cevaba cevrilir. barge_in'in yerine gecer. false ise klasik barge-in.
                "hold_during_speech": bool(config.get("voice_input_hold_during_speech", True)),
                # Tarayici mikrofon DSP bayraklari. Chrome'un noiseSuppression/AGC'si
                # telefon gorusmesi icin tasarlandi; uzak konusmaci + Whisper'da sesi
                # bozabiliyor. A/B testi icin config'ten kapatilabilir.
                "echo_cancellation": bool(config.get("voice_input_echo_cancellation", True)),
                "noise_suppression": bool(config.get("voice_input_noise_suppression", True)),
                "auto_gain": bool(config.get("voice_input_auto_gain", True)),
                # ——— Ortam gurultusu kalibrasyonu ———
                # calibration_enabled=true: mikrofon acilinca calib_ms boyunca
                # KIMSE KONUSMADAN ortam dinlenir; olcumun medyani gurultu tabani,
                # p90'i (calib_headroom ile) MUTLAK ALT ESIK olur. Boylece salonun
                # ugultusu konusma sayilmaz ve abs_min_rms'i sahada elle kismak
                # gerekmez. abs_min_rms yine ALT SINIR: kalibrasyon esigi yalnizca
                # yukseltebilir. Ayrica canli gurultu tabani EMA yerine yuzdelik
                # ile izlenir (gurultulu ortamda EMA kilitleniyordu). false yapmak
                # ESKI davranisi birebir geri getirir.
                "calibration_enabled": bool(config.get("voice_input_calibration_enabled", True)),
                "calib_ms": int(config.get("voice_input_calib_ms", 4000)),
                "calib_headroom": float(config.get("voice_input_calib_headroom", 1.35)),
                # Olculen medyan bunu asarsa kalibrasyon REDDEDILIR (olcum sirasinda
                # konusuldu / mikrofon bozuk): config esikleri + canli taban devreye girer.
                "calib_max_rms": float(config.get("voice_input_calib_max_rms", 0.08)),
                # Canli taban: son floor_window_ms'lik pencerenin en sessiz
                # floor_pct'lik dilimi ortam gurultusu sayilir.
                "floor_window_ms": int(config.get("voice_input_floor_window_ms", 15000)),
                "floor_pct": float(config.get("voice_input_floor_pct", 0.10)),
            },
        })

    @app.get("/api/models")
    def api_models():
        return jsonify({"models": bridge.list_local_models(), "active": bridge.model})

    @app.post("/api/model")
    def api_set_model():
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "model adi bos"}), 400
        changed = bridge.set_model(name)
        if changed:
            config["ollama_model"] = name
            try:
                save_config(config)
            except OSError as e:
                log.warning("config.json yazilamadi: %s", e)
            logger.model_name = name
            logger.log_event(f"Aktif model degisti: {name}")
        return jsonify({"changed": changed, "active": bridge.model})

    @app.post("/api/pull")
    def api_pull():
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "model adi bos"}), 400
        last_status = {"status": "baslatildi"}

        def on_progress(data):
            last_status.update(data)

        ok = bridge.pull_model(name, on_progress)
        if not ok:
            return jsonify({"error": last_status.get("error", "indirme basarisiz"),
                            "status": last_status}), 500
        return jsonify({"ok": True, "name": name, "status": last_status})

    @app.post("/api/send")
    def api_send():
        payload = request.get_json(silent=True) or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return jsonify({"error": "metin bos"}), 400
        max_chars = int(config.get("max_user_input_chars", 240))
        if len(text) > max_chars:
            # Sergi koruma: cok uzun prompt -> Ollama'yi kilitlemeyelim
            return jsonify({
                "error": "too_long",
                "max": max_chars,
                "len": len(text),
            }), 413
        # Yasakli girdi (panelden yazilan metin de dahil): LLM'e GITMEZ, ekrana
        # yazilmaz — yalniz "anlamadim" repligi doner.
        esl = _yasakli_kontrol(text)
        if esl is not None:
            return jsonify(_yasakli_yanit(esl, "sohbet"))
        if test_mode["on"]:
            # Test gunu: sohbet kapali — LLM'e gitmeden nazik oyun yonlendirmesi.
            # (Frontend zaten oyuna yonlendirir; bu backend guvencesidir.)
            logger.log_event("Test modu: sohbet istegi oyuna yonlendirildi")
            sergi.sohbet()
            return jsonify({
                "yanit": TEST_SOHBET_KAPALI_TEXT,
                "jest_id": SESSION_GREETING_JEST,
                "yogunluk": 0.8,
                "meta": {"test_mode": True},
            })
        result = bridge.request(text)
        if result is None or "error" in result:
            err = (result or {}).get("error", "no_response")
            meta = dict((result or {}).get("meta") or {})
            logger.log_error(text, result or {"error": err})
            # Sergi dayanikliligi: 500 yerine HTTP 200 + nazik "bekle" yaniti.
            # Kiosk hata kutusu gostermez; ziyaretci dogal bir cevap duyar/gorur.
            # 'bekle' jesti gestures.json'da mevcut (donen ibre — saat).
            meta.update({"degraded": True, "error": err})
            return jsonify({
                "yanit": "Şu an düşünemiyorum, birazdan tekrar dener misin?",
                "jest_id": "bekle",
                "yogunluk": 0.4,
                "meta": meta,
            })
        logger.log_request(text, result)
        return jsonify(result)

    @app.post("/api/filter_check")
    def api_filter_check():
        """Metin yasakli mi? (Kontrol paneli, sozu EKRANA YAZMADAN once sorar.)

        Sesli yolda gerek yoktur — /api/transcribe metni zaten hic gondermez.
        Yanit yasakli metni TASIMAZ; yalnizca 'anlamadim' repligi doner."""
        payload = request.get_json(silent=True) or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return jsonify({"blocked": False})
        try:
            beklenen = game.stt_hints()
        except Exception:  # noqa: BLE001
            beklenen = []
        esl = _yasakli_kontrol(text, izinli=beklenen)
        if esl is None:
            return jsonify({"blocked": False})
        return jsonify(_yasakli_yanit(esl, "panel"))

    @app.post("/api/clear_history")
    def api_clear():
        bridge.clear_history()
        logger.log_event("Konusma gecmisi sifirlandi")
        return jsonify({"ok": True})

    @app.post("/api/session/new")
    def api_session_new():
        """Yeni ziyaretci selami: sohbet gecmisini ve oyun durumunu temizle.

        Bu akista LLM'e gidilmez; karsilama sabit kalir ki kiosk her ziyaretciye
        temiz ve hizli bir acilis yapsin.

        KORUMA: Aktif (girdi almaya devam eden) bir oyun (quiz VEYA kelime)
        yalnizca "ziyaretci gitti" kararlariyla (attract/idle_reset/end_to_eyes)
        sifirlanabilir. Acik unutulmus ikinci bir sergi sekmesi/istemci
        gurultuyle 'greet' atarsa ORTADAKI OYUN bozulmasin. Sayfa yenilenip
        oyun sahipsiz kaldiysa (60+ sn girdisiz) eskimis sayilir ve sifirlamaya
        izin verilir — yoksa kiosk sonsuza dek "oyun aktif" diye selam veremezdi.
        409 yaniti phase VE turn_id tasir: istemci fazi geri yukleyip kendini
        onarir; jetonu da tazeler ki sonraki cevap gecerli turla gitsin (jetonsuz
        istemci /api/game/input'ta korumasiz kalirdi).
        """
        payload = request.get_json(silent=True) or {}
        reason = str(payload.get("reason") or "eski_istemci")[:24]
        with game_lock:
            aktif_oyun = ((game.phase == "quiz" and game.quiz_turn is not None)
                          or (game.phase == "kelime" and game.word_turn is not None))
            taze = (time.time() - game_last_input["t"]) < 60
            if (aktif_oyun and taze
                    and reason not in ("attract", "idle_reset", "end_to_eyes")):
                logger.log_event(
                    f"session/new REDDEDILDI: aktif oyun korundu (neden={reason})")
                return jsonify({"error": "game_active", "phase": game.phase,
                                "turn_id": game.turn_id}), 409
        # Sergi ziyaretci logu: "ziyaretci gitti" nedenleri acik kaydi kapatir;
        # greet yeni ziyaretci acar (yalniz sergi/test modunda — panel kullanimi
        # ziyaretci sayilmaz). visitor_start acik kaydi zaten guvenle kapatir.
        if reason in ("attract", "idle_reset", "end_to_eyes"):
            sergi.visitor_end(reason)
        elif test_mode["on"]:
            sergi.visitor_start(reason)
        else:
            sergi.visitor_end(reason)   # test modu kapaliyken acik kayit birakma
        bridge.clear_history()
        if test_mode["on"]:
            # Test gunu: "merhaba" -> selamla + dogrudan oyun secimi (sohbet yok).
            with game_lock:
                game.exit()
                menu = game.start()
            menu["yanit"] = _test_greeting_yanit()
            menu["jest_id"] = SESSION_GREETING_JEST
            menu["yogunluk"] = SESSION_GREETING_YOGUNLUK
            logger.log_event(
                f"Yeni ziyaretci (test modu): selamlama + oyun menusu [neden={reason}]")
            return jsonify(menu)
        with game_lock:
            game.exit()
        logger.log_event(f"Yeni ziyaretci: selamlama ile temiz oturum [neden={reason}]")
        return jsonify({
            "ok": True,
            "jest_id": SESSION_GREETING_JEST,
            "yogunluk": SESSION_GREETING_YOGUNLUK,
            "yanit": SESSION_GREETING_TEXT,   # on-isitma ile ayni sabit (anahtar isabeti)
            "phase": "idle",
            "buttons": [],
        })

    # ——— Test modu (sergi test gunu: sinirli menu + sohbet kapali) ————————
    @app.get("/api/test_mode")
    def api_test_mode_get():
        return jsonify({"on": test_mode["on"], "games": list(TEST_OYUNLAR)})

    @app.post("/api/test_mode")
    def api_test_mode_set():
        """Test modunu ac/kapa. Body {"on": bool} verilirse o degere, verilmezse
        toggle. Aktif oyun sifirlanir (menude eski butonlar kalmasin)."""
        payload = request.get_json(silent=True) or {}
        on = payload.get("on")
        on = (not test_mode["on"]) if on is None else bool(on)
        test_mode["on"] = on
        if not on:
            # Sergi modu kapandi: acik ziyaretci kaydi kaybolmasin.
            sergi.visitor_end("test_mode_kapandi")
        with game_lock:
            game.izinli_oyunlar = TEST_OYUNLAR if on else None
            game.voice_only = on
            game.exit()
        config["test_mode"] = on
        # Kalicilik: diskteki config tazelenip YALNIZ bu anahtar yazilir
        # (calisma-zamani degisikliklerini diske sizdirmamak icin). Disk bozuksa
        # (JSONDecodeError=ValueError!) bellekteki kopyaya dusulur; kalicilik
        # hatasi HTTP 500 uretmez — bellek durumu zaten degisti, 200 donmeli.
        try:
            disk = load_config()
        except (OSError, ValueError) as e:
            log.warning("config.json okunamadi (%s) — bellekteki kopya yazilacak", e)
            disk = dict(config)
        disk["test_mode"] = on
        try:
            save_config(disk)
        except OSError as e:
            log.warning("config.json yazilamadi: %s", e)
        logger.log_event("Test modu " + ("ACIK (yalniz " + ", ".join(TEST_OYUNLAR) + ")"
                                         if on else "KAPALI"))
        return jsonify({"on": on, "games": list(TEST_OYUNLAR)})

    # ——— Oyun modu (Kelime Türetme; deterministik akis, AI kelimeleri temali havuzdan) ————
    @app.post("/api/game/start")
    def api_game_start():
        # KORUMA: /api/session/new ile ayni kural — CANLI bir oyun start ile
        # sifirlanmasin. Fazi kaybetmis (sayfa yenilenmis / payload kacirmis)
        # bir istemci "oyun oynayalim" duyunca start cagirir ve ORTADAKI
        # yarismayi menuye dondururdu. 409 + phase doner; istemci fazi geri
        # yukler, sonraki girdi oyuna akar (kendiliginden onarim). 409 phase ile
        # BIRLIKTE turn_id tasir: fazi geri yukleyen istemci jetonsuz kalirsa
        # sonraki cevabi /api/game/input'ta dogrulanamaz ve yanlis soruyu tuketir.
        with game_lock:
            aktif_oyun = ((game.phase == "quiz" and game.quiz_turn is not None)
                          or (game.phase == "kelime" and game.word_turn is not None))
            taze = (time.time() - game_last_input["t"]) < 60
            if aktif_oyun and taze:
                logger.log_event("game/start REDDEDILDI: aktif oyun korundu")
                return jsonify({"error": "game_active", "phase": game.phase,
                                "turn_id": game.turn_id}), 409
            result = game.start()
        game_last_input["t"] = time.time()
        logger.log_event("Oyun baslatildi (kelime turetme)")
        return jsonify(result)

    @app.post("/api/game/input")
    def api_game_input():
        payload = request.get_json(silent=True) or {}
        text = (payload.get("text") or "").strip()
        timeout = bool(payload.get("timeout"))
        # button=True: panel butonundan geldi — sesli girdiden farkli olarak
        # cikis komutlari aktif quiz'de de gecerli (STT gurultusu sayilmaz).
        button = bool(payload.get("button"))
        # TUR JETONU (soru kaymasi korumasi): istemci, cevabini HANGI payload'a
        # verdigini bildirir. Jeton sunucudakinden farkliysa girdi BAYAT'tir —
        # soru TUKETILMEDEN reddedilir. Bayat girdi kaynaklari: AI konusurken
        # birikip TTS biter bitmez gonderilen kayit, tek cevabin VAD ile ikiye
        # bolunmesi, soru duyulmadan baslayan sayacin gec timeout'u.
        # GERIYE DONUK UYUM anahtarin VARLIGINA bakar: jeton alanini HIC
        # gondermeyen istemci (eski panel/sekme) eskisi gibi kabul edilir.
        # turn_id=null GONDEREN istemci jeton destekliyor ama senkronu KAYBETMIS
        # demektir (orn. 409 game_active ile fazi geri yukleyip jetonsuz kalmak) —
        # "None ise atla" mantigi bu durumda korumayi sessizce kapatiyor, girdi
        # dogrulanmadan o anki soruyu tuketiyordu. Artik bayat sayilir: istemci
        # 409'dan gercek jetonu ogrenir, sonraki soz dogru turla gider.
        jeton_gonderildi = "turn_id" in payload
        client_turn = payload.get("turn_id")
        if not text and not timeout:
            return jsonify({"error": "metin bos"}), 400
        # Sergi koruma: oyun girdileri kisa olmali
        if len(text) > 60:
            text = text[:60]
        # Yasakli girdi: oyun motoruna GIRMEZ (tur tuketilmez, soru kaymaz);
        # ziyaretci ayni soruya tekrar cevap verebilir. Sesli yolda bu zaten
        # /api/transcribe'da kesilir; burasi panel/yazi yolunun guvencesidir.
        if text and not timeout:
            try:
                beklenen = game.stt_hints()
            except Exception:  # noqa: BLE001
                beklenen = []
            esl = _yasakli_kontrol(text, izinli=beklenen)
            if esl is not None:
                payload = _yasakli_yanit(esl, "oyun")
                payload.update({"phase": game.phase, "turn_id": game.turn_id})
                return jsonify(payload)
        with game_lock:
            if jeton_gonderildi:
                try:
                    ct = int(client_turn)
                except (TypeError, ValueError):
                    ct = None          # null / bozuk jeton = senkron kaybi
                if ct != game.turn_id:
                    logger.log_event(
                        f"game/input BAYAT girdi reddedildi (jeton {client_turn} != "
                        f"{game.turn_id}){' [timeout]' if timeout else ''}: {text[:40]!r}")
                    return jsonify({"error": "stale_input",
                                    "turn_id": game.turn_id,
                                    "phase": game.phase}), 409
            # GEC TIMEOUT: aktif tur yoksa (yarisma bitti, menu, hazir-oncesi,
            # idle) handle() timeout'u girdi sanip _start_quiz/_start_kelime/start
            # cagiriyor — sahada "biten oyun kendiliginden yeniden basladi".
            # Jeton bunu cogu durumda keser (istemci bitiste sayaci durdurur) ama
            # jetonsuz istemci ya da tam yarisi kazanmis bir istek hâlâ gecebilir:
            # aktif tur yoksa timeout HICBIR SEY yapmaz, tur da tuketilmez.
            if timeout and not ((game.phase == "kelime" and game.word_turn is not None)
                                or (game.phase == "quiz" and game.quiz_turn is not None)):
                logger.log_event(
                    f"game/input GEC timeout yoksayildi (aktif tur yok, faz={game.phase})")
                return jsonify({"error": "stale_input",
                                "turn_id": game.turn_id,
                                "phase": game.phase}), 409
            result = game.handle(text, timeout=timeout, button=button)
        game_last_input["t"] = time.time()
        if text and not timeout:
            sergi.aktivite()   # gercek girdi (buton dahil) aktif sureyi tazeler
        if result.get("kind") == "round":
            logger.log_event(
                f"Oyun turu: kullanici={result.get('user_move')} ai={result.get('ai_move')} "
                f"sonuc={result.get('outcome')} skor={result.get('score')} jest={result.get('jest_id')}"
            )
        elif result.get("game") == "kelime":
            logger.log_event(
                f"Kelime: kind={result.get('kind')} kullanici_kelime={result.get('user_word')} "
                f"harf={result.get('required_letter')} outcome={result.get('outcome')} "
                f"skor={result.get('score')}"
            )
        elif result.get("ended"):
            logger.log_event("Oyundan cikildi")
        return jsonify(result)

    @app.post("/api/game/ai_turn")
    def api_game_ai_turn():
        """Kelime oyunu: sira AI'dayken AI'nin kelimesini/pes'ini uretir (LLM burada)."""
        with game_lock:
            result = game.ai_turn()
        if result.get("ai_error"):
            log.warning("Kelime AI turu: Ollama erisilemedi — gercek pes DEGIL (gorevli kontrol etsin)")
            logger.log_event("UYARI: Kelime AI turunda Ollama erisilemedi (gercek pes degil)")
        logger.log_event(
            f"Kelime AI turu: kind={result.get('kind')} kelime={result.get('ai_word')} "
            f"harf={result.get('required_letter')} outcome={result.get('outcome')}"
        )
        return jsonify(result)

    @app.post("/api/game/exit")
    def api_game_exit():
        with game_lock:
            result = game.exit()
        logger.log_event("Oyun kapatildi")
        return jsonify(result)

    @app.get("/api/transcribe/status")
    def api_transcribe_status():
        return jsonify({
            "status": whisper_state.status,
            "ready": whisper_state.is_ready(),
            "error": whisper_state.error,
            "model": whisper_size,
            "device": whisper_state.device or whisper_device,
            "compute_type": whisper_state.compute_type or whisper_compute,
            "language": WHISPER_LANGUAGE,
        })

    @app.post("/api/transcribe")
    def api_transcribe():
        """Tarayicidan gelen ses (multipart 'audio' veya raw body) -> turkce metin.
        faster-whisper PyAV ile WebM/Opus, MP3, WAV vb. format'lari decode eder.
        """
        if not whisper_state.is_ready():
            return jsonify({
                "error": "whisper_not_ready",
                "status": whisper_state.status,
                "detail": whisper_state.error,
            }), 503

        # Audio bytes'i topla: once multipart 'audio' alani, yoksa raw request body
        audio_bytes = b""
        if "audio" in request.files:
            audio_bytes = request.files["audio"].read()
        else:
            audio_bytes = request.get_data() or b""
        if not audio_bytes:
            return jsonify({"error": "audio_empty"}), 400

        # Baglam bias'i: oyun modunda kisa komut sozlugu, yoksa genel sergi
        # sozlugu. Serbest LLM duzeltmesi DEGIL — yalnizca initial_prompt degisir.
        ctx = (request.form.get("context") or request.args.get("context") or "").strip()
        if ctx == "game":
            init_prompt = config.get("whisper_initial_prompt_game", WHISPER_GAME_PROMPT)
            # DINAMIK BIAS: olasi cevaplar zaten dosyada yazili (menu secenekleri,
            # o anki quiz sorusunun kabul cevaplari, "basla" onayi). Oyun motoru
            # fazina gore listeyi verir; Whisper cozumlemeyi bu kelimelere ceker.
            # Serbest duzeltme DEGIL: cocuk baska bir sey derse o yazilir.
            try:
                hints = game.stt_hints()
            except Exception as e:  # noqa: BLE001 — ipucu alinamazsa temel prompt yeter
                log.debug("stt_hints alinamadi: %s", e)
                hints = []
            if hints:
                init_prompt = f"{init_prompt} Olası cevaplar: {', '.join(hints)}."
        else:
            init_prompt = config.get("whisper_initial_prompt", WHISPER_INITIAL_PROMPT)

        # Istemci ipuclari: trim_ms = konusma oncesi kirpilacak sure (kayit surekli
        # acik; bastaki sessizlik/TTS yankisi Whisper'a girmesin — hem hiz hem
        # dogruluk). echo_text = kayit AI konusurken basladiysa az once calan TTS
        # metni (transkript salt yankiysa atilir).
        try:
            trim_ms_req = int(request.form.get("trim_ms") or request.args.get("trim_ms") or 0)
        except ValueError:
            trim_ms_req = 0
        echo_text = (request.form.get("echo_text") or "").strip()

        # STT ONCESI trim + opsiyonel gurultu bastirma — model KILIDINDAN ONCE
        # (CPU isi, kilidi tutmaz). Basarisiz/kapali ise ham bytes ile devam edilir.
        prepared, denoise_ms, trimmed_ms = _prepare_audio(audio_bytes, config, trim_ms_req)
        stt_input = prepared if prepared is not None else io.BytesIO(audio_bytes)

        # Transcribe — re-entrancy lock (tek model, tek thread guvenli kullanim).
        # TIMEOUT'LU acquire: onceki bir istek native katmanda takilirsa (CUDA
        # kutuphane hatasi vb.) sonraki istekler sonsuza dek beklemesin — sergi
        # ekrani 503 alir, mikrofon dongusu kendini toparlar.
        if not whisper_state._lock.acquire(timeout=30):
            log.warning("Transkripsiyon kilidi 30 sn'de alinamadi — onceki istek takili.")
            return jsonify({"error": "transcribe_busy"}), 503
        dropped = []  # halusinasyon diye atilan segmentler (log/teshis)
        retried = False  # bos sonuc kurtarma turu calisti mi (log/teshis)
        t0 = time.perf_counter()  # saf STT suresi (kilit alindiktan sonra)

        def _stt_gecir(inp, vad_params, siki_filtre=False):
            """Tek transkripsiyon gecisi (kilit CAGIRANDA). -> (text, info)

            siki_filtre: kurtarma turu dusuk VAD esigiyle calisir — gurultuden
            metin uydurma riski yuksektir. Modelin KENDI guven olcutleriyle ele:
            sessizlik olasiligi yuksek ya da olasiligi cok dusuk segmentler atilir.
            Ilk (normal) geciste dokunulmaz — kisik gercek konusma yanmasin."""
            segments, info = whisper_state.model.transcribe(
                inp,
                language=WHISPER_LANGUAGE,
                vad_filter=True,
                vad_parameters=vad_params,
                # Dogruluk icin beam arama (eski greedy=1 oto-VAD parcali sesinde
                # cok yanlis okuyordu). config.whisper_beam_size ile ayarlanir;
                # CPU/small'da 5 ~1 sn ek gecikme getirir, sergide dogruluk onceliklidir.
                beam_size=int(config.get("whisper_beam_size", 5)),
                condition_on_previous_text=False,
                initial_prompt=(init_prompt or None),
                # Zaman damgasi kullanilmiyor — token uretimini azaltir (daha hizli).
                without_timestamps=True,
            )
            parts = []
            for seg in segments:  # generator: asil hesap bu dongude olur
                s = seg.text.strip()
                if not s:
                    continue
                if _stt_is_hallucination(s):
                    dropped.append(s)
                    continue
                if siki_filtre and (getattr(seg, "no_speech_prob", 0.0) > 0.5
                                    or getattr(seg, "avg_logprob", 0.0) < -1.2):
                    dropped.append(s)
                    continue
                parts.append(s)
            return " ".join(parts).strip(), info

        try:
            # Ic VAD siki: varsayilan min_silence 2000 ms — 1-3 sn'lik sergi
            # cumlelerinde bastaki/sondaki sessizligi hic kirpmiyordu (bosuna
            # cozumleme + kuyruk halusinasyonu). 300/200 ms sergi icin yeterli.
            vad_params = {
                "min_silence_duration_ms": int(config.get("whisper_vad_min_silence_ms", 300)),
                "speech_pad_ms": int(config.get("whisper_vad_speech_pad_ms", 200)),
            }
            text, info = _stt_gecir(stt_input, vad_params)
            # KURTARMA TURU ("defalarca duyamadim" onlemi): ilk gecis bos dondu
            # ama istemci konusma ALGILADI (RMS esigi asilmadan gonderim olmaz).
            # Iki olasi kayip noktasi var: (1) trim/denoise on-islemesi sesi
            # bozdu, (2) ic VAD kisik konusmayi yuttu. HAM bytes + dusuk VAD
            # esigiyle BIR kez daha dene — yalnizca basarisizlikta calisir,
            # tipik yolda ek maliyet sifir. Yanki/halusinasyon filtreleri
            # kurtarma metnine de aynen uygulanir.
            if not text:
                retried = True
                text, info = _stt_gecir(io.BytesIO(audio_bytes),
                                        dict(vad_params, threshold=0.4),
                                        siki_filtre=True)
            stt_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            log.warning("Transkripsiyon hatasi: %s", e)
            return jsonify({"error": "transcribe_failed", "detail": str(e)}), 500
        finally:
            whisper_state._lock.release()
        if dropped:
            log.info("STT halusinasyon atildi: %s", " | ".join(dropped))
        # TTS yankisi filtresi: kayit AI konusurken basladiysa ve transkript az
        # once calan cumlenin kendisiyse kullanici girdisi DEGILDIR — at.
        # (AI'nin kendi sorusunu cevap sanmasi = sahadaki "yanlis aliyor".)
        is_echo = _stt_is_tts_echo(text, echo_text)
        if is_echo:
            log.info("STT TTS yankisi atildi: %s", text)
            text = ""
        # Performans izleme noktasi: sahada hedef ~1 sn (GPU turbo). Belirgin
        # artis = CPU'ya dusulmus ya da VRAM taskini — /api/transcribe/status'a bak.
        log.info("STT %d ms%s%s%s | ses %.1f sn | baglam=%s",
                 stt_ms, (f" | denoise {denoise_ms} ms" if denoise_ms else ""),
                 (f" | trim {trimmed_ms} ms" if trimmed_ms else ""),
                 (" | kurtarma turu" if retried else ""),
                 getattr(info, "duration", 0.0), ctx or "sohbet")
        # Sergi ziyaretci logu: bos sonuc = "duyamadim" (anlamsiz cevap sayilir),
        # yanki = TTS'in kendi sesi. Ziyaretci acik degilse sessizce yok sayilir.
        sergi.stt(bos=not text, yanki=is_echo, kurtarma=retried,
                  stt_ms=stt_ms, ses_sn=getattr(info, "duration", 0.0))

        # Teshis kaydi (whisper_debug_save_audio): gercek ortamdan ornek toplayip
        # model/ayar adaylarini ayni set uzerinde kiyaslamak icin.
        if config.get("whisper_debug_save_audio", False):
            try:
                dbg_dir = ROOT_DIR / "logs" / "stt_debug"
                dbg_dir.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
                (dbg_dir / f"{stamp}.webm").write_bytes(audio_bytes)
                with open(dbg_dir / "transcripts.log", "a", encoding="utf-8") as f:
                    f.write(f"{stamp}.webm\t{getattr(info, 'duration', 0.0):.1f}s"
                            f"\t{text}\t[atilan: {' | '.join(dropped)}]\n")
            except Exception as e:  # noqa: BLE001 — teshis kaydi sergiyi durdurmasin
                log.warning("STT debug kaydi yazilamadi: %s", e)

        meta = {
            "duration_s": getattr(info, "duration", 0.0),
            "language": getattr(info, "language", WHISPER_LANGUAGE),
            "language_prob": getattr(info, "language_probability", 0.0),
            "stt_ms": stt_ms,
            "denoise_ms": denoise_ms,
            "trim_ms": trimmed_ms,
            "retry": retried,
        }
        if not text:
            return jsonify({"text": "", "meta": meta,
                            "warning": "tts_echo" if is_echo else "no_speech"})

        # ——— YASAKLI KELIME FILTRESI ————————————————————————————————
        # Ziyaretci sozu bu noktadan SONRA istemciye gider ve ekrana yazilir.
        # Yasakliysa metin HIC gonderilmez: sergi ekrani gostermek istese bile
        # elinde metin olmaz. Oyun motoruna da gitmez — tur tuketilmez, sayac
        # islemeye devam eder, ziyaretci bambaska bir sey soyleyebilir.
        # izinli: o turun beklenen cevaplari ("güzel"in ziddi "çirkin" gibi) —
        # AI'nin kendi sorusunda gecen kelime cevap olarak engellenmemeli.
        try:
            beklenen = game.stt_hints() if ctx == "game" else []
        except Exception:  # noqa: BLE001 — ipucu alinamazsa filtre yine calisir
            beklenen = []
        esl = _yasakli_kontrol(text, izinli=beklenen)
        # TESHIS (yasakli_debug): filtreden GECEN sozler de metniyle loglanir —
        # "kufur ekrana yazildi" sikayetinde Whisper'in tam olarak ne yazdigini
        # gormek icin tek yol budur (normal calismada metin HIC loglanmaz).
        # Sergi gununde KAPATILMALI: ziyaretci sozlerini diske yazar.
        if config.get("yasakli_debug", False):
            logger.log_event(
                f"YASAKLI-TESHIS: {'ENGEL' if esl else 'gecti'} | metin={text!r}"
                f" | baglam={ctx or 'sohbet'} | muaf={list(beklenen)[:4]}"
                + (f" | sebep={esl.sebep()} terim={esl.terim!r}" if esl else ""))
        if esl is not None:
            payload = _yasakli_yanit(esl, "ses")
            payload.update({"text": "", "meta": meta, "warning": "blocked"})
            return jsonify(payload)

        # Sergi koruma: cok uzun konusma -> kirp (ses giris akisini kilitlemeyelim)
        max_chars = int(config.get("max_user_input_chars", 240))
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"
            truncated = True
        return jsonify({"text": text, "meta": meta, "truncated": truncated})

    @app.get("/api/speak/status")
    def api_speak_status():
        return jsonify({
            "status": tts_state.status,
            "ready": tts_state.is_ready(),
            "error": tts_state.error,
            "engine": config.get("tts_engine", "piper"),
            "voice": config.get("tts_voice", DEFAULT_TTS_VOICE),  # QW-5: edge varsayilani
            "enabled": bool(config.get("tts_enabled", True)),
            "autoplay": bool(config.get("tts_autoplay", True)),
        })

    @app.post("/api/speak")
    def api_speak():
        """Metin + jest_id + yogunluk -> duyguya gore tonlanmis WAV ses."""
        if not config.get("tts_enabled", True):
            return jsonify({"error": "tts_disabled"}), 503
        payload = request.get_json(silent=True) or {}
        text = (payload.get("text") or "").strip()
        jest_id = (payload.get("jest_id") or "").strip() or None
        try:
            yogunluk = float(payload.get("yogunluk", 0.7))
        except (TypeError, ValueError):
            yogunluk = 0.7
        if not text:
            return jsonify({"error": "metin bos"}), 400
        # Sergi koruma: asiri uzun metni kirp (CPU'yu kilitlemeyelim)
        max_chars = int(config.get("max_user_input_chars", 240)) * 2
        if len(text) > max_chars:
            text = text[:max_chars]
        if not tts_state.is_ready():
            return jsonify({
                "error": "tts_not_ready",
                "status": tts_state.status,
                "detail": tts_state.error,
            }), 503
        # Seslendirilecek sey kalmadiysa (yalnizca emoji/isaret) sessizlik don —
        # hata donmek cumlenin KALAN parcalarini da susturur (bkz _sessiz_wav).
        from tts.text_norm import seslendirme_metni
        if not seslendirme_metni(text):
            return Response(_sessiz_wav(), mimetype="audio/wav",
                            headers={"Cache-Control": "no-store"})

        # Anahtar turetimi + sentez ortak yardimcida — on-isitma da AYNI yolu kullanir.
        try:
            audio = _tts_synth_cached(tts_state, tts_cache, config, text, jest_id, yogunluk)
        except Exception as e:  # noqa: BLE001
            log.warning("TTS sentez hatasi: %s", e)
            return jsonify({"error": "tts_failed", "detail": str(e)}), 500
        if not audio:
            return jsonify({"error": "tts_empty"}), 500
        return Response(audio, mimetype="audio/wav",
                        headers={"Cache-Control": "no-store"})

    @app.route("/<path:filename>")
    def static_files(filename):
        # API yollari yukaridaki net route'larda kalmali; catch-all sadece web dosyalari icin.
        resp = send_from_directory(str(WEB_DIR), filename)
        # app.js/control.js/*.html degisince tarayici ESKI surumu onbellekten
        # vermesin (kalici profilli kiosk tarayicisi inatci): her seferinde
        # yeniden dogrula. Aksi halde JS degisiklikleri "gorunmez" kalir.
        if filename.rsplit(".", 1)[-1].lower() in ("js", "css", "html"):
            resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp

    # CORS: sadece localhost; basit acik politika (tek bilgisayar)
    @app.after_request
    def add_cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    app.config["_logger"] = logger
    app.config["_sergi"] = sergi
    return app


def _kill_stale_kiosk():
    """Onceki BASLAT'tan kalan sergi tarayicisini kapat (tek sergi sayfasi kurali).

    Ayni .tarayici_profili'ne her calistirmada YENI sekme/pencere eklenir; eski
    sergi sayfasi arka planda calismaya (mikrofonu dinlemeye) devam eder ve
    gorunmez bir 'hayalet' istemci olur: gurultu duyunca selam/oturum sifirlama
    cagirir, gorunur ekrandaki AKTIF OYUNU ortasinda bozar. Kiosk profili sergiye
    ozel oldugundan yalnizca o profili kullanan tarayici surecleri kapatilir."""
    try:
        import psutil
    except ImportError:
        return
    oldurulen = 0
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            ad = (p.info["name"] or "").lower()
            if not (ad.startswith("chrome") or ad.startswith("msedge")):
                continue
            cmd = " ".join(p.info["cmdline"] or ())
            if ".tarayici_profili" in cmd:
                p.kill()
                oldurulen += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if oldurulen:
        log.info("Eski sergi tarayicisi kapatildi (%d surec) — taze sayfa acilacak", oldurulen)
        import time as _t
        _t.sleep(1.0)   # profil kilidi (SingletonLock) birakilsin


def _find_kiosk_browser():
    """Chrome/Edge exe yolu (sergi bayraklari icin). Bulunamazsa None."""
    import shutil
    for name in ("chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    for c in (
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ):
        if os.path.exists(c):
            return c
    return None


def open_browsers(host: str, port: int, delay_sec: float = 1.2,
                  open_control: bool = True, kiosk: bool = True,
                  fullscreen: bool = True) -> None:
    """Sunucu kalktiktan sonra sekmeleri ac.

    open_control=False (sergi profili: web_open_control=false): YALNIZ sergi
    ekrani acilir — ziyaretci kontrol paneline erisemez; ekran panelsiz surucu
    (app.js drv*) ile kendi basina calisir.

    kiosk=True (web_kiosk_browser): Chrome/Edge ayri profil + sergi bayraklariyla
    acilir — mikrofon izni OTOMATIK verilir (soru cikmaz) ve ses/TTS ilk dokunusu
    beklemez. Bayraklar ancak YENI tarayici surecinde islediginden ayri
    --user-data-dir sart (acik Chrome'a sekme eklense bayraklar yok sayilirdi).

    fullscreen=True (web_fullscreen): pencere dogrudan TAM EKRAN acilir
    (--start-fullscreen; F11 ile cikilabilir — kilitli --kiosk modu DEGIL,
    operator gerekirse cikabilsin). Yalniz kiosk tarayici yolunda gecerli.
    """
    def _open():
        import time
        time.sleep(delay_sec)
        base = f"http://{host}:{port}"
        urls = [f"{base}/"] + ([f"{base}/control"] if open_control else [])
        if kiosk:
            exe = _find_kiosk_browser()
            if exe:
                import subprocess
                # Eski calistirmadan kalan sergi sayfasi 'hayalet istemci' olarak
                # oturum sifirlayip aktif oyunu bozabiliyor — once onu kapat.
                _kill_stale_kiosk()
                profil = Path(__file__).resolve().parent.parent / ".tarayici_profili"
                try:
                    subprocess.Popen([
                        exe,
                        f"--user-data-dir={profil}",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--autoplay-policy=no-user-gesture-required",
                        "--use-fake-ui-for-media-stream",
                        # --test-type: Chromium'un "Desteklenmeyen komut satiri
                        # isareti kullaniyorsunuz" sari uyari cubugunu bastirir.
                        # Mikrofon otomatik izni aynen calisir.
                        "--test-type",
                    ] + (["--start-fullscreen"] if fullscreen else []) + urls)
                    return
                except Exception as e:  # noqa: BLE001
                    log.warning("Sergi tarayicisi acilamadi (%s) — varsayilana dusuluyor", e)
            else:
                log.warning("Chrome/Edge yok — varsayilan tarayici (mikrofon izni sorulabilir)")
        try:
            webbrowser.open_new(urls[0])
            if open_control:
                # ikinci sekme ayni pencereye gelsin
                webbrowser.open_new_tab(urls[1])
        except Exception as e:
            log.warning("Tarayici acilamadi: %s — manuel ac: %s", e, base)
    threading.Thread(target=_open, daemon=True).start()


def _port_in_use(host: str, port: int) -> bool:
    """Port zaten dinleniyor mu? Windows'ta SO_REUSEADDR yuzunden AYNI porta
    birden cok sunucu 'basariyla' baglanabiliyor (BASLAT.bat iki kez calistirilinca
    istekler rastgele/eski kopyaya gider — sahada 'bazen cevap yok' olarak gorulur).
    Bu yuzden bind denemesi degil, fiilen BAGLANARAK kontrol ederiz."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def main() -> None:
    config = load_config()
    host = "127.0.0.1"
    port = int(config.get("web_port", 5057))
    if _port_in_use(host, port):
        log.error("Port %d zaten kullanimda — AICAN muhtemelen ACIK. Ikinci kopya "
                  "baslatilmadi. Once eski pencereyi kapatin (veya gorev "
                  "yoneticisinden python'u sonlandirin).", port)
        return
    app = create_app(config)
    open_control = bool(config.get("web_open_control", True))
    kiosk = bool(config.get("web_kiosk_browser", True))
    fullscreen = bool(config.get("web_fullscreen", True))
    log.info("AI Body web sunucusu: http://%s:%d", host, port)
    log.info("  Sergi:          http://%s:%d/%s", host, port,
             " (tam ekran)" if fullscreen else "")
    if open_control:
        log.info("  Kontrol paneli: http://%s:%d/control", host, port)
    else:
        log.info("  Kontrol paneli: ACILMAYACAK (web_open_control=false — sergi modu)")
    open_browsers(host, port, open_control=open_control, kiosk=kiosk,
                  fullscreen=fullscreen)
    try:
        # use_reloader=False -> warmup ve iki sekme acmayi tek seferde calistirir
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    finally:
        sergi = app.config.get("_sergi")
        if sergi:
            try:
                sergi.close()   # acik ziyaretci kaydi kaybolmasin
            except Exception as e:
                log.warning("Sergi logu kapanis hatasi: %s", e)
        logger = app.config.get("_logger")
        if logger:
            try:
                logger.end()
            except Exception as e:
                log.warning("Oturum kapanis hatasi: %s", e)


if __name__ == "__main__":
    main()
