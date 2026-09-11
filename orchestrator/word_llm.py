"""AICAN — Kelime Türetme oyunu için yerel LLM köprüsü (Ollama).

Bu modül SOHBET çekirdeğinden (llm_bridge.py, system_prompt.txt, gestures.json)
BAĞIMSIZDIR ve onlara dokunmaz. Kelime oyununa özel iki iş yapar:
  1) uret_kelime(harf, kullanilmis) -> verilen harfle başlayan yeni bir Türkçe kelime
  2) gecerli_mi(kelime)             -> kelime gerçek bir Türkçe sözcük mü?

Ollama'ya kendi promptu + JSON şeması ile gider (gesture sistem promptu KULLANILMAZ).
Sergi sağlamlığı: kısa timeout, küçük num_predict, hata/kararsızlıkta GÜVENLİ taraf
(gecerli_mi lenient → ziyaretçiyi modelin zayıflığından cezalandırma).
"""
from __future__ import annotations

import json
import logging
import random
import re

import requests

import paths

log = logging.getLogger(__name__)

# Türkçe küçük harfe çevirme (I/İ doğru ele alınır) — eşleştirme/ilk harf için.
_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def tr_lower(s: str) -> str:
    return (s or "").translate(_TR_LOWER).lower()


def temiz_kelime(s: str) -> str:
    """Modelden/kullanıcıdan gelen kelimeyi sadeleştir: tek sözcük, harfler, küçük."""
    s = tr_lower(s).strip()
    # İlk sözcüğü al (model bazen 'elma.' / 'elma kelimesi' döndürür)
    s = re.sub(r"[^a-zçğıöşü]", " ", s).strip()
    return s.split(" ")[0] if s else ""


def son_harf(kelime: str) -> str:
    """Kelimenin oyunda kullanılacak son harfi (küçük)."""
    k = temiz_kelime(kelime)
    return k[-1] if k else ""


def ilk_harf(kelime: str) -> str:
    k = temiz_kelime(kelime)
    return k[0] if k else ""


# ——— Statik yedek havuz (ai/word_categories.json) ——————————————————
# Sergi sağlamlığı: LLM timeout/hata verdiğinde oyun kilitlenmesin diye
# uret_kelime önce LLM'i dener, olmazsa bu havuzdan (doğru harfle başlayan +
# o oyunda kullanılmamış) kelime seçer. Havuzda da yoksa None döner (mevcut
# 'pes' akışı korunur). game_engine._pick_ai_word havuz deseninin word_llm
# tarafındaki karşılığıdır; dosya okunamazsa boş havuz = eski davranış.
_CATS_PATH = "ai/word_categories.json"  # paths.kaynak_oku anahtari (depo kokune gore)
_yedek_havuz_cache = None  # {harf: [kelime, ...]} — lazy, tek sefer yüklenir


def _yedek_havuz() -> dict:
    global _yedek_havuz_cache
    if _yedek_havuz_cache is None:
        idx: dict = {}
        try:
            data = json.loads(paths.kaynak_oku(_CATS_PATH).decode("utf-8-sig"))
            for words in data.values():
                if not isinstance(words, list):
                    continue
                for w in words:
                    w = temiz_kelime(w)
                    if len(w) >= 2:
                        idx.setdefault(w[0], []).append(w)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            log.warning("Yedek kelime havuzu okunamadı (%s): %s", _CATS_PATH, e)
        _yedek_havuz_cache = idx
    return _yedek_havuz_cache


def _havuzdan_kelime(harf: str, kullanilmis: set) -> str | None:
    """Havuzdan `harf` ile başlayan, kullanılmamış rastgele kelime; yoksa None."""
    adaylar = [w for w in _yedek_havuz().get(harf, []) if w not in kullanilmis]
    return random.choice(adaylar) if adaylar else None


# ——— LLM çağrı şemaları ————————————————————————————————————————
_URET_SCHEMA = {
    "type": "object",
    "properties": {"kelime": {"type": "string"}},
    "required": ["kelime"],
}
_GECERLI_SCHEMA = {
    "type": "object",
    "properties": {"gecerli": {"type": "boolean"}},
    "required": ["gecerli"],
}


