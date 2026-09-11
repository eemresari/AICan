"""Ollama HTTP köprüsü — config'deki modele (ollama_model) sistem promptu + kullanıcı
metni gönderir, format-schema ile JSON jest cevabını çözümler.
Aktif model config.json'dan gelir; jest davranışı ai/system_prompt.txt ile belirlenir."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests

import paths

log = logging.getLogger(__name__)

# Mirror override: model bu jestlerden birini secince ve kullanici 1. tekil
# olumsuz duygu paylasiyorsa sicaklik'a override edilir.
_MIRROR_TARGET_JESTS = {
    "uzgun_yavas", "uzgun_derin", "ofke", "korku", "panik",
    "yalniz", "hayal_kirikligi", "sikilma",
}

# Kullanicinin kendi olumsuz duygu sinyali (1. tekil sahis)
_MIRROR_NEG_PATTERNS = [
    r"\bk[oö]t[uü]y[uü]m\b", r"\b[uü]z[uü]nl?[uü]y[uü]m\b", r"\b[uü]zg[uü]n[uü]m\b",
    r"\bsinirliyim\b", r"\bk[ıi]zg[ıi]n[ıi]m\b", r"\bgerginim\b", r"\bstresliyim\b",
    r"\bkorkuyorum\b", r"\bend[ıi]şeliyim\b", r"\btedirginim\b",
    r"\byaln[ıi]z[ıi]m\b", r"\byorgunum\b", r"\bbunald[ıi]m\b",
    r"\bmoralim bozuk\b", r"\bmoralim k[oö]t[uü]\b",
    r"\b[ıi]yi de[gğ]ilim\b", r"\b[ıi]yi hissetmiyorum\b",
    r"\bk[oö]t[uü] hissediyorum\b", r"\bberbat hissediyorum\b",
]

# Override yapma istisnalari: kullanici bir KAYIP/OLAY anlatiyor (gercek empati uygun)
_MIRROR_LOSS_PATTERNS = [
    r"\b[oö]ld[uü]\b", r"\bkaybettim\b", r"\bvefat\b",
    r"\bayr[ıi]ld[ıi]k\b", r"\bboşand[ıi]k?\b",
    r"\bhastaland[ıi]\b", r"\b[ıi]şten at[ıi]ld[ıi]m\b",
]

# Sanitize: yanit metninde bu kelimeler varsa nazik sablonla degistir
_BANNED_FEELING_WORDS = [
    "üzüldü", "üzülüyor", "üzgün", "üzdü",
    "öfkelend", "sinirlend",
    "korkma", "korktu",
    "kızdı", "kızgın",
]

# jest_id'ye gore nazik sablon yanit
_SAFE_RESPONSE_TEMPLATES = {
    "sicaklik": "Yanındayım, anlatır mısın?",
    "dinliyorum": "Buradayım, dinliyorum.",
    "uzgun_yavas": "Bu hissi anlıyorum, yanındayım.",
    "uzgun_derin": "Çok ağır bir şey, yanındayım.",
    "yalniz": "Yalnız değilsin, buradayım.",
    "hayal_kirikligi": "Bu beklediğin gibi olmamış, anlatır mısın?",
    "korku": "Güvendesin, derin nefes al.",
    "panik": "Birlikte nefes alalım, yavaş.",
    "ofke": "Bunun ağır geldiğini görüyorum.",
    "sikilma": "Anlatmak ister misin?",
    "sevgi": "Sıcak sözlerin için teşekkür ederim.",
    "sicaklik_default": "Seni dinliyorum.",
}

# ---------- Guard katmani: dil/uzunluk/tekrar kontrolleri ----------
# test_runner.py da ayni fonksiyonlari import eder (tek gerceklik kaynagi).

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")

# Turkce'ye ozgu karakter icermeyen kisa yanitlari yakalamak icin sik kelimeler
_TR_COMMON_WORDS = {
    "bir", "bu", "ve", "de", "da", "ne", "mi", "acaba", "ama", "gibi",
    "daha", "en", "var", "yok", "ben", "sen", "biz", "o", "evet", "tamam",
    "seni", "sana", "bana", "benim", "senin", "peki", "nasil", "neden",
    "merhaba", "selam", "harika", "bravo", "aferin", "haydi", "hadi",
    "dinliyorum", "buradayim", "anlat", "birlikte", "istersen", "tekrar",
}

# Ingilizce'ye kayma sinyali — 2+ eslesme yaniti Ingilizce sayar
_EN_STOPWORDS = {
    "the", "is", "are", "you", "your", "i", "am", "it", "to", "and",
    "for", "with", "of", "that", "this", "was", "be", "have", "not",
    "can", "will", "what", "how", "here", "there", "me", "my", "we",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", (text or "").lower(), flags=re.UNICODE)


def guard_word_count(text: str, max_words: int = 12) -> bool:
    """Yanit kelime sayisi sinirda mi?"""
    return len(_words(text)) <= max_words


def truncate_sentences(text: str, max_sentences: int = 2) -> str:
    """Metni cumle sinirinda (. ! ?) keserek en fazla max_sentences cumleye indir."""
    parts = re.split(r"(?<=[.!?…])\s+", (text or "").strip())
    parts = [p for p in parts if p]
    if len(parts) <= max_sentences:
        return text.strip()
    return " ".join(parts[:max_sentences]).strip()


def guard_turkish(text: str) -> bool:
    """Yanit Turkce mi? (heuristik; yanlis-pozitife karsi genis tutuldu)
    Once Ingilizce kaymasi aranir; yoksa Turkce karakter/sik kelime yeterli sayilir.
    """
    ws = _words(text)
    if not ws:
        return True  # bos metni dil hatasi sayma; uzunluk/baska katman yakalar
    en_hits = sum(1 for w in ws if w in _EN_STOPWORDS)
    if en_hits >= 2 or (en_hits >= 1 and len(ws) <= 3):
        return False
    if any(ch in _TR_CHARS for ch in text):
        return True
    if any(w in _TR_COMMON_WORDS for w in ws):
        return True
    # Ne Turkce sinyal ne Ingilizce sinyal: kisa unlemler vs. — lenient gecir
    return True


def guard_no_parrot(user_text: str, yanit: str) -> bool:
    """Yanit, kullanici girdisini papaganlamiyor mu? (True = temiz)
    3+ kelimelik girdinin bigram'lariyla >%50 ortusme ya da girdinin
    aynen icinde gecmesi papagan sayilir.
    """
    uw, yw = _words(user_text), _words(yanit)
    if len(uw) < 3 or not yw:
        return True
    if " ".join(uw) in " ".join(yw):
        return False
    ub = {(uw[i], uw[i + 1]) for i in range(len(uw) - 1)}
    yb = {(yw[i], yw[i + 1]) for i in range(len(yw) - 1)}
    if not yb:
        return True
    return (len(ub & yb) / len(yb)) < 0.5


def guard_no_loop(yanit: str) -> bool:
    """Yanit ici tekrar dongusu var mi? (True = temiz)
    Ayni kelime-3'lusunun tekrari ya da ayni kelimenin 3+ kez pes pese gelmesi dongudur.
    """
    ws = _words(yanit)
    if len(ws) >= 3:
        trigrams = [tuple(ws[i:i + 3]) for i in range(len(ws) - 2)]
        if len(trigrams) != len(set(trigrams)):
            return False
    run = 1
    for a, b in zip(ws, ws[1:]):
        run = run + 1 if a == b else 1
        if run >= 3:
            return False
    return True


class LLMBridge:
    def __init__(self, config: dict, base_dir: Path):
        self.url = config["ollama_url"].rstrip("/")
        self.model = config["ollama_model"]
        self.timeout = float(config.get("request_timeout_sec", 20))
        self.use_baked_prompt = bool(config.get("use_baked_prompt", False))
        self.history_max_turns = int(config.get("history_max_turns", 6))
        # Sergi sertlestirme bayraklari
        self.mirror_override_enabled = bool(config.get("mirror_override_enabled", True))
        self.sanitize_responses = bool(config.get("sanitize_responses", True))
        # Ollama keep_alive — model RAM'de kalsin (sergi acilisi gecikmemesi icin)
        self.keep_alive = config.get("keep_alive", "60m")
        # Ollama default num_ctx=4096, sistem promptumuz ~5000 token + tarihce ile
        # kirpiliyor ve model tone/kural tablolarini goremiyor. 8192 rahat sigsin.
        self.num_ctx = int(config.get("num_ctx", 8192))
        # Ornekleme parametreleri (config'ten ayarlanabilir). Varsayilanlar
        # cesitlilik icindir: dusuk deterministiklik + frequency/presence penalty
        # -> ornek cumleleri ezberleyip papaganlamayi azaltir.
        self.temperature = float(config.get("llm_temperature", 0.75))
        self.top_p = float(config.get("llm_top_p", 0.92))
        # top_k dusuk olasilikli sacma tokenlari keser; min_p cok dusuk olasilikli
        # kuyrugu atar. Qwen3-instruct resmi onerisi top_k=20/top_p=0.8;
        # gemma3 icin top_k=64/top_p=0.95 kullan (config'ten).
        self.top_k = int(config.get("llm_top_k", 20))
        self.min_p = float(config.get("llm_min_p", 0.0))
        self.repeat_penalty = float(config.get("llm_repeat_penalty", 1.15))
        self.frequency_penalty = float(config.get("llm_frequency_penalty", 0.6))
        self.presence_penalty = float(config.get("llm_presence_penalty", 0.3))
        self.num_predict = int(config.get("llm_num_predict", 160))
        # num_gpu: 4GB kartta Ollama muhafazakar davranip katmanlari CPU'ya
        # tasiriyor (5-10x yavaslama); 99 = tum katmanlari GPU'ya zorla.
        # 0 = Ollama otomatigine birak (options'a eklenmez).
        self.num_gpu = int(config.get("llm_num_gpu", 0))
        # Guard katmani (uzunluk/dil/tekrar) + hata-geribildirimli tek retry
        self.guard_enabled = bool(config.get("guard_enabled", True))
        self.guard_max_words = int(config.get("guard_max_words", 12))
        self.guard_max_sentences = int(config.get("guard_max_sentences", 2))
        # Sergi koruma: asiri uzun girdi prompt'u sisirip timeout/donma yapmasin.
        # web_server zaten 413 ile reddeder; bu, Tkinter (main.py) yolunu da korur.
        self.max_user_input_chars = int(config.get("max_user_input_chars", 240))

        # ai/ icerigi paths.kaynak_oku uzerinden: dondurulmus build'de web.pak'tan
        # (diskte ai/ yoktur), kaynakta diskten. base_dir yalniz geriye uyumluluk
        # icin imzada duruyor; config'deki yollar orchestrator/'a gorelidir.
        self.system_prompt = paths.kaynak_oku(
            paths.kaynak_rel(config["system_prompt_path"])).decode("utf-8-sig")

        gdata = json.loads(paths.kaynak_oku(
            paths.kaynak_rel(config["gestures_path"])).decode("utf-8-sig"))
        self.valid_ids = {g["id"] for g in gdata["jestler"]}

        # Yapilandirilmis cikti semasi — Ollama'da jest_id'yi enum'a kilitler,
        # gecersiz jest uretme ihtimalini sifirlar.
        self._format_schema = {
            "type": "object",
            "properties": {
                "jest_id": {"type": "string", "enum": sorted(self.valid_ids)},
                "yogunluk": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "yanit": {"type": "string", "maxLength": 200},
            },
            "required": ["jest_id", "yogunluk", "yanit"],
        }

        # Konusma gecmisi — son N turun user/assistant ciftleri tutulur.
        self._history: list[dict] = []

        mode = "baked (modele gömülü)" if self.use_baked_prompt else "her istek (api üzerinden)"
        log.info("LLMBridge hazır — %d jest, model=%s, sistem promptu=%s, history=%d tur",
                 len(self.valid_ids), self.model, mode, self.history_max_turns)

    # ---------- Post-processing katmani ----------
    def _apply_mirror_override(self, user_text: str, jest_id: str, yanit: str) -> tuple[str, str, bool]:
        """Mirror kuralini sertlestir: model uzgun_*/ofke/korku/panik/yalniz/sikilma
        secip kullanici 1. tekil olumsuz duygu paylasiyorsa sicaklik'a override et.
        ISTISNA: kullanici kayip/olay anlatiyorsa override yapma (gercek empati uygun).
        Doner: (yeni_jest_id, yeni_yanit, override_yapildi_mi)
        """
        if not self.mirror_override_enabled:
            return jest_id, yanit, False
        if jest_id not in _MIRROR_TARGET_JESTS:
            return jest_id, yanit, False

        text = user_text.lower()
        # Kayip/olay cumlesi varsa override yapma (uzgun_derin gercek empati)
        if any(re.search(p, text) for p in _MIRROR_LOSS_PATTERNS):
            return jest_id, yanit, False
        # 1. tekil olumsuz duygu sinyali var mi?
        if not any(re.search(p, text) for p in _MIRROR_NEG_PATTERNS):
            return jest_id, yanit, False

        new_yanit = _SAFE_RESPONSE_TEMPLATES.get("sicaklik", "Yanındayım.")
        log.info("Mirror override: %s -> sicaklik (kullanici: %r)", jest_id, user_text[:40])
        return "sicaklik", new_yanit, True

    def _sanitize_yanit(self, jest_id: str, yanit: str) -> tuple[str, bool]:
        """Yanit metni kullanicinin duygu kelimesini tekrar ediyorsa nazik sablona cevir.
        Doner: (yeni_yanit, sanitize_yapildi_mi)
        """
        if not self.sanitize_responses or not yanit:
            return yanit, False
        low = yanit.lower()
        if not any(w in low for w in _BANNED_FEELING_WORDS):
            return yanit, False
        new_yanit = _SAFE_RESPONSE_TEMPLATES.get(jest_id, _SAFE_RESPONSE_TEMPLATES["sicaklik_default"])
        log.info("Sanitize: %r -> %r (jest=%s)", yanit[:50], new_yanit, jest_id)
        return new_yanit, True

    def _fallback_jest(self, yanit: str) -> str:
        """Model gecersiz jest_id urettiginde (cok nadir, schema enum kilidini asarsa)
        yanit metninin valansina gore makul bir jest sec.
        """
        text = (yanit or "").lower()
        if any(w in text for w in ("üzül", "ağır", "kötü", "kayıp", "yanındayım")):
            return "uzgun_yavas"
        if any(w in text for w in ("güzel", "harika", "sevin", "mutlu", "tebrik")):
            return "sicaklik"
        if "?" in text or any(w in text for w in ("kasted", "anlat", "tekrar")):
            return "soru_isareti"
        if any(w in text for w in ("merhaba", "selam", "hoş geldin")):
            return "selamlama"
        return "anlamadim"

    def clear_history(self) -> None:
        """Konusma gecmisini sifirla (yeni oturum/konu icin)."""
        self._history.clear()

    def warmup(self) -> bool:
        """Modeli RAM'e isit — ilk kullanici beklemesin. /api/generate ile kucuk
        bir istek gonderir; cevabin icerigi onemsiz, amac model_load."""
        try:
            r = requests.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "ok",
                    "stream": False,
                    "think": False,
                    "keep_alive": self.keep_alive,
                    "options": {
                        "num_predict": 1, "temperature": 0.0, "num_ctx": self.num_ctx,
                        # Ayni GPU yerlesimiyle isinsin ki ilk gercek istek reload tetiklemesin
                        **({"num_gpu": self.num_gpu} if self.num_gpu > 0 else {}),
                    },
                },
                timeout=120,
            )
            ok = r.status_code == 200
            log.info("Warmup %s: %s", self.model, "OK" if ok else f"HTTP {r.status_code}")
            return ok
        except requests.RequestException as e:
            log.warning("Warmup hatasi: %s", e)
            return False

    def is_alive(self) -> bool:
        # Iki defaya kadar dene; ilk istek bazen geç gelir (Ollama henuz hazirlanir)
        for attempt in range(2):
            try:
                r = requests.get(f"{self.url}/api/tags", timeout=5)
                if r.status_code == 200:
                    return True
            except requests.RequestException as e:
                if attempt == 1:
                    log.warning("Ollama erişilemiyor (2 deneme): %s", e)
        return False

    def list_local_models(self) -> list[dict]:
        """Lokal yuklu modelleri donder: [{name, size_gb}]."""
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=5)
            r.raise_for_status()
            out = []
            for m in r.json().get("models", []):
                size_gb = float(m.get("size", 0)) / (1024 ** 3)
                out.append({"name": m.get("name", "?"), "size_gb": size_gb})
            out.sort(key=lambda x: x["name"])
            return out
        except requests.RequestException as e:
            log.warning("Model listesi alinamadi: %s", e)
            return []

    def set_model(self, name: str) -> bool:
        """Aktif modeli degistir; konusma gecmisini sifirla."""
        name = name.strip()
        if not name or name == self.model:
            return False
        log.info("Model degistirildi: %s -> %s", self.model, name)
        self.model = name
        self._history.clear()
        return True

    def pull_model(self, name: str, on_progress) -> bool:
        """Modeli Ollama registry'sinden cek; her durum guncellemesi on_progress'e gonderilir.
        Streaming JSON (her satir bir olay): {status, completed?, total?, error?}.
        """
        name = name.strip()
        if not name:
            on_progress({"error": "model adi bos"})
            return False
        try:
            with requests.post(
                f"{self.url}/api/pull",
                json={"name": name, "stream": True},
                stream=True,
                timeout=None,
            ) as r:
                if r.status_code != 200:
                    on_progress({"error": f"http {r.status_code}: {r.text[:200]}"})
                    return False
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    on_progress(data)
                    if data.get("error"):
                        return False
            return True
        except requests.RequestException as e:
            log.error("Model indirme hatasi: %s", e)
            on_progress({"error": str(e)})
            return False

    def _llm_options(self) -> dict:
        """Her istekte acikca gonderilen Ollama options — Modelfile/sunucu
        varsayilanlarina guvenme (surum guncellemelerinde degisebiliyor)."""
        opts = {
            # jest_id format-schema enum'la kilitli oldugu icin sicaklik
            # artirmak JSON'u BOZMAZ, sadece "yanit" metnini cesitlendirir.
            # frequency/presence penalty ornek cumlelerin ezberlenip
            # papaganlanmasini kirar (config'ten ayarlanir).
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "min_p": self.min_p,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            # 1.3 Turkce'yi bozuyor (kelime atlama); 1.15 dengeli.
            "repeat_penalty": self.repeat_penalty,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }
        if self.num_gpu > 0:
            opts["num_gpu"] = self.num_gpu
        return opts

    def _chat_once(self, messages: list[dict], t0: float) -> dict:
        """Tek /api/chat cagrisi + JSON cozumleme.
        Basarili: {parsed, raw, meta}; degilse {error, raw?, meta}."""
        try:
            r = requests.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": self._format_schema,
                    "keep_alive": self.keep_alive,
                    # Qwen3 gibi "thinking" modellerinde dusunce tokenlari content'i
                    # bos birakir ve num_predict limiti dolar -> empty_content hatasi.
                    # think=false dusunceyi kapatir; thinking desteklemeyen modeller
                    # (qwen2.5, gemma3) bu alani gormez.
                    "think": False,
                    "options": self._llm_options(),
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            log.error("Ollama çağrısı hata verdi: %s", e)
            return {"error": f"ollama_request_failed: {e}",
                    "meta": {"wall_s": time.monotonic() - t0}}

        meta = {
            "wall_s": time.monotonic() - t0,
            "total_ms": data.get("total_duration", 0) / 1e6,
            "load_ms": data.get("load_duration", 0) / 1e6,
            "prompt_tokens": int(data.get("prompt_eval_count", 0)),
            "prompt_eval_ms": data.get("prompt_eval_duration", 0) / 1e6,
            "eval_tokens": int(data.get("eval_count", 0)),
            "eval_ms": data.get("eval_duration", 0) / 1e6,
        }
        meta["tok_per_s"] = (
            meta["eval_tokens"] * 1000.0 / meta["eval_ms"]
            if meta["eval_ms"] > 0 else 0.0
        )

        content = data.get("message", {}).get("content", "")
        if not content:
            log.error("Ollama boş cevap döndü: %s", data)
            return {"error": "empty_content", "meta": meta}

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            log.error("Model JSON çözülemedi: %s\nİçerik: %s", e, content)
            return {"error": "invalid_json", "raw": content, "meta": meta}

        return {"parsed": parsed, "raw": content, "meta": meta}

    def _extract(self, parsed: dict, meta: dict) -> tuple[str, float, str]:
        """Model JSON'undan (jest_id, yogunluk, yanit) cek; gecersiz jest'te fallback."""
        jest_id = parsed.get("jest_id")
        try:
            yog = float(parsed.get("yogunluk", 0.7))
        except (TypeError, ValueError):
            yog = 0.7
        yog = max(0.0, min(1.0, yog))
        yanit = str(parsed.get("yanit", "")).strip()

        # Schema enum kilidi normalde gecersiz jest_id'yi onler; yine de gelirse
        # hatayla durmak yerine yanitin valansindan makul bir jest sec.
        if jest_id not in self.valid_ids:
            log.warning("Bilinmeyen jest_id: %r — fallback uygulandi", jest_id)
            jest_id = self._fallback_jest(yanit)
            meta["fallback_used"] = True
        return jest_id, yog, yanit

    def _guard_problems(self, user_text: str, yanit: str) -> list[str]:
        """Retry gerektiren yanit sorunlarini listele (uzunluk haric — o kesilir)."""
        problems = []
        if not guard_turkish(yanit):
            problems.append("dil")
        if not guard_no_parrot(user_text, yanit):
            problems.append("papagan")
        if not guard_no_loop(yanit):
            problems.append("dongu")
        return problems

    def request(self, user_text: str) -> Optional[dict]:
        """Başarılı: {jest_id, yogunluk, yanit, meta}. Başarısız: {error: ..., meta?}"""
        t0 = time.monotonic()
        # Asiri uzun girdiyi kirp (her iki giris yolunu da korur).
        if self.max_user_input_chars > 0 and len(user_text) > self.max_user_input_chars:
            user_text = user_text[: self.max_user_input_chars]
        # Baked modda sistem promptu modele gömülü olduğundan tekrar göndermeyiz —
        # bu ~2300 token prompt eval süresi tasarrufu sağlar.
        messages: list[dict] = []
        if not self.use_baked_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        # Onceki turlar — modelin bagi kaybetmemesi icin son N user/assistant cifti
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})

        result = self._chat_once(messages, t0)
        if "error" in result:
            out = {"error": result["error"], "meta": result["meta"]}
            if "raw" in result:
                out["raw"] = result["raw"]
            return out

        meta = result["meta"]
        meta["fallback_used"] = False
        jest_id, yog, yanit = self._extract(result["parsed"], meta)

        # Guard: dil/papagan/dongu sorununda AYNI istegi degil, hatayi ACIKLAYAN
        # ek satirla 1 kez retry; ikinci basarisizlikta guvenli sablona dus.
        # (Cogu model hata geribildirimiyle ilk retry'da kendini duzeltir.)
        meta["guard_retry"] = ""
        meta["guard_fallback"] = False
        if self.guard_enabled:
            problems = self._guard_problems(user_text, yanit)
            if problems:
                meta["guard_retry"] = ",".join(problems)
                log.info("Guard retry (%s): %r", meta["guard_retry"], yanit[:60])
                aciklama = {
                    "dil": "Cevabın Türkçe değildi.",
                    "papagan": "Cevabın kullanıcının sözlerini tekrarlıyordu.",
                    "dongu": "Cevabında aynı sözler dönüp duruyordu.",
                }
                correction = (
                    " ".join(aciklama[p] for p in problems)
                    + f" Aynı mesaja YENİ bir cevap ver: yalnızca Türkçe, en fazla"
                      f" {self.guard_max_sentences} cümle, kullanıcının sözlerini tekrar etmeden."
                )
                retry = self._chat_once(
                    messages + [
                        {"role": "assistant", "content": result["raw"]},
                        {"role": "user", "content": correction},
                    ],
                    time.monotonic(),
                )
                if "parsed" in retry:
                    jest2, yog2, yanit2 = self._extract(retry["parsed"], retry["meta"])
                    if not self._guard_problems(user_text, yanit2):
                        jest_id, yog, yanit = jest2, yog2, yanit2
                        meta["retry_wall_s"] = round(retry["meta"]["wall_s"], 2)
                    else:
                        yanit = _SAFE_RESPONSE_TEMPLATES.get(
                            jest_id, _SAFE_RESPONSE_TEMPLATES["sicaklik_default"])
                        meta["guard_fallback"] = True
                else:
                    yanit = _SAFE_RESPONSE_TEMPLATES.get(
                        jest_id, _SAFE_RESPONSE_TEMPLATES["sicaklik_default"])
                    meta["guard_fallback"] = True
                meta["wall_s"] = time.monotonic() - t0

        # Uzunluk sorunu retry gerektirmez: cumle sinirinda kes.
        meta["truncated"] = False
        if not guard_word_count(yanit, self.guard_max_words):
            kisa = truncate_sentences(yanit, self.guard_max_sentences)
            if kisa and kisa != yanit:
                log.info("Uzun yanit kesildi: %r -> %r", yanit[:60], kisa[:60])
                yanit = kisa
                meta["truncated"] = True

        # Post-processing: mirror override (Sorun 4) + sanitize (Sorun 5)
        jest_id, yanit, mirror_done = self._apply_mirror_override(user_text, jest_id, yanit)
        meta["mirror_override"] = mirror_done
        yanit, sanitize_done = self._sanitize_yanit(jest_id, yanit)
        meta["sanitized"] = sanitize_done

        # Basarili turu gecmise yaz — assistant turunu tam JSON olarak sakliyoruz
        # ki model formati ve onceki kararlarini tutarli sekilde gorsun.
        assistant_payload = json.dumps(
            {"jest_id": jest_id, "yogunluk": yog, "yanit": yanit},
            ensure_ascii=False,
        )
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": assistant_payload})
        limit = self.history_max_turns * 2
        if len(self._history) > limit:
            self._history = self._history[-limit:]

        return {"jest_id": jest_id, "yogunluk": yog, "yanit": yanit, "meta": meta}