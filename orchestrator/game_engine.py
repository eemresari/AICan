"""AICAN — Oyun motoru: 4 oyunlu menu (deterministik).

Sergi temasi "yapay zekanin duygulari var mi?": ziyaretci AI ile oyun
oynar; AI kazaninca/kaybedince gercek bir insan gibi DUYGUSAL tepki verir.

Akis: "oyun oynayalim" tetiklenince DUZ 4 secenekli MENU cikar:
  🔤 Kelime Türetme · 🔁 Eş/Zıt Anlam · 📜 Atasözü · ✅ Doğru/Yanlış
Ziyaretci butonla/sesle birini secer; oyun biter bitmez menuye doner.
Eş/Zıt · Atasözü · Doğru/Yanlış ortak bir quiz motorundan (5 soru, dostca
puanli) gelir; verileri ai/*.json'dan. Kelime Türetme'de AI'nin verdigi
kelimeler edebiyat + tarih + bilim havuzlarinin BIRLESIMINDEN gelir.

Tasarim ilkesi: oyun mantigi ve duygu secimi DETERMINISTIK kod ile yurur
(hizli + sergi ortaminda cokme riski yok). Kelime gecerliligi once yerel
sozlukten, gerekirse local LLM'den (word_llm) dogrulanir.

Bu modul UI'dan bagimsizdir: girdi metni alir, gosterilecek payload doner.
Cekirdek sohbet dosyalari (llm_bridge.py, system_prompt.txt, gestures.json)
DEGISMEZ; oyun ek bir katmandir.
"""
from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path

from word_llm import son_harf, temiz_kelime

log = logging.getLogger(__name__)

# ——— Duygu (jest) havuzlari — mevcut jestleri yeniden kullanir ————
# Hicbiri yeni gorsel gerektirmez; gestures.json'daki id'ler.
_JEST = {
    "exit": "huzur",
    "menu": "selamlama",
    # ——— Kelime Türetme duyguları (mevcut id'ler) ———
    "kel_intro":     ["selamlama", "nese"],
    "kel_ai_word":   ["gurur", "mutluluk_yogun", "nese"],
    "kel_ai_streak": ["hayranlik", "gurur"],
    "kel_user_ok":   ["hayranlik", "nese", "onayla_sicak", "merak"],
    "kel_retry":     ["soru_isareti", "merak", "anlamadim"],
    "kel_ai_lose":   ["hayal_kirikligi", "uzgun_yavas"],
    "kel_user_lose": ["gurur", "mutluluk_sakin", "onayla_net"],
}

# ——— Replik havuzlari (Turkce, karakterli) ————————————————————
_TXT = {
    "exit": [
        "Oynamak güzeldi! İstediğinde yine çağır.",
    ],
    # ——— Kelime Türetme replikleri ————————————————————————————
    # Kullanici dogru kelime soyleyince AI sevinir/heyecanlanir (kisa tezahurat;
    # asil duygu jestle verilir). AI'nin KENDI cevabi ise sadece kelimedir.
    "kel_user_ok": [
        "Harika!", "Bravo!", "Süper kelime!", "Çok iyi!", "Helal!", "Vay, güzeldi!",
    ],
    # NOT: Bu replikler ARTIK '{harf}' icermez (ElevenLabs on-uretimi harf-basi
    # cesitlemeyi katlamasin diye). Gereken harf ekranda gosterilir. .format(harf=...)
    # cagrilari zararsiz no-op olur.
    "kel_retry_invalid": [
        "O bir kelime değil gibi. Gerçek bir kelime dene, bir hakkın var!",
    ],
    "kel_retry_letter": [
        "O kelime doğru harfle başlamıyor. Ekrandaki harfe bak, tekrar dene — bir hakkın var!",
    ],
    "kel_retry_used": [
        "O kelimeyi kullandık! Başka bir kelime söyle, bir hakkın var!",
    ],
    "kel_user_lose_invalid": [
        "Olmadı yine… Bu el bende! İyi oynadın ama.",
        "Bu sefer ben kazandım! Yine de keyifliydi, değil mi?",
    ],
    "kel_user_lose_timeout": [
        "Süre doldu! Bu turu ben aldım. Hızlı düşünmek gerek :)",
        "Zaman bitti — puan bende! Bir daha dene, eminim daha hızlısın.",
    ],
    "kel_ai_lose": [
        "Off… hiçbir şey gelmiyor aklıma. Pes! Sen kazandın, helal olsun!",
        "Düşünüyorum düşünüyorum, bir türlü bulamadım. Yenildim — sen daha iyisin!",
        "Tamam, teslim! Bu tur beni bitirdi. Kazanan sensin, tebrikler!",
    ],
}

# Kelime oyununda AI'nın açılış kelimesi için güvenli tohum havuzu (LLM gerekmez).
_KEL_SEED = ["elma", "kalem", "masa", "kitap", "deniz", "araba", "çiçek",
             "balık", "kapı", "bulut", "orman", "yıldız"]

# Yaygın Türkçe kelime sözlüğü — kelime oyununda HIZ ve SAĞLAMLIK için.
# (1) Kullanıcı bu kümeden bir kelime yazınca gecerli_mi() LLM'e HİÇ gitmez (anında kabul).
# (2) Temalı havuz boş kalırsa (JSON yok) AI bu kümeden geçerli bir kelime oynayıp sürdürür.
# Hepsi gerçek, yaygın, tek-sözcük; temiz_kelime() çıktısıyla (küçük, Türkçe harf) eşleşir.
_TR_COMMON_WORDS = frozenset({
    "elma", "armut", "kiraz", "vişne", "kayısı", "şeftali", "erik", "üzüm", "incir",
    "nar", "portakal", "mandalina", "limon", "muz", "çilek", "karpuz", "kavun", "ceviz",
    "fındık", "fıstık", "badem", "domates", "salatalık", "patates", "soğan", "sarımsak",
    "havuç", "lahana", "ıspanak", "marul", "biber", "patlıcan", "kabak", "fasulye",
    "bezelye", "mercimek", "nohut", "ekmek", "peynir", "zeytin", "yumurta", "süt",
    "yoğurt", "bal", "reçel", "çay", "kahve", "şeker", "tuz", "un", "pirinç", "makarna",
    "çorba", "salata", "kalem", "defter", "silgi", "cetvel", "kitap", "çanta", "masa",
    "sandalye", "koltuk", "dolap", "yatak", "halı", "perde", "lamba", "ayna", "kapı",
    "pencere", "anahtar", "kilit", "çekiç", "makas", "iğne", "iplik", "düğme", "sabun",
    "havlu", "fırça", "tarak", "saat", "gözlük", "yüzük", "kolye", "bilezik", "kemer",
    "şapka", "eldiven", "atkı", "çorap", "ayakkabı", "gömlek", "pantolon", "etek",
    "ceket", "palto", "elbise", "deniz", "göl", "nehir", "dere", "dağ", "tepe", "orman",
    "ağaç", "yaprak", "dal", "kök", "çiçek", "gül", "papatya", "lale", "menekşe", "ot",
    "çimen", "kuş", "serçe", "kartal", "baykuş", "karga", "güvercin", "leylek", "ördek",
    "kaz", "tavuk", "horoz", "balık", "yengeç", "kedi", "köpek", "at", "eşek", "inek",
    "öküz", "koyun", "keçi", "deve", "aslan", "kaplan", "ayı", "tilki", "kurt", "geyik",
    "tavşan", "fil", "zürafa", "maymun", "yılan", "kurbağa", "kaplumbağa", "arı",
    "karınca", "kelebek", "sinek", "örümcek", "araba", "otobüs", "kamyon", "tren",
    "uçak", "gemi", "vapur", "bisiklet", "motor", "yol", "köprü", "tünel", "ev", "bina",
    "okul", "sınıf", "hastane", "market", "mağaza", "fırın", "lokanta", "bahçe", "park",
    "sokak", "cadde", "meydan", "şehir", "kasaba", "köy", "ülke", "dünya", "güneş",
    "gökyüzü", "bulut", "yağmur", "kar", "dolu", "rüzgar", "fırtına", "şimşek", "su",
    "ateş", "toprak", "hava", "taş", "kum", "demir", "altın", "gümüş", "bakır", "cam",
    "tahta", "kağıt", "kumaş", "ip", "anne", "baba", "kardeş", "abla", "dede", "nine",
    "teyze", "hala", "amca", "dayı", "çocuk", "bebek", "kız", "oğlan", "adam", "kadın",
    "insan", "arkadaş", "komşu", "öğretmen", "öğrenci", "doktor", "hemşire", "polis",
    "asker", "şoför", "aşçı", "ressam", "oyun", "top", "oyuncak", "balon", "uçurtma",
    "salıncak", "renk", "sayı", "harf", "kelime", "cümle", "masal", "hikaye", "şiir",
    "şarkı", "türkü", "dans", "resim", "müzik", "göz", "kulak", "burun", "ağız", "dil",
    "diş", "dudak", "el", "kol", "ayak", "bacak", "parmak", "saç", "kaş", "yüz", "baş",
    "boyun", "omuz", "sırt", "karın", "kalp", "beyin", "kemik", "kan", "gün", "gece",
    "sabah", "akşam", "öğle", "hafta", "ay", "yıl", "mevsim", "yaz", "kış", "bahar",
    "zaman", "dakika", "saniye", "rüya", "umut", "sevgi", "mutluluk", "neşe", "hayat",
    "barış", "para", "hediye", "kutu", "sepet", "şişe", "bardak", "tabak", "çatal",
    "kaşık", "bıçak", "tencere", "tava", "buzdolabı", "soba", "ütü", "süpürge", "kova",
})

