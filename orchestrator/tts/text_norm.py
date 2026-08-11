"""Seslendirme oncesi metin normalizasyonu — EKRAN metni ile SES metnini ayirir.

Neden: ekranda ":)" sicak durur, emoji'li menu okunakli olur; ama TTS motorlari
bunlari OKUR — ":)" "gulumseme"/"smiley" diye seslendirilir, "🔤" emoji adina
cevrilir, "Es/Zit Anlam" egik cizgi yuzunden tek belirtece yapisip yanlis
telaffuz edilir ("zit"). Bu katman YALNIZCA sese giden kopyayi temizler;
payload["yanit"] (ekranda gorunen metin) hic degismez.

ONBELLEK SOZLESMESI: normalizasyon anahtar turetiminden ONCE uygulanir ve
runtime (web_server._tts_synth_cached) ile on-uretim (tts.gen_batch_elevenlabs)
AYNI fonksiyonu cagirir — boylece iki taraf ayni anahtari kurar. Buradaki bir
kurali degistirmek etkilenen parcalarin cache anahtarini degistirir:
degisiklikten sonra `python -m tts.gen_batch_elevenlabs --eksik` ile olc,
`--run --yes` ile yeniden uret. Aksi halde o parcalar sergide ucretsiz yedek
sese duser.
"""
from __future__ import annotations

import re
import unicodedata

# ——— 1) Yuz ifadeleri ————————————————————————————————————————
# Nokta ile DEGISTIRILIR (silinmez): ":)" cogu zaman cumle sonunu isaretliyor
# ("Hmm, tam anlamadim :) Hangisini oynayalim?") — silmek iki cumleyi birlestirip
# tonlamayi bozardi. Fazla nokta asagida temizlenir.
_YUZ_IFADESI = re.compile(r"[:;=8]['`^-]?[()\[\]DdPpOo3]+(?=\s|$)")

# ——— 2) Egik cizgi ——————————————————————————————————————————
# "Bitti! 3/5 dogru." -> kesir gibi okunur ("uc bolu bes"); dogal Turkce'ye cevir.
_SKOR = re.compile(r"(\d+)\s*/\s*(\d+)(\s+doğru)", re.IGNORECASE)
# "Es/Zit Anlam", "Dogru/Yanlis" -> ikili tek belirtece yapismasin diye BOSLUK.
# (Virgul degil: menu zaten virgulle ayrilmis liste — "Dogru, Yanlis" ayri iki
# secenek sanilirdi.)
_IKILI = re.compile(r"(?<=\w)\s*/\s*(?=\w)")

# ——— 3) Olcu birimi ————————————————————————————————————————
_DERECE = re.compile(r"(\d+)\s*°\s*[Cc]?")

# ——— 4) BUYUK HARFLI vurgu ————————————————————————————————————
# Ekranda "her birinin EŞ ya da ZIT anlamlısını bul" vurgudur; ama TTS buyuk
# harfli belirteci ya harf harf heceler ya da yabanci kelime sanir — "ZIT"
# Turkce "zıt" yerine Ingilizce "zit" diye okunuyordu (noktasiz ı buyuk harfte
# I'ya donustugu icin). Sese giderken normal yazima cevrilir; EKRAN buyuk kalir.
# Sesli harf sarti kisaltmalari korur (TRT, MHP harf harf okunmali).
_BUYUK_KELIME = re.compile(r"\b[A-ZÇĞİIÖŞÜ]{2,}\b")
_SESLI = set("AEIİOÖUÜ")


def _tr_kucult(s: str) -> str:
    """Turkce-dogru kucultme: I->ı, İ->i (Python'un varsayilani I->i verirdi)."""
    return s.replace("I", "ı").replace("İ", "i").lower()


def _buyuk_vurgu_duzelt(m: re.Match) -> str:
    w = m.group(0)
    if not (_SESLI & set(w)):
        return w                      # sesli harfsiz = kisaltma, dokunma
    return w[0] + _tr_kucult(w[1:])