class WordLLM:
    """Kelime oyunu için Ollama sarmalayıcı. url+model dışarıdan verilir (LLMBridge'den)."""

    def __init__(self, url: str, model: str, *, timeout: float = 12.0,
                 keep_alive: str = "60m", num_ctx: int = 8192):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = float(timeout)
        self.keep_alive = keep_alive
        self.num_ctx = int(num_ctx)
        # Son cagrida Ollama'ya ULASILAMADI mi? (baglanti/timeout/HTTP hatasi)
        # GameEngine bunu okuyup "gercek pes" ile "model coktu"yu ayirir.
        self.unreachable = False

    # ——— Ortak çağrı ————————————————————————————————————————
    def _chat(self, system: str, user: str, schema: dict, num_predict: int = 24):
        """Ollama /api/chat — JSON şemasıyla. Başarısızsa None döner (sergi çökmesin)."""
        try:
            r = requests.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "format": schema,
                    "think": False,
                    "keep_alive": self.keep_alive,
                    "options": {
                        "temperature": 0.6,
                        "top_p": 0.9,
                        "num_ctx": self.num_ctx,
                        "num_predict": num_predict,
                    },
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "")
            self.unreachable = False
            if not content:
                return None
            return json.loads(content)
        except requests.RequestException as e:
            # Baglanti/timeout/HTTP -> Ollama'ya ulasilamadi (oyun fallback'i icin isaretle)
            self.unreachable = True
            log.warning("Kelime LLM ulaşılamadı: %s", e)
            return None
        except (json.JSONDecodeError, ValueError) as e:
            # Model yanit verdi ama JSON bozuk -> ulasilabiliyor, sadece bu cevap kotu
            self.unreachable = False
            log.warning("Kelime LLM yanıtı çözülemedi: %s", e)
            return None

    # ——— AI'nın kelimesini üret ————————————————————————————————
    def uret_kelime(self, harf: str, kullanilmis: set[str], denemeler: int = 2):
        """`harf` ile başlayan, kullanılmamış bir Türkçe kelime döndür. Bulamazsa None.

        Çıktı determinist olarak doğrulanır: gerçekten o harfle mi başlıyor + yeni mi?
        Bu sayede modelin kuralı çiğnediği cevaplar AI'nın 'pes etmesi'ne dönüşür (kabul).
        """
        harf = tr_lower(harf)[:1]
        if not harf:
            return None
        sistem = (
            "Sen bir Türkçe kelime oyunu oyuncususun. Sana bir HARF verilir; o harfle "
            "BAŞLAYAN, gerçek ve yaygın bir Türkçe sözcük (tercihen tek kelime, isim) bulursun. "
            "Özel isim, kısaltma, argo kullanma. Sadece JSON döndür: {\"kelime\": \"...\"}."
        )
        kull_ipucu = ""
        if kullanilmis:
            ornek = ", ".join(list(kullanilmis)[:12])
            kull_ipucu = f" Şu kelimeleri KULLANMA: {ornek}."
        kullanici = f"'{harf}' harfi ile başlayan bir Türkçe kelime söyle.{kull_ipucu}"

        for _ in range(max(1, denemeler)):
            data = self._chat(sistem, kullanici, _URET_SCHEMA, num_predict=24)
            if not data:
                continue
            kelime = temiz_kelime(data.get("kelime", ""))
            if kelime and kelime[0] == harf and kelime not in kullanilmis and len(kelime) >= 2:
                return kelime
        # LLM başarısız (timeout/erişilemedi/kural ihlali) → statik havuz yedeği.
        # Oyun kilitlenmez; havuzda da uygun kelime yoksa None = mevcut 'pes' akışı.
        yedek = _havuzdan_kelime(harf, kullanilmis)
        if yedek is not None:
            log.info("uret_kelime: LLM başarısız — statik havuzdan '%s' seçildi.", yedek)
        return yedek

    # ——— Kullanıcının kelimesi gerçek mi? ————————————————————————
    def gecerli_mi(self, kelime: str) -> bool:
        """Gerçek bir Türkçe sözcük mü? LENIENT: model hata/kararsızsa True (kabul).

        Harf/kullanılmış kontrolü ÇAĞIRAN tarafça yapılır; burada yalnız sözlük geçerliliği.
        """
        kelime = temiz_kelime(kelime)
        if len(kelime) < 2:
            return False
        sistem = (
            "Sana bir sözcük verilir. Bunun gerçek, geçerli bir TÜRKÇE sözcük olup olmadığını "
            "söyle. Yaygın çekimli haller de geçerlidir. Özel isim/uydurma/anlamsız ise geçersiz. "
            "Sadece JSON döndür: {\"gecerli\": true} ya da {\"gecerli\": false}."
        )
        data = self._chat(sistem, f"'{kelime}' geçerli bir Türkçe sözcük mü?",
                           _GECERLI_SCHEMA, num_predict=8)
        if data is None or "gecerli" not in data:
            # Model erişilemedi/kararsız → ziyaretçiyi cezalandırma, kabul et.
            return True
        return bool(data["gecerli"])