# ——— Kategorili kelime havuzu (AI temali kelimeler buradan secilir) ————
# AI kelimeleri edebiyat + tarih + bilim havuzlarinin BIRLESIMINDEN gelir.
_DEFAULT_CATS_PATH = Path(__file__).resolve().parent.parent / "ai" / "word_categories.json"

# AI'nin temali kelime havuzunu olusturan kategoriler (birlestirilir).
_THEMED_CATEGORIES = ("edebiyat", "tarih", "bilim")


def _index_by_first_letter(words):
    """Kelime listesini ilk harfe gore grupla: {harf: [kelime,...]} (temiz_kelime'li)."""
    idx = {}
    for w in words:
        w = temiz_kelime(w)
        if len(w) < 2:
            continue
        idx.setdefault(w[0], []).append(w)
    return idx


def _load_word_categories(path):
    """JSON'dan temali kategorileri yukle: {kategori: [kelime,...]}.
    Hata (yok/bozuk) -> {} (temali havuz bos kalir; _TR_COMMON_WORDS yedegi devreye girer)."""
    try:
        # utf-8-sig: BOM'lu dosya da kabul (Windows editorleri BOM ekleyebiliyor;
        # strict utf-8 BOM'da patlar ve veri sessizce yedege duserdi).
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return {k: [temiz_kelime(w) for w in v if temiz_kelime(w)]
                for k, v in data.items() if isinstance(v, list)}
    except (OSError, json.JSONDecodeError, ValueError) as e:
        log.warning("word_categories.json okunamadi: %s — _TR_COMMON_WORDS yedegi kullanilacak", e)
        return {}


# ——— Es/Zit Anlam verisi (dostca quiz; AI sorar, kullanici cevaplar) ————
# Kaynak: cocuklar icin 30 es + 30 zit (2026-07-25). Runtime, batch on-uretim ve
# test modu AYNI sabiti kullanir -> cache anahtarlari birebir eslesir (edge'e dusmez).
_EA_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "ai" / "es_zit_anlam_cocuklar_30_30.json"

# JSON okunamazsa mod calismaya devam etsin diye kucuk gomulu yedek.
_EA_FALLBACK = {
    "siyah": {"zit": ["beyaz", "ak"]},
    "büyük": {"zit": ["küçük"], "es": ["iri", "kocaman"]},
    "mutlu": {"zit": ["üzgün", "mutsuz"], "es": ["sevinçli", "neşeli"]},
    "hızlı": {"zit": ["yavaş"], "es": ["çabuk"]},
    "uzun": {"zit": ["kısa"]},
    "sıcak": {"zit": ["soğuk"]},
    "açık": {"zit": ["kapalı"]},
    "yeni": {"zit": ["eski"]},
    "güzel": {"zit": ["çirkin"], "es": ["hoş"]},
    "iyi": {"zit": ["kötü"]},
}


def _load_es_zit(path):
    """es_zit_anlam.json yukle: {kelime: {"es":[...], "zit":[...]}}.
    Hata -> {} (cagiran gomulu yedege duser)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        out = {}
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            entry = {}
            for tip in ("es", "zit"):
                vals = [temiz_kelime(w) for w in v.get(tip, []) if temiz_kelime(w)]
                if vals:
                    entry[tip] = vals
            kk = temiz_kelime(k)
            if kk and entry:
                out[kk] = entry
        return out
    except (OSError, json.JSONDecodeError, ValueError) as e:
        log.warning("es_zit_anlam.json okunamadi: %s — gomulu yedek kullanilacak", e)
        return {}


# Havuz buyutuldu (2026-08-13): atasozu50.json (49) -> atasozu.json (106, elenmis).
# atasozu.json, atasozu50'deki 49 atasozunun TAMAMINI iceriyor; hepsinin sesi
# ElevenLabs cache'inde hazir -> gecis 0 kredi.
# GERI DONUS: asagidaki satiri "atasozu50.json" yap; eski dosya yerinde duruyor.
_ATASOZU_PATH = Path(__file__).resolve().parent.parent / "ai" / "atasozu.json"
_DY_PATH = Path(__file__).resolve().parent.parent / "ai" / "dogru_yanlis.json"
_ATASOZU_FALLBACK = [
    {"bas": "Damlaya damlaya", "tamam": ["göl olur"]},
    {"bas": "Sakla samanı", "tamam": ["gelir zamanı"]},
    {"bas": "Bir elin nesi var", "tamam": ["iki elin sesi var"]},
    {"bas": "Ağaç yaşken", "tamam": ["eğilir"]},
    {"bas": "Son pişmanlık", "tamam": ["fayda etmez"]},
]
_DY_FALLBACK = [
    {"ifade": "Dünya, Güneş'in etrafında döner", "dogru": True, "aciklama": "Bir yılda döner."},
    {"ifade": "Güneş bir gezegendir", "dogru": False, "aciklama": "Güneş bir yıldızdır."},
    {"ifade": "Su 100 derecede kaynar", "dogru": True, "aciklama": "Deniz seviyesinde."},
    {"ifade": "Penguenler kuzey kutbunda yaşar", "dogru": False, "aciklama": "Güneyde yaşarlar."},
    {"ifade": "Buz suyun üstünde yüzer", "dogru": True, "aciklama": "Buz sudan hafiftir."},
]


def _load_json_list(path):
    """JSON dizi dosyasi yukle; hata/uyumsuz -> [] (cagiran gomulu yedege duser)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError, ValueError) as e:
        log.warning("%s okunamadi: %s — gomulu yedek", path, e)
        return []


# ——— Quiz saglayicilar — her biri tekduze soru dict uretir ————
# Soru dict: {"id", "prompt", "accept_norm": set, "accept_display": {norm: orijinal},
#             "reveal": str, "match": "token"|"substring"}
class _Provider:
    key = ""
    label = ""

    def intro(self, n):
        return ""

    def next_question(self, used):
        return None


class _EsZitProvider(_Provider):
    key = "eszit"
    label = "Eş/Zıt Anlam"

    def __init__(self, data):
        self.data = data
        self.norm = {w: {t: {normalize(x) for x in v} for t, v in e.items()}
                     for w, e in data.items()}
        self.words = [w for w, e in data.items() if e]

    def intro(self, n):
        return (f"Eş/Zıt Anlam! Sana kelimeler söyleyeceğim; her birinin EŞ ya da ZIT "
                f"anlamlısını bul. {n} soru, doğrularını sayacağım.")

    def next_question(self, used):
        adaylar = [w for w in self.words if w not in used]
        if not adaylar:
            return None
        kelime = random.choice(adaylar)
        tip = random.choice([t for t in ("es", "zit") if self.data[kelime].get(t)])
        tip_ad = "eş" if tip == "es" else "zıt"
        return {"id": kelime,
                "prompt": f"'{_cap(kelime)}' kelimesinin {tip_ad} anlamlısı ne?",
                "accept_norm": self.norm[kelime][tip],
                # norm -> ekran hali: fuzzy kabulde kullanici balonuna bu yazilir
                "accept_display": {normalize(x): _cap(x) for x in self.data[kelime][tip]},
                "reveal": _cap(self.data[kelime][tip][0]),
                # STT bias: kabul edilen cevaplarin ORIJINAL (Turkce harfli) halleri —
                # web_server bunlari whisper initial_prompt'a ekler.
                "hints": list(self.data[kelime][tip]),
                "match": "token"}


class _AtasozuProvider(_Provider):
    key = "atasozu"
    label = "Atasözü Tamamlama"

    def __init__(self, items):
        self.items = [it for it in items
                      if isinstance(it, dict) and it.get("bas") and it.get("tamam")]

    def intro(self, n):
        return (f"Atasözü Tamamlama! Atasözünün başını söyleyeceğim, sen devamını getir. "
                f"{n} soru, doğrularını sayacağım.")

    def next_question(self, used):
        adaylar = [it for it in self.items if it["bas"] not in used]
        if not adaylar:
            return None
        it = random.choice(adaylar)
        return {"id": it["bas"],
                "prompt": f"'{it['bas']} …' nasıl devam eder?",
                "accept_norm": {normalize(x) for x in it["tamam"]},
                "accept_display": {normalize(x): x for x in it["tamam"]},
                "reveal": f"{it['bas']} {it['tamam'][0]}",
                # STT bias: atasozunun tam hali(leri) — cocuk devamini soylerken
                # Whisper dogru kelimelere cekilir ("göl olur" vb.).
                "hints": [f"{it['bas']} {t}" for t in it["tamam"][:2]],
                "match": "substring"}