# ——— 5) Temizlik ————————————————————————————————————————————
_BOSLUK_ONCE_NOKTALAMA = re.compile(r"\s+([.,!?;:])")
_FAZLA_NOKTA = re.compile(r"([.,!?;:—–-])\s*\.")
_COKLU_BOSLUK = re.compile(r"\s{2,}")


def _emoji_sil(s: str) -> str:
    """Sembol/emoji karakterlerini at (kategori So + varyasyon secici, ZWJ).

    Turkce harfler (Ll/Lu), noktalama (P*) ve rakamlar (Nd) korunur. '°' de So
    sinifindadir — bu yuzden _DERECE ondan ONCE calisir, yoksa "100°C" sessizce
    "100C" olur ("yuz ce")."""
    return "".join(
        ch for ch in s
        if not (unicodedata.category(ch) == "So" or ch in ("️", "︎", "‍"))
    )


def seslendirme_metni(text: str) -> str:
    """Sese gidecek metnin temizlenmis hali. Bos donebilir (yalnizca emoji vb.)."""
    s = (text or "").strip()
    if not s:
        return ""
    s = _DERECE.sub(r"\1 derece", s)         # emoji temizliginden ONCE ('°' = So)
    s = _emoji_sil(s)
    s = _YUZ_IFADESI.sub(".", s)
    s = _SKOR.sub(r"\2 soruda \1\3", s)     # "3/5 doğru" -> "5 soruda 3 doğru"
    s = _IKILI.sub(" ", s)                   # "Eş/Zıt" -> "Eş Zıt"
    s = _BUYUK_KELIME.sub(_buyuk_vurgu_duzelt, s)   # "ZIT" -> "Zıt"
    s = s.replace("·", ",")                  # menu ayraci -> dogal duraklama
    s = _COKLU_BOSLUK.sub(" ", s).strip()
    s = _BOSLUK_ONCE_NOKTALAMA.sub(r"\1", s)
    s = _FAZLA_NOKTA.sub(r"\1", s)           # "Merhaba! ." -> "Merhaba!"
    s = _COKLU_BOSLUK.sub(" ", s).strip()
    # Sondaki yalniz kalmis ayrac (emoji silinince olusabilir) sesli duraksama yapmasin.
    return s.strip(" ,;:·-–—")


if __name__ == "__main__":  # hizli gozle dogrulama: python -m tts.text_norm
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    for ornek in [
        "Hazır olunca 'başla' de :)",
        "Hazır olunca 'başla' de ya da butona dokun :)",
        "Hmm, tam anlamadım :) Hangisini oynayalım — Eş/Zıt Anlam ya da Atasözü?",
        "Hızlı düşünmek gerek :)",
        "Söyle: 🔤 Kelime Türetme · 🔁 Eş/Zıt Anlam · 📜 Atasözü · ✅ Doğru/Yanlış",
        "Dokun ya da söyle: 🔁 Eş/Zıt Anlam · 📜 Atasözü",
        "Merhaba, hoş geldin! Atasözü mü oynamak istersin, Eş/Zıt Anlam mı?",
        "Bitti! 3/5 doğru. Güzel oynadın!",
        "Bitti! 0/1 doğru.",
        "Eş/Zıt Anlam!",
        "Cevap: Doğru — Deniz seviyesinde su 100°C'de kaynar.",
        "'Kaçan balık büyük …' nasıl devam eder?",
        "Cevap: İsim.",
        "Merhaba. Sohbet edebiliriz. Oyun için \"oyun oynayalım\" de.",
        "Sana kelimeler söyleyeceğim; her birinin EŞ ya da ZIT anlamlısını bul.",
        "TRT ve MHP kısaltmaları harf harf okunmalı.",
        "🔤",
    ]:
        cikti = seslendirme_metni(ornek)
        print(f"  {ornek}\n-> {cikti}\n")
        # Sabit nokta: runtime ve batch ayni ham metni normalize eder; yine de
        # kural zinciri kendi ciktisinda DEGISMEZ kalmali (anahtar kaymasin).
        assert seslendirme_metni(cikti) == cikti, f"idempotent degil: {cikti!r}"
    print("idempotanlik: TAMAM")