class _DogruYanlisProvider(_Provider):
    key = "dogruyanlis"
    label = "Doğru mu Yanlış mı"
    _EVET = {"dogru", "evet", "d", "true", "dogrudur", "doru"}
    _HAYIR = {"yanlis", "hayir", "y", "false", "yanlistir", "yalan"}

    def __init__(self, items):
        self.items = [it for it in items
                      if isinstance(it, dict) and it.get("ifade") and isinstance(it.get("dogru"), bool)]

    def intro(self, n):
        return (f"Doğru mu Yanlış mı! Bir şey söyleyeceğim; doğru mu yanlış mı bil. "
                f"{n} soru, doğrularını sayacağım.")

    def next_question(self, used):
        adaylar = [it for it in self.items if it["ifade"] not in used]
        if not adaylar:
            return None
        it = random.choice(adaylar)
        accept = self._EVET if it["dogru"] else self._HAYIR
        dy = "Doğru" if it["dogru"] else "Yanlış"
        return {"id": it["ifade"],
                "prompt": f"'{it['ifade']}' — doğru mu, yanlış mı?",
                "accept_norm": set(accept),
                # Hangi varyant soylenirse soylensin ("evet", "doru"...) ekranda
                # kanonik "Dogru"/"Yanlis" gorunur.
                "accept_display": {a: dy for a in accept},
                "reveal": f"{dy} — {it.get('aciklama', '')}".strip(" —"),
                "hints": ["doğru", "yanlış"],
                "match": "token"}


# Kelime fazinda yalnizca NET komutlar cikistir ("son", "bitti" gercek kelime olabilir).
_KEL_EXIT = {"cikis", "cik", "dur", "durdur", "kapat", "iptal", "vazgec", "vazgectim"}

# Hazirlik fazinda "oyunu baslat" onayi.
_KEL_READY = {"basla", "baslayalim", "baslat", "hazir", "hazirim", "evet",
              "tamam", "tamamdir", "hadi", "oyna", "olur", "devam", "ok", "tabii"}


def _cap(w: str) -> str:
    """Kelimenin ilk harfini Türkçe-doğru büyüt (i->İ, ı->I) — AI kelimesini gösterirken."""
    if not w:
        return w
    first = {"i": "İ", "ı": "I"}.get(w[0], w[0].upper())
    return first + w[1:]

# ——— Cikis anahtar kelimeleri (oyun fazinda genis kume) ————————————
_EXIT_WORDS = {
    "cikis", "cik", "dur", "durdur", "kapat", "yeter", "bitir", "bitti",
    "iptal", "son", "sohbet", "vazgec", "vazgectim", "yeterli",
}

# Turkce karakter -> ascii (kucuk), eslestime icin
_TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "I": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
    "â": "a", "î": "i", "û": "u",
})


def normalize(s: str) -> str:
    """Turkce metni eslestirme icin sadelestir: kucuk harf, ascii, tek bosluk."""
    s = (s or "").translate(_TR_MAP).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# STT'nin Turkcede en sik karistirdigi sesli/sessiz ciftleri esitle (normalize
# SONRASI, ascii metin uzerinde): kisa/kiza, dogru/tokru gibi tanima hatalari
# ayni fonetik iskelete duser. Sesli harf sadelestirmesi zaten _TR_MAP'te.
_FON_MAP = str.maketrans({"z": "s", "b": "p", "d": "t", "g": "k", "v": "f"})


def _fon(s: str) -> str:
    return s.translate(_FON_MAP)


def _token_yakin(w: str, hedefler) -> bool:
    """STT token'i hedef kelimelerden birine kucuk yazim farkiyla mi benziyor?
    Fonetik iskelet uzerinde OSA mesafesi; kisa hedefte 1, uzun hedefte 2."""
    if len(w) < 4:
        return False
    fw = _fon(w)
    for h in hedefler:
        tol = 1 if len(h) <= 6 else 2
        if abs(len(w) - len(h)) <= tol and \
                GameEngine._duzenleme_mesafesi(fw, _fon(h)) <= tol:
            return True
    return False


# "basla" onayinin STT'de bozulmus halleri icin fuzzy hedefler (_KEL_READY'nin
# uzun uyeleri). Hazirlik fazinda beklenen TEK sey onay oldugundan genis tolerans
# guvenlidir (yanlis-pozitif sadece oyunu baslatir).
_READY_FUZZY = ("basla", "baslat", "baslayalim", "hazirim", "tamam")


def _ready_mi(n: str) -> bool:
    """Hazirlik onayi mi? Once birebir kume, sonra fuzzy ('batla'~'basla')."""
    words = n.split()
    if n in _KEL_READY or any(w in _KEL_READY for w in words):
        return True
    return any(_token_yakin(w, _READY_FUZZY) for w in words)


# Hazir komut tetikleyicileri — control.js de ayni mantigi kullanir, ama
# backend de tanir (savunma amacli, ileride /api/send'e baglanabilir).
def is_game_trigger(text: str) -> bool:
    n = normalize(text)
    if n in ("oyun", "oyna", "oyun modu"):
        return True
    return bool(re.search(r"\boyun\s*oyna", n))


class GameEngine:
    """Tek ziyaretcili kiosk icin tekil oyun durumu.

    Faz: 'idle' (oyun yok) | 'menu' (oyun secimi) | 'kelime' (kural/hazirlik/oyun)
         | 'quiz' (es-zit/atasozu/dogru-yanlis).
    """

    # ——— Kelime Turetme parametreleri ————————————————————————
    USER_TURN_SECONDS = 20     # ziyaretci cevap suresi
    AI_TURN_SECONDS = 20       # AI dusunme suresi (gorsel bar)
    WORD_AI_GRACE = 2          # ilk N cevap neredeyse kesin dogru
    WORD_AI_BASE = 0.95        # baslangic basari olasiligi
    WORD_AI_DECAY = 0.30       # grace sonrasi her turda dusus
    WORD_AI_FLOOR = 0.05       # taban (AI ~4-5. cevapta yenilir)
    QUIZ_QUESTION_COUNT = 5    # bilgi yarismasi (es-zit/atasozu/dogru-yanlis): soru sayisi

    def __init__(self, bridge=None, word_llm=None, categories=None, categories_path=None,
                 session_logger=None, ea_data=None, ea_path=None,
                 atasozu_data=None, dogru_yanlis_data=None):
        # bridge: LLMBridge (kelime oyunu Ollama bilgisini buradan alir)
        self.bridge = bridge
        self._word_llm = word_llm   # WordLLM benzeri; None ise bridge'den lazy kurulur
        # session_logger: SessionLogger benzeri (log_game). Gozlem amacli; None ise
        # loglama sessizce atlanir — oyun akisini hicbir kosulda etkilemez.
        self.session_logger = session_logger
        # sergi_logger: SergiLogger benzeri (ziyaretci bazli sergi olcumu).
        # web_server atar; None ise tum sergi olaylari sessizce atlanir.
        self.sergi_logger = None
        self.phase = "idle"
        # ——— Tur jetonu (soru kaymasi korumasi) ————————————————————
        # Her girdi turunda artar. Uretilen HER payload o anki jetonu tasir;
        # istemci cevabini gonderirken ayni jetonu geri yollar. Sunucu farkli
        # jeton gorurse girdi BAYAT sayilir ve soru TUKETILMEDEN reddedilir
        # (web_server /api/game/input -> 409 stale_input).
        # Neden: /api/game/input sozlesmesinde soru kimligi yoktu; gec gelen her
        # POST (AI konusurken birikip TTS biter bitmez gonderilen kayit, tek
        # cevabin VAD ile ikiye bolunmesi, soru duyulmadan baslayan sayacin
        # timeout'u) o anki soruyu mesru sekilde tuketiyor ve ziyaretcinin
        # cevabi bir SONRAKI soruya kayiyordu.
        self.turn_id = 0
        # Test/sergi gunu sinirlamasi: None = tum oyunlar; ör. ("eszit","atasozu")
        # -> menude yalnizca bunlar gorunur ve secilebilir (web_server yonetir).
        self.izinli_oyunlar = None
        # Sesli-yalniz (sergi test gunu): True ise oyun metinleri "butona dokun"
        # yerine yalniz "basla" der ve aksiyon butonlari (Basla/Menu/Cikis) gizlenir.
        # Menu secim butonlari (Es/Zit, Atasozu) gorsel ipucu olarak KALIR.
        # web_server test_mode ile birlikte yonetir; normal modda davranis degismez.
        self.voice_only = False
        # AI'nin temali kelime havuzu: edebiyat + tarih + bilim BIRLESIMI.
        cats = categories if categories is not None else _load_word_categories(
            categories_path or _DEFAULT_CATS_PATH)
        cats = {k: list(v) for k, v in cats.items()}
        themed_words = []
        for c in _THEMED_CATEGORIES:
            themed_words.extend(cats.get(c, []))
        # Enjekte edilen ama _THEMED_CATEGORIES'te olmayan kategoriler de dahil
        # (test enjeksiyonu / ileride yeni tema) — havuz asla bos kalmasin.
        for c, ws in cats.items():
            if c not in _THEMED_CATEGORIES:
                themed_words.extend(ws)
        if not themed_words:
            # JSON yok/bos -> oyun yine oynansin diye yaygin kelimelere dus.
            themed_words = sorted(_TR_COMMON_WORDS)
        self._ai_pool = _index_by_first_letter(themed_words)
        # Gecerlilik kumesi: temali kelimeler + yaygin kelimeler (ziyaretci serbest,
        # bu kumedekiler LLM'e gitmeden aninda kabul).
        self._all_words = set(_TR_COMMON_WORDS)
        self._all_words.update(temiz_kelime(w) for w in themed_words)
        # Quiz saglayicilar (es/zit + atasozu + dogru/yanlis) — her biri tekduze soru uretir.
        # Veri ai/*.json'dan; okunamazsa gomulu yedege duser (mod calismaya devam eder).
        ea_src = ea_data if ea_data is not None else _load_es_zit(ea_path or _EA_DEFAULT_PATH)
        if not ea_src:
            ea_src = {temiz_kelime(k): v for k, v in _EA_FALLBACK.items()}
        ata_src = atasozu_data if atasozu_data is not None else _load_json_list(_ATASOZU_PATH)
        if not ata_src:
            ata_src = list(_ATASOZU_FALLBACK)
        dy_src = dogru_yanlis_data if dogru_yanlis_data is not None else _load_json_list(_DY_PATH)
        if not dy_src:
            dy_src = list(_DY_FALLBACK)
        self._providers = {
            "eszit": _EsZitProvider(ea_src),
            "atasozu": _AtasozuProvider(ata_src),
            "dogruyanlis": _DogruYanlisProvider(dy_src),
        }
        self._reset_word()
        self._reset_quiz()

    # ——— Kelime oyunu icin LLM (lazy; testte enjekte edilebilir) ————
    @property
    def word_llm(self):
        if self._word_llm is None and self.bridge is not None:
            from word_llm import WordLLM
            self._word_llm = WordLLM(
                self.bridge.url, self.bridge.model,
                keep_alive=getattr(self.bridge, "keep_alive", "60m"),
                num_ctx=getattr(self.bridge, "num_ctx", 8192),
            )
        return self._word_llm

    def _reset_word(self) -> None:
        self.word_used = set()
        self.word_turn = None              # "user" | "ai" | "hazir" | None (oyun yok/bitti)
        self.word_required_letter = None   # sonraki kelimenin baslamasi gereken harf
        self.word_last = None
        self.word_ai_count = 0             # AI'nin basarili cevap sayisi (yenilme egrisi)
        self.word_user_retried = False     # bu turda 1 tekrar hakki kullanildi mi
        self.word_score = {"ai": 0, "user": 0}
        self.word_starter = None

    def _reset_quiz(self) -> None:
        self.quiz_provider = None        # "eszit" | "atasozu" | "dogruyanlis"
        self.quiz_turn = None            # "hazir" | "soru" | None (yok/bitti)
        self.quiz_used = set()
        self.quiz_score = {"dogru": 0, "toplam": 0}
        self.quiz_q_index = 0
        self.quiz_current = None
        self.quiz_timeout_streak = 0     # ardisik cevapsiz zaman asimi sayaci

    # ——— Oyun oturumu loglama (gozlem; akisi DEGISTIRMEZ) ————————
    def _log_game(self, mode: str, event: str, detail: str = "") -> None:
        """Oyun baslangic/bitis ozetini session_logger'a yaz (varsa). Hata yutulur."""
        if self.session_logger is None:
            return
        try:
            self.session_logger.log_game(mode, event, detail)
        except Exception as e:  # noqa: BLE001 — loglama oyunu asla durdurmasin
            log.debug("Oyun logu yazilamadi: %s", e)

    def _sergi(self, metot: str, *args, **kwargs) -> None:
        """Sergi ziyaretci olayini sergi_logger'a ilet (varsa). Hata yutulur."""
        sl = self.sergi_logger
        if sl is None:
            return
        try:
            getattr(sl, metot)(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — loglama oyunu asla durdurmasin
            log.debug("Sergi logu yazilamadi: %s", e)

    # ——— Disa acilan API ————————————————————————————————————
    def _bump_turn(self) -> int:
        """Yeni girdi turu basladi — onceki jetonla gelen girdiler bayatlar.

        Durum degistiren TUM giris noktalarinda (start/handle/exit/ai_turn)
        cagrilir; boylece bir payload'a karsilik YALNIZCA BIR girdi kabul edilir."""
        self.turn_id += 1
        return self.turn_id

    def start(self) -> dict:
        """Oyunu baslat: DUZ 4 secenekli menuye gec (sabit cevap, LLM yok)."""
        self._bump_turn()
        self.phase = "menu"
        self._reset_word()
        self._reset_quiz()
        return self._menu_payload()

    # ——— Menu fazi (duz menu; izinli_oyunlar sinirlar) ————————————
    _MENU_TUM = (
        {"key": "kelime",      "label": "🔤 Kelime Türetme"},
        {"key": "eszit",       "label": "🔁 Eş/Zıt Anlam"},
        {"key": "atasozu",     "label": "📜 Atasözü"},
        {"key": "dogruyanlis", "label": "✅ Doğru/Yanlış"},
    )

    def _oyun_izinli(self, key: str) -> bool:
        return self.izinli_oyunlar is None or key in self.izinli_oyunlar

    def _menu_buttons(self):
        return [dict(b) for b in self._MENU_TUM if self._oyun_izinli(b["key"])]

    # ——— Sergi ekrani ses yonlendirme baloncugu ————————————————————
    # payload["hint"]: ziyaretcinin O AN soylemesi beklenen sey. Sergi ekraninda
    # secenek ovalleriyle ayni bantta 🎤'li kucuk bir balon olarak cizilir.
    # TTS'e GIRMEZ (yanit metinleri degismedi -> ses cache isabeti korunur).
    def _hint_basla(self) -> str:
        return "«Başla» de" if self.voice_only else "«Başla» de ya da butona dokun"

    def _menu_payload(self, reprompt=False) -> dict:
        # Metin butonlardan turetilir; tum oyunlar izinliyken eski sabit
        # metinlerle BIREBIR ayni kalir (TTS on-uretim cache'i bozulmasin).
        btns = self._menu_buttons()
        labels = " · ".join(b["label"] for b in btns)
        adlar = [b["label"].split(" ", 1)[1] for b in btns]
        secenekler = ((", ".join(adlar[:-1]) + " ya da " + adlar[-1])
                      if len(adlar) > 1 else (adlar[0] if adlar else ""))
        soyle = "Söyle" if self.voice_only else "Dokun ya da söyle"
        yanit = (
            f"Hmm, tam anlamadım :) Hangisini oynayalım — {secenekler}?" if reprompt else
            f"Süper! Hangisini oynayalım? {soyle}: {labels}"
        )
        return {
            "game": "menu",
            "phase": "menu",
            "turn_id": self.turn_id,
            "kind": "reprompt" if reprompt else "menu",
            "turn": "secim",
            "jest_id": _JEST["menu"],
            "yogunluk": 0.8,
            "yanit": yanit,
            "score": None,
            "ai_move": None,
            "outcome": None,
            "buttons": self._menu_buttons(),
            "hint": ("Oyunun adını söyle" if self.voice_only
                     else "Dokun ya da oyunun adını söyle"),
            "ended": False,
        }

    def _handle_menu(self, n: str) -> dict:
        """Menuden oyun sec (buton key'i veya dogal dil). Anlasilmazsa tekrar sor.
        izinli_oyunlar disindaki secimler de tekrar-sor'a duser (test modu).

        STT toleransi: bosluklu bolunme ("ata sözü") icin birlesik metin (j),
        kucuk tanima hatalari ("atasözler", "eşit anlam") icin _token_yakin."""
        words = n.split()
        j = n.replace(" ", "")   # "ata sozu" -> "atasozu" (STT kelimeyi bolebilir)
        if ((n in ("kelime", "1", "bir") or "kelime" in words or "turet" in j)
                and self._oyun_izinli("kelime")):
            return self._start_kelime()
        # NOT: "anlam" TAM KELIME olarak aranir ('anlamadım' tetiklemesin —
        # reprompt metni bizzat "tam anlamadım" diyor, ziyaretci tekrarlayabilir).
        # "esit": STT "eş zıt"i cok sik "eşit" diye yazar — menu baglaminda kabul.
        if ((n in ("eszit", "2", "iki") or "es" in words or "zit" in words
                or "esanlam" in j or "zitanlam" in j or "eszit" in j
                or "anlam" in words or "esit" in words
                or any(w.startswith("anlaml") for w in words)   # "anlamlısı" (ama "anlamadım" degil)
                or any(_token_yakin(w, ("anlam", "eszit")) for w in words))
                and self._oyun_izinli("eszit")):
            self.quiz_provider = "eszit"
            return self._start_quiz()
        if ((n in ("atasozu", "3", "uc") or "atasoz" in j or "deyim" in n
                or any(_token_yakin(w, ("atasozu",)) for w in words))
                and self._oyun_izinli("atasozu")):
            self.quiz_provider = "atasozu"
            return self._start_quiz()
        if ((n in ("dogruyanlis", "dy", "4", "dort") or "dogru" in n or "yanlis" in n)
                and self._oyun_izinli("dogruyanlis")):
            self.quiz_provider = "dogruyanlis"
            return self._start_quiz()
        self._sergi("anlamsiz", "menu", n)
        return self._menu_payload(reprompt=True)

    def exit(self) -> dict:
        """Oyundan cik, sohbet moduna don."""
        self._bump_turn()
        # Gozlem: yarim kalan oyunun ozetini logla (reset ONCESI okunur; akis degismez).
        if self.phase == "kelime" and self.word_turn is not None:
            self._log_game("kelime", "yarim_birakildi",
                           f"skor=ai:{self.word_score['ai']} "
                           f"ziyaretci:{self.word_score['user']}")
            self._sergi("game_end", "yarim_birakildi",
                        skor=f"ai:{self.word_score['ai']} "
                             f"ziyaretci:{self.word_score['user']}")
        self.phase = "idle"
        self._reset_word()
        self._reset_quiz()
        return {
            "phase": "idle",
            "turn_id": self.turn_id,
            "kind": "exit",
            "user_echo": None,
            "jest_id": _JEST["exit"],
            "yogunluk": 0.6,
            "yanit": random.choice(_TXT["exit"]),
            "score": None,
            "ai_move": None,
            "outcome": None,
            "buttons": [],
            "ended": True,
        }

    def handle(self, text: str, timeout: bool = False, button: bool = False) -> dict:
        """Faz'a gore girdiyi isle ve gosterilecek payload don.

        timeout=True: kelime oyununda ziyaretci suresi doldu sinyali.
        button=True: girdi panel BUTONUNDAN geldi (sesli degil) — cikis komutlari
        her fazda gecerli kalir.

        NOT: Jeton dogrulamasi BURADA DEGIL cagirandadir (web_server): bu metoda
        gelindiginde girdi zaten kabul edilmis sayilir ve tur tuketilir.
        DIKKAT: timeout=True aktif tur YOKKEN buraya gelirse (yarisma bitmis,
        menu, idle) asagidaki dallar onu girdi sanip oyunu YENIDEN BASLATIR;
        bu yuzden web_server /api/game/input aktif tur yoksa timeout'u 409 ile
        reddeder. Yeni bir cagiran eklenirse ayni korumayi tasi.
        """
        self._bump_turn()
        n = normalize(text)

        # Cikis: aktif oyunda yalnizca NET komutlar ("son"/"bitti" gercek kelime olabilir);
        # diger durumda genis kelime kumesi gecerli. Timeout sinyalinde cikis kontrolu yok.
        # AKTIF QUIZ'DE SESLI CIKIS YOK (buton haric): gurultu/yanki tek kelimelik
        # "dur"/"çıkış" uretebiliyor ve oyunu ORTASINDA bitiriyordu. Yarisma ancak
        # butonla, sorular bitince ya da 2 ardisik cevapsiz zaman asimiyla biter;
        # sesli komut burada dusuk-guvenilirlikli sayilir ve normal girdi gibi islenir.
        if not timeout:
            active_game = ((self.phase == "kelime" and self.word_turn is not None) or
                           (self.phase == "quiz" and self.quiz_turn is not None))
            if active_game:
                if n in _KEL_EXIT and (button or self.phase != "quiz"):
                    return self.exit()
            elif self.phase == "menu" and self.voice_only and not button:
                # Sergi menusunde SESLI cikis komutu yok: gurultu/yanki "dur"/"bitti"
                # uretip menuyu aniden kapatabiliyordu. Menu reprompt eder; ziyaretci
                # gercekten yoksa bosta sayaci goz moduna dondurur.
                pass
            elif n in _EXIT_WORDS or any(w in _EXIT_WORDS for w in n.split()):
                return self.exit()

        if self.phase == "menu":
            return self._handle_menu(n)

        if self.phase == "kelime":
            if self.word_turn is None:
                # oyun bitti — "menu" -> ana menu; aksi halde yeni Kelime oyunu
                if n in ("menu", "anamenu") or "menu" in n.split():
                    return self.start()
                return self._start_kelime()
            if self.word_turn == "hazir":
                # kurallar anlatildi, oyuncunun "basla" onayini bekliyoruz
                return self._handle_kelime_ready(text)
            # Kelime eslestirmesi Turkce harfleri korur (normalize degil, ham metin)
            return self._handle_kelime(text, timeout)

        if self.phase == "quiz":
            if self.quiz_turn is None:
                # yarisma bitti — "menu" -> ana menu; aksi halde ayni yarismayi tekrar
                if n in ("menu", "anamenu") or "menu" in n.split():
                    return self.start()
                return self._start_quiz()
            if self.quiz_turn == "hazir":
                # kurallar anlatildi, "basla" onayini bekliyoruz
                return self._handle_quiz_ready(text, button)
            return self._handle_quiz(text, timeout)

        # idle iken girdi gelirse menuyu ac
        return self.start()

    # ——— Kelime Turetme fazi ————————————————————————————————
    @staticmethod
    def _kel_buttons():
        return [{"key": "cikis", "label": "Çıkış"}]

    @staticmethod
    def _kel_end_buttons():
        return [{"key": "kelime", "label": "🔤 Yeni oyun"},
                {"key": "menu", "label": "🏠 Menü"},
                {"key": "cikis", "label": "Çıkış"}]

    @staticmethod
    def _kel_ready_buttons():
        return [{"key": "basla", "label": "▶ Başla"},
                {"key": "cikis", "label": "Çıkış"}]

    def _kel_payload(self, kind, *, turn, jest_id, yanit, yogunluk=0.8,
                     required_letter=None, ai_word=None, user_word=None,
                     timer=None, ended=False, outcome=None, buttons=None,
                     hint=None):
        return {
            "game": "kelime",
            "phase": self.phase,
            "turn_id": self.turn_id,
            "category": None,          # tek, temasiz havuz (edebiyat+tarih+bilim birlesik)
            "kind": kind,
            "turn": turn,
            "required_letter": required_letter,
            "ai_word": ai_word,
            "user_word": user_word,
            "jest_id": jest_id,
            "yogunluk": yogunluk,
            "yanit": yanit,
            "score": dict(self.word_score),
            "timer": timer,
            "buttons": buttons if buttons is not None else self._kel_buttons(),
            "hint": hint,
            "ended": ended,
            "outcome": outcome,
        }

    def _word_ai_success_p(self) -> float:
        """AI'nin bu turda dogru cevap verme olasiligi — grace sonrasi duser."""
        n = self.word_ai_count
        if n < self.WORD_AI_GRACE:
            return self.WORD_AI_BASE
        return max(self.WORD_AI_FLOOR,
                   self.WORD_AI_BASE - self.WORD_AI_DECAY * (n - self.WORD_AI_GRACE + 1))

    def _gecerli_kelime(self, w: str) -> bool:
        """Kelime gercek bir Turkce sozcuk mu? Once yerel yaygin-kelime sozlugu
        (LLM'siz, aninda) — cogu turda Ollama'ya hic gidilmez, gecikme sifir.
        Sozlukte yoksa LLM'e sor (lenient: model down/kararsiz -> kabul)."""
        if w in self._all_words:
            return True
        return self.word_llm.gecerli_mi(w)

    def _pick_ai_word(self, req_letter, used):
        """AI'nin temali kelimesi: edebiyat+tarih+bilim BIRLESIK havuzundan
        `req_letter` ile baslayan, kullanilmamis rastgele kelime. O harfte kelime
        yoksa None (AI pes eder)."""
        pool = self._ai_pool
        if req_letter:
            cands = [w for w in pool.get(req_letter, []) if w not in used]
        else:
            cands = [w for ws in pool.values() for w in ws if w not in used]
        return random.choice(cands) if cands else None

    def _start_kelime(self) -> dict:
        """Kurallari anlat + 'hazirsan baslayalim' de. Oyun HENÜZ başlamaz (süre yok)."""
        self.phase = "kelime"
        self._reset_word()
        self.word_turn = "hazir"   # onay bekleniyor
        self._sergi("game_select", "kelime")
        yanit = (
            "Kelime türetme oynayalım! Ben bir kelime söylerim. Sen de son "
            "harfiyle başlayan yeni bir kelime söyle. Sırayla devam ederiz. "
            "Aynı kelimeyi iki kez kullanamayız. Her tur için "
            f"{self.USER_TURN_SECONDS} saniyen var. Hazırsan 'başla' de!"
        )
        return self._kel_payload(
            "ready", turn="hazir", jest_id=random.choice(_JEST["kel_intro"]),
            yanit=yanit, yogunluk=0.8, timer=None,
            buttons=self._kel_ready_buttons(), hint=self._hint_basla(),
        )

    def _handle_kelime_ready(self, text: str) -> dict:
        """Hazırlık fazı: 'başla'/'hazırım' gelince gerçek oyunu başlat, yoksa tekrar sor."""
        n = normalize(text)
        # Sozlu "menü" hazirlik ekranindan ana menuye doner (quiz ile simetrik).
        if n in ("menu", "anamenu") or "menu" in n.split():
            return self.start()
        if _ready_mi(n):
            return self._begin_kelime()
        self._sergi("anlamsiz", "hazir", n)
        return self._kel_payload(
            "ready", turn="hazir", jest_id="bekle",
            yanit="Hazır olunca 'başla' de ya da butona dokun :)", yogunluk=0.6,
            timer=None, buttons=self._kel_ready_buttons(), hint=self._hint_basla(),
        )

    def _begin_kelime(self) -> dict:
        """Oyunu gerçekten başlat: başlayan rastgele, ilk kelime/sıra + süre.
        Oyun sırasında AI yalnızca KELİMEYLE cevap verir (yanit = kelime)."""
        self.word_starter = "ai" if random.random() < 0.5 else "user"
        self._log_game("kelime", "basladi", f"baslayan={self.word_starter}")
        self._sergi("game_begin")
        if self.word_starter == "ai":
            kelime = self._pick_ai_word(None, self.word_used) or random.choice(_KEL_SEED)
            self.word_used.add(temiz_kelime(kelime))
            self.word_last = kelime
            self.word_required_letter = son_harf(kelime)
            self.word_turn = "user"
            yanit = _cap(kelime)          # AI sadece kelimesini söyler
            ai_word = kelime
        else:
            self.word_turn = "user"
            self.word_required_letter = None   # ilk kelime serbest
            yanit = "Sen başla — bir kelime söyle!"
            ai_word = None
        return self._kel_payload(
            "intro", turn="user", jest_id=random.choice(_JEST["kel_intro"]),
            yanit=yanit, yogunluk=0.8,
            required_letter=self.word_required_letter, ai_word=ai_word,
            timer={"seconds": self.USER_TURN_SECONDS, "who": "user"},
        )

    def _kel_user_lose(self, reason: str) -> dict:
        """reason: 'timeout' | 'invalid' — ziyaretci kaybeder, AI kazanir."""
        self.word_turn = None
        self._log_game("kelime", "bitti",
                       f"kazanan=ai sebep={reason} "
                       f"skor=ai:{self.word_score['ai']} ziyaretci:{self.word_score['user']}")
        self._sergi("game_end", "bitti",
                    skor=f"kazanan=ai ai:{self.word_score['ai']} "
                         f"ziyaretci:{self.word_score['user']}")
        txt_key = "kel_user_lose_timeout" if reason == "timeout" else "kel_user_lose_invalid"
        return self._kel_payload(
            "ended", turn=None, jest_id=random.choice(_JEST["kel_user_lose"]),
            yanit=random.choice(_TXT[txt_key]), yogunluk=0.8,
            timer=None, ended=True, outcome="ai_win",
            buttons=self._kel_end_buttons(),
            hint="«Yeni oyun» ya da «Menü» de",
        )

    def _handle_kelime(self, text: str, timeout: bool) -> dict:
        # Sure doldu → tekrar hakki YOK, kullanici kaybeder
        if timeout:
            return self._kel_user_lose("timeout")

        w = temiz_kelime(text)
        req = self.word_required_letter

        # Gecersizlik nedeni: bos/kisa, yanlis harf, kullanilmis, gercek kelime degil
        reason = None
        if len(w) < 2:
            reason = "invalid"
        elif req and w[0] != req:
            reason = "letter"
        elif w in self.word_used:
            reason = "used"
        elif not self._gecerli_kelime(w):
            reason = "invalid"

        if reason:
            if not self.word_user_retried:
                self.word_user_retried = True
                txt_key = {"letter": "kel_retry_letter", "used": "kel_retry_used",
                           "invalid": "kel_retry_invalid"}[reason]
                harf = req or (w[0] if w else "")
                return self._kel_payload(
                    "retry", turn="user", jest_id=random.choice(_JEST["kel_retry"]),
                    yanit=random.choice(_TXT[txt_key]).format(harf=harf), yogunluk=0.65,
                    required_letter=req,
                    timer={"seconds": self.USER_TURN_SECONDS, "who": "user"},
                )
            # 2. hata → kayip
            return self._kel_user_lose("invalid")

        # Gecerli kelime → kabul, sira AI'ya
        self.word_used.add(w)
        self.word_last = w
        self.word_score["user"] += 1
        self.word_required_letter = son_harf(w)
        self.word_turn = "ai"
        self.word_user_retried = False
        return self._kel_payload(
            "user_ok", turn="ai", jest_id=random.choice(_JEST["kel_user_ok"]),
            yanit=random.choice(_TXT["kel_user_ok"]), yogunluk=0.85,
            required_letter=self.word_required_letter, user_word=w,
            timer={"seconds": self.AI_TURN_SECONDS, "who": "ai"},
        )

    def ai_turn(self) -> dict:
        """Sira AI'dayken cagrilir: AI kelime bulur ya da pes eder (yenilme egrisi)."""
        self._bump_turn()   # AI hamlesi de yeni tur: onceki tura ait girdiler bayatlar
        if self.phase != "kelime" or self.word_turn != "ai":
            return self._kel_payload(
                "noop", turn=self.word_turn, jest_id="bekle", yanit="", yogunluk=0.5,
                required_letter=self.word_required_letter, timer=None)

        req = self.word_required_letter
        # AI kelimeleri saf havuzdan (LLM yok) -> Ollama'dan bagimsiz, halusinasyonsuz.
        basarili = random.random() < self._word_ai_success_p()
        kelime = self._pick_ai_word(req, self.word_used) if basarili else None
        ai_error = False  # AI Ollama gerektirmez; "Ollama-down -> sessiz pes" ayrimi yok

        if kelime:
            self.word_used.add(temiz_kelime(kelime))
            self.word_last = kelime
            self.word_ai_count += 1
            self.word_score["ai"] += 1
            self.word_required_letter = son_harf(kelime)
            self.word_turn = "user"
            streak = self.word_ai_count >= 3
            jest_pool = "kel_ai_streak" if streak else "kel_ai_word"
            yanit = _cap(kelime)   # oyun sirasinda AI yalnizca kelimeyle cevap verir
            return self._kel_payload(
                "ai_word", turn="user", jest_id=random.choice(_JEST[jest_pool]),
                yanit=yanit, yogunluk=0.9 if streak else 0.85,
                required_letter=self.word_required_letter, ai_word=kelime,
                timer={"seconds": self.USER_TURN_SECONDS, "who": "user"},
            )

        # AI pes etti → kullanici kazanir
        self.word_turn = None
        self._log_game("kelime", "bitti",
                       f"kazanan=ziyaretci sebep=ai_pes "
                       f"skor=ai:{self.word_score['ai']} ziyaretci:{self.word_score['user']}")
        self._sergi("game_end", "bitti",
                    skor=f"kazanan=ziyaretci ai:{self.word_score['ai']} "
                         f"ziyaretci:{self.word_score['user']}")
        payload = self._kel_payload(
            "ai_concede", turn=None, jest_id=random.choice(_JEST["kel_ai_lose"]),
            yanit=random.choice(_TXT["kel_ai_lose"]).format(harf=req or "?"),
            yogunluk=0.85, timer=None, ended=True, outcome="user_win",
            buttons=self._kel_end_buttons(),
            hint="«Yeni oyun» ya da «Menü» de",
        )
        payload["ai_error"] = ai_error  # True ise: gercek pes degil, Ollama erisilemedi
        return payload

    # ——— Bilgi Yarismasi (ortak quiz motoru: es-zit/atasozu/dogru-yanlis) ————
    def _quiz_ready_buttons(self):
        # Sesli-yalniz (sergi test gunu): aksiyon butonlari gizli — ziyaretci "basla" der.
        if self.voice_only:
            return []
        return [{"key": "basla", "label": "▶ Başla"},
                {"key": "menu", "label": "🏠 Menü"},
                {"key": "cikis", "label": "Çıkış"}]

    def _quiz_end_buttons(self):
        if self.voice_only:
            return []
        return [{"key": "tekrar", "label": "🔁 Yeni yarışma"},
                {"key": "menu", "label": "🏠 Menü"},
                {"key": "cikis", "label": "Çıkış"}]

    def _quiz_payload(self, kind, *, turn, jest_id, yanit, yogunluk=0.8,
                      quiz_progress=None, dogru_mu=None, timer=None, ended=False,
                      buttons=None, user_display=None, hint=None):
        return {
            "game": "quiz",
            "phase": self.phase,
            "turn_id": self.turn_id,
            "kind": kind,
            "turn": turn,
            "quiz": self.quiz_provider,
            "jest_id": jest_id,
            "yogunluk": yogunluk,
            "yanit": yanit,
            "score": None,                 # ilerleme quiz_progress'te
            "quiz_progress": quiz_progress,
            "dogru_mu": dogru_mu,
            # Dogru kabul edilen cevabin ekran hali: istemci kullanici balonundaki
            # ham STT metnini bununla degistirir (fuzzy kabul gorunur olsun).
            "user_display": user_display,
            "timer": timer,
            "buttons": (buttons if buttons is not None
                        else ([] if self.voice_only else [{"key": "cikis", "label": "Çıkış"}])),
            "hint": hint,
            "ended": ended,
            "outcome": None,
        }

    def _start_quiz(self) -> dict:
        """Secilen quiz icin kurallari anlat + 'basla' bekle (oyun HENUZ baslamaz)."""
        self.phase = "quiz"
        self.quiz_used = set()
        self.quiz_score = {"dogru": 0, "toplam": 0}
        self.quiz_q_index = 0
        self.quiz_current = None
        self.quiz_timeout_streak = 0
        self.quiz_turn = "hazir"
        self._sergi("game_select", "quiz", self.quiz_provider)
        prov = self._providers[self.quiz_provider]
        kapanis = ("Hazırsan başlayalım — 'başla' de!" if self.voice_only
                   else "Hazırsan başlayalım — 'başla' de ya da butona dokun!")
        yanit = prov.intro(self.QUIZ_QUESTION_COUNT) + " " + kapanis
        return self._quiz_payload(
            "quiz_ready", turn="hazir", jest_id=random.choice(_JEST["kel_intro"]),
            yanit=yanit, yogunluk=0.8, timer=None, buttons=self._quiz_ready_buttons(),
            hint=self._hint_basla())

    def _handle_quiz_ready(self, text: str, button: bool = False) -> dict:
        n = normalize(text)
        # Hazir ekranindan ana menuye donus yalnizca '🏠 Menü' BUTONUYLA (panel).
        # Sergi (voice_only) yolunda sesli "menü" KABUL EDILMEZ: STT gurultu/yankidan
        # "menü" uretebiliyor ve oyun ortasinda baslangic menusune donuyordu.
        # Kullanici kurali: aktif oyunu yalniz art arda 2 cevapsiz zaman asimi bitirir.
        if (button or not self.voice_only) and (
                n in ("menu", "anamenu") or "menu" in n.split()):
            return self.start()
        if _ready_mi(n):
            return self._begin_quiz()
        self._sergi("anlamsiz", "hazir", n)
        bekle_txt = ("Hazır olunca 'başla' de :)" if self.voice_only
                     else "Hazır olunca 'başla' de ya da butona dokun :)")
        return self._quiz_payload(
            "quiz_ready", turn="hazir", jest_id="bekle",
            yanit=bekle_txt, yogunluk=0.6,
            timer=None, buttons=self._quiz_ready_buttons(),
            hint=self._hint_basla())

    def _begin_quiz(self) -> dict:
        self.quiz_used = set()
        self.quiz_score = {"dogru": 0, "toplam": 0}
        self.quiz_q_index = 0
        self.quiz_timeout_streak = 0
        self._sergi("game_begin")
        return self._quiz_ask_next()

    def _quiz_ask_next(self, prefix=None, dogru_mu=None, user_display=None) -> dict:
        """Sonraki soruyu sor; soru kalmadi/sayi doldu -> bitir.
        prefix: bir onceki cevabin geri bildirimi (ayni mesaja eklenir).
        user_display: onceki cevap fuzzy kabul edildiyse balona yazilacak hali."""
        if self.quiz_q_index >= self.QUIZ_QUESTION_COUNT:
            return self._quiz_end(prefix=prefix, user_display=user_display)
        prov = self._providers[self.quiz_provider]
        q = prov.next_question(self.quiz_used)
        if q is None:
            return self._quiz_end(prefix=prefix, user_display=user_display)
        self.quiz_used.add(q["id"])
        self.quiz_current = q
        self.quiz_q_index += 1
        self.quiz_turn = "soru"
        yanit = f"{prefix} {q['prompt']}" if prefix else q["prompt"]
        if dogru_mu is True:
            jest = random.choice(_JEST["kel_user_ok"])
        elif dogru_mu is False:
            jest = random.choice(_JEST["kel_retry"])
        else:
            jest = random.choice(_JEST["kel_intro"])
        return self._quiz_payload(
            "quiz_question", turn="soru", jest_id=jest, yanit=yanit, yogunluk=0.85,
            dogru_mu=dogru_mu, user_display=user_display,
            quiz_progress=f"Soru {self.quiz_q_index}/{self.QUIZ_QUESTION_COUNT} · Doğru {self.quiz_score['dogru']}",
            timer={"seconds": self.USER_TURN_SECONDS, "who": "user"})

    def _quiz_check(self, q, text: str):
        """Cevap kontrolu — token (kume kesisimi) veya substring (atasozu).

        Donus: ESLESEN kabul cevabi (accept_norm uyesi, truthy) veya None.
        Bool yerine eslesen cevabin donmesi, fuzzy kabulde ekrana ham STT yerine
        kabul edilen cevabin yazilabilmesi icindir (accept_display ile).

        Cevaplar DOSYADA yazili oldugundan eslestirme STT'ye karsi hosgoruludur
        (sergi ilkesi: yanlis RED, yanlis KABULDEN kotudur):
        - Token: 5-7 harfte 1, 8+ harfte 2 duzenleme mesafesi; mesafe fonetik
          iskelet uzerinde olculur ('kıza'~'kısa', 'tokru'~'dogru'). Kisa
          kelimeler (<=4) fonetik AYNILIK ister — 'uzun'~'uzak' gibi gercek
          kelime karisimlarina mesafe toleransi verilmez.
        - Substring (atasozu): tam icerme YA DA kabul cevabinin ayirt edici
          kelimelerinin cogu (fuzzy) soylenmisse dogru ('göl oldu'~'göl olur')."""
        un = normalize(text)
        if not un:
            return None
        acc = q["accept_norm"]
        if q.get("match") == "substring":
            for a in acc:
                if a and (a in un or un in a):
                    return a
            return self._substring_yaklasik(acc, un)
        cand = {un} | set(un.split())
        if " " in un:
            cand.add(un.replace(" ", ""))   # STT kelimeyi boldu: "koca man"
        ortak = acc & cand
        if ortak:
            return next(iter(ortak))
        fon_cand = {_fon(c) for c in cand}
        for a in acc:
            fa = _fon(a)
            if fa in fon_cand:
                return a
            tol = 2 if len(a) >= 8 else (1 if len(a) >= 5 else 0)
            if tol and any(self._duzenleme_mesafesi(fa, c) <= tol for c in fon_cand):
                return a
        return None

    def _substring_yaklasik(self, acc, un: str):
        """Atasozu icin yaklasik dogru: kabul cevabinin ayirt edici (>=3 harf,
        dolgu olmayan) kelimelerinin >=%60'i, fonetik/yazim toleransiyla
        transkriptte geciyorsa dogru say. 'göl oluyor', 'iki elin sesi bar'
        gibi STT bozulmalari boylece cevap yanmaz.
        Donus: eslesen kabul cevabi veya None (_quiz_check sozlesmesi)."""
        tokens = un.split()
        for a in acc:
            a_toks = [t for t in a.split() if len(t) >= 3 and t not in self._YAKIN_STOP]
            if not a_toks:
                continue
            gerek = max(1, -(-len(a_toks) * 3 // 5))   # ceil(0.6 * n)
            hit = 0
            for at in a_toks:
                fat = _fon(at)
                esik = 0 if len(at) < 4 else (1 if len(at) <= 5 else 2)
                if any(_fon(t) == fat
                       or (esik and self._duzenleme_mesafesi(_fon(t), fat) <= esik)
                       for t in tokens):
                    hit += 1
            if hit >= gerek:
                return a
        return None

    # Quiz onay replikleri — SES ON-URETIMI icin sabit/dusuk-varyant. Rastgele
    # tezahurat cevaba YAPISTIRILMAZ: onek (tezahurat/uyari) ayri cumle, "Cevap: X"
    # ayri paylasilan cumle olur; boylece her cevap TEK kez seslendirilir (cache).
    _QUIZ_DOGRU_CHEER = ("Doğru bildin!", "Harika, bildin!", "Aferin, doğru!")
    # Yanlis-cevap onekleri iki havuz: YAKIN yalnizca cevap gercekten yakinsa
    # (kucuk yazim farki / kismi eslesme) soylenir; digerinde NOTR havuz doner.
    # DIKKAT: her onek EN AZ 10 karakter olmali — cumle bolucunun (SENT_MIN_LEN)
    # kisa parcayi "Cevap: X." ile birlestirip TTS cache'ini iskalamamasi icin.
    _QUIZ_YAKIN = ("Çok yaklaştın!", "Az kalmıştı!", "Ucundan kaçtı!")
    _QUIZ_YANLIS = ("Olmadı bu sefer!", "Bilemedin, olsun!", "Bu biraz zordu galiba!")

    @staticmethod
    def _duzenleme_mesafesi(a: str, b: str) -> int:
        """OSA duzenleme mesafesi (ekle/sil/degistir + komsu harf takasi=1) —
        kisa kelimeler icin saf Python yeterli."""
        if a == b:
            return 0
        if not a or not b:
            return len(a) + len(b)
        prev2 = None
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                d = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
                if prev2 is not None and j > 1 and i > 1 and ca == b[j - 2] and a[i - 2] == cb:
                    d = min(d, prev2[j - 2] + 1)
                cur.append(d)
            prev2, prev = prev, cur
        return prev[-1]

    # Yakinlik tespitinde SAYILMAYAN yaygin dolgu kelimeleri (normalize edilmis):
    # "para olur" gibi alakasiz cevaplarda tek basina "olur" yakinlik saymasin.
    _YAKIN_STOP = frozenset({
        "olur", "olmaz", "gelir", "gider", "eder", "etmez", "yapar", "olsun",
        "vardir", "yoktur", "iyidir", "degildir", "kadar", "gibi", "icin", "bir",
    })

    def _quiz_yakin_mi(self, q, text: str) -> bool:
        """Yanlis cevap gercekten 'yakin' miydi? Yakin = kabul cevabinin ayirt
        edici bir kelimesi soylenmis (atasozu: 'göl oldu' ~ 'göl olur') YA DA
        kucuk yazim farki var ('berayz' ~ 'beyaz'). Dogru/Yanlis'ta yakinlik
        anlamsiz (iki secenek var) -> her zaman False."""
        if self.quiz_provider == "dogruyanlis":
            return False
        un = normalize(text)
        if not un:
            return False
        tokens = set(un.split())
        for a in q["accept_norm"]:
            a_tokens = [t for t in a.split() if len(t) >= 3 and t not in self._YAKIN_STOP]
            if any(t in tokens for t in a_tokens):
                return True
            for at in a_tokens:
                if len(at) < 4:
                    continue  # 3 harfli tokenda mesafe-1 cok gevsek ('gol'~'yol')
                esik = 1 if len(at) <= 5 else 2
                if any(self._duzenleme_mesafesi(t, at) <= esik
                       for t in tokens if t not in self._YAKIN_STOP):
                    return True
        return False

    def _handle_quiz(self, text: str, timeout: bool) -> dict:
        # Ust uste 2 soru CEVAPSIZ zaman asimina ugradiysa ziyaretci gitti say:
        # yarismayi kapat (sergi kurali — yarim oyun ekranda asili kalmasin).
        # Herhangi bir gercek cevap sayaci sifirlar; oyun ancak boyle, butonla
        # ya da sorular bitince sona erer.
        if timeout:
            self.quiz_timeout_streak += 1
            self._sergi("question", "timeout")
            if self.quiz_timeout_streak >= 2:
                self._log_game("quiz", "terk_edildi",
                               f"tur={self.quiz_provider} "
                               f"skor={self.quiz_score['dogru']}/{self.quiz_score['toplam']}")
                self._sergi("game_end", "terk_edildi",
                            dogru=self.quiz_score["dogru"],
                            toplam=self.quiz_score["toplam"])
                return self.exit()
        else:
            self.quiz_timeout_streak = 0
        q = self.quiz_current
        beklenen = (q["reveal"] if q else "?").rstrip(" .")  # cift nokta olmasin
        self.quiz_score["toplam"] += 1
        eslesen = None if (timeout or not q) else self._quiz_check(q, text)
        user_display = None
        if eslesen:
            self.quiz_score["dogru"] += 1
            # 3 sabit tezahurat arasinda donusumlu (deterministik -> pre-gen dostu)
            cheer = self._QUIZ_DOGRU_CHEER[self.quiz_score["dogru"] % len(self._QUIZ_DOGRU_CHEER)]
            geri = f"{cheer} Cevap: {beklenen}."
            dogru = True
            # Fuzzy kabulde kullanici balonunda ham STT degil kabul edilen
            # cevabin kendisi gorunsun ("göl oldu" yazip dogru sayilmasi kafa
            # karistiriyordu) — istemci user_display'i balona geri yazar.
            user_display = (q.get("accept_display") or {}).get(eslesen)
            self._sergi("question", "dogru")
        else:
            if timeout:
                onek = "Süre doldu!"
            else:
                havuz = (self._QUIZ_YAKIN if q and self._quiz_yakin_mi(q, text)
                         else self._QUIZ_YANLIS)
                yanlis_n = self.quiz_score["toplam"] - self.quiz_score["dogru"]
                onek = havuz[yanlis_n % len(havuz)]
            geri = f"{onek} Cevap: {beklenen}."     # "Cevap: X" cumlesi dogru/yanlis'ta ORTAK
            dogru = False
            if not timeout:
                self._sergi("question", "yanlis")
        return self._quiz_ask_next(prefix=geri, dogru_mu=dogru, user_display=user_display)

    def _quiz_end(self, prefix=None, user_display=None) -> dict:
        self.quiz_turn = None
        self._log_game("quiz", "bitti",
                       f"tur={self.quiz_provider} skor={self.quiz_score['dogru']}/"
                       f"{self.quiz_score['toplam']}")
        self._sergi("game_end", "bitti",
                    dogru=self.quiz_score["dogru"],
                    toplam=self.quiz_score["toplam"])
        d = self.quiz_score["dogru"]
        t = self.quiz_score["toplam"] or self.QUIZ_QUESTION_COUNT
        if d >= t * 0.8:
            jest = random.choice(_JEST["kel_user_ok"]); kapanis = "Harikasın!"
        elif d >= t * 0.4:
            jest = random.choice(_JEST["kel_intro"]); kapanis = "Güzel oynadın!"
        else:
            jest = "huzur"; kapanis = "Önemli değil, yine beklerim!"
        yanit = f"{prefix + ' ' if prefix else ''}Bitti! {d}/{t} doğru. {kapanis}"
        # yogunluk=0.85: ORTA-OYUN geri bildirimiyle AYNI. Son sorunun geri bildirim
        # oneki (tezahurat + "Cevap: X.") bu payload'a eklenir; orta oyun 0.85 kullanip
        # bu parcalari 0.85'te on-uretttiginden, oyun-sonunu da 0.85'te tutmak onbellek
        # ISABETINI saglar (0.9 olsaydi onek/cevap parcalari edge'e duserdi). Batch
        # (gen_batch_elevenlabs) quiz_end birimi de 0.85 uretir (yoksa Bitti/kapanis kacar).
        return self._quiz_payload(
            "quiz_end", turn=None, jest_id=jest, yanit=yanit, yogunluk=0.85,
            user_display=user_display,
            quiz_progress=f"Bitti · {d}/{t} doğru", timer=None, ended=True,
            buttons=self._quiz_end_buttons(),
            hint="«Tekrar» ya da «Menü» de")

    # ——— STT bias ipuclari ————————————————————————————————————
    # Menu secenekleri icin Whisper'a verilecek dogal soyleyisler.
    _MENU_STT = {
        "kelime": ("kelime türetme",),
        "eszit": ("eş anlam", "zıt anlam"),
        "atasozu": ("atasözü",),
        "dogruyanlis": ("doğru", "yanlış"),
    }

    def stt_hints(self) -> list:
        """O anki fazda mikrofondan DUYULMASI beklenen kelimeler (Turkce harfli).

        web_server /api/transcribe bunlari whisper initial_prompt'a ekler: olasi
        cevaplar dosyadan onceden bilindigi icin Whisper dogru yazima/kelimeye
        cekilir (serbest LLM duzeltmesi DEGIL, yalnizca cozumleme bias'i).
        Kelime Turetme oyun fazi serbest sozcuk bekler -> ipucu verilmez."""
        if self.phase == "menu":
            out = []
            for b in self._menu_buttons():
                out.extend(self._MENU_STT.get(b["key"], ()))
            return out
        if self.phase == "quiz":
            if self.quiz_turn == "hazir":
                # "menü" BILEREK yok: bias STT'yi menuye cekip oyunu bozuyordu
                # (sesli menu donusu zaten kapali; bkz. _handle_quiz_ready).
                return ["başla", "hazırım"]
            if self.quiz_turn == "soru" and self.quiz_current:
                return list(self.quiz_current.get("hints") or [])
            if self.quiz_turn is None:   # yarisma bitti: tekrar/menu bekleniyor
                return ["tekrar", "menü", "çıkış"]
        if self.phase == "kelime" and self.word_turn == "hazir":
            return ["başla", "hazırım", "menü"]
        return []

    # ——— Durum ————————————————————————————————————————————
    def status(self) -> dict:
        return {
            "phase": self.phase,
            "turn_id": self.turn_id,   # istemci fazi kaybederse jetonu buradan tazeler
            "word_turn": self.word_turn,
            "word_score": dict(self.word_score),
            "word_required_letter": self.word_required_letter,
            "word_ai_count": self.word_ai_count,
            "quiz_provider": self.quiz_provider,
            "quiz_turn": self.quiz_turn,
            "quiz_score": dict(self.quiz_score),
        }
