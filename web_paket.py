"""web/ + ai/ agacini tek sifreli pakete koyar ve BELLEKTE cozer.

NEDEN: Nuitka Python tarafini makine koduna cevirir, ama Aican'in asil icerigi
Python'da degil — sergi on yuzu web/*.js|html, oyun veri tablolari ai/*.json
ve sistem promptu ai/system_prompt.txt. Ham konurlarsa standalone EXE'nin
yaninda okunabilir kaynak olarak dururlar.

Pakete GIREN: `web/` (5 dosya) + `ai/` (json + system_prompt.txt vb.).
GIRMEYEN:  `assets/` (16 MB emoji PNG — gorsel, kaynak degil; diskten servis),
           `ai/Modelfile` (build_model.py uretir, .gitignore'da).

Bicim:  AIPAK1\\n | paket_no (4 bayt BE) | 12 bayt nonce | AES-256-GCM(zip)

Sihir URUNE OZEL (SprayTarih: STPAK1): baska urunun web.pak'i yanlislikla
yuklenirse "gecersiz anahtar" degil, "bu bir Aican paketi degil" denir.

paket_no BASLIKTA ACIK DURUR: EXE, lisansi cozmeden once "bu anahtar bu surum
icin mi" diyebilmeli; yoksa surum uyusmazliginda kullaniciya "gecersiz
anahtar" gibi yanlis bir mesaj gosterirdi.

Zip ARA BIR ADIM: dosya adlarini ve iceriklerini tek blokta tutmanin en kisa
yolu. Sifreleme zip'in USTUNDE oldugu icin paketin icinde ne dosya adi ne de
icerik duz metin gorunur.

ANAHTAR BU MODULDE YOK: cagiran taraf onu lisansin imzali yukunden getirir.
Boylece "anahtarsiz oyun acilmaz" yamalanabilir bir kontrol degil,
kriptografik bir gercektir — yamalanacak dallanma yoktur.

Cozulen sozluk `paths.PAKET`'e konur; anahtarlar depo kokune gore POSIX
("web/app.js", "ai/atasozu.json") — `paths.kaynak_oku` ve web_server'in
bellekten servis yolu ayni anahtarlari kullanir.
"""

from __future__ import annotations

import io
import secrets
import zipfile
from pathlib import Path
from typing import Optional

BASLIK = b"AIPAK1\n"
PAKET_NO_UZUNLUK = 4
NONCE_UZUNLUK = 12
_ON_EK = len(BASLIK) + PAKET_NO_UZUNLUK

# Pakete giren dizinler (depo kokune gore) ve dislanan anahtarlar.
PAKET_DIZINLERI = ("web", "ai")
HARIC = frozenset({"ai/Modelfile"})


def _dizini_topla(dizin: Path, on_ek: str, hedef: dict) -> None:
    for p in sorted(Path(dizin).rglob("*")):
        if not p.is_file():
            continue
        anahtar = f"{on_ek}/{p.relative_to(dizin).as_posix()}"
        if anahtar in HARIC:
            continue
        hedef[anahtar] = p.read_bytes()


def topla(kok: Path, web_kok: Optional[Path] = None) -> dict:
    """kok/web ve kok/ai altindaki dosyalari {"web/app.js": b"..."} sozlugune al.

    `web_kok` verilirse web/ icerigi ORADAN alinir (build.py obfuscate edilmis
    web-hazir/ dizinini verir) ama anahtar yine "web/..." kalir; ai/ her zaman
    kok/ai'dan gelir. assets/ ve kokteki dosyalar hicbir zaman girmez.
    """
    kok = Path(kok)
    dosyalar: dict = {}
    for ad in PAKET_DIZINLERI:
        kaynak = Path(web_kok) if (ad == "web" and web_kok is not None) else kok / ad
        _dizini_topla(kaynak, ad, dosyalar)
    return dosyalar


def sozlugu_paketle(dosyalar: dict, anahtar: bytes, paket_no: int) -> bytes:
    """Hazir sozlugu tek sifreli bloga koy (topla() ciktisi ya da test verisi)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for ad in sorted(dosyalar):
            z.writestr(ad, dosyalar[ad])
    nonce = secrets.token_bytes(NONCE_UZUNLUK)
    govde = AESGCM(anahtar).encrypt(nonce, tampon.getvalue(), None)
    return (BASLIK + paket_no.to_bytes(PAKET_NO_UZUNLUK, "big")
            + nonce + govde)


def paketle(kok: Path, anahtar: bytes, paket_no: int,
            web_kok: Optional[Path] = None) -> bytes:
    """kok/web + kok/ai'yi tek sifreli bloga koy (bkz. topla)."""
    return sozlugu_paketle(topla(kok, web_kok=web_kok), anahtar, paket_no)


def paket_no_oku(veri: bytes) -> int:
    """Sifreyi COZMEDEN paket surumunu oku."""
    if not veri.startswith(BASLIK) or len(veri) < _ON_EK:
        raise ValueError("Bu bir Aican icerik paketi degil (baslik uymuyor).")
    return int.from_bytes(veri[len(BASLIK):_ON_EK], "big")


def coz(veri: bytes, anahtar: bytes) -> dict:
    """Paketi BELLEKTE coz; paths.PAKET'e konacak {anahtar: bytes} doner.
    Diske hicbir sey yazilmaz."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    paket_no_oku(veri)      # baslik dogrulamasi
    kalan = veri[_ON_EK:]
    nonce, gizli = kalan[:NONCE_UZUNLUK], kalan[NONCE_UZUNLUK:]
    duz = AESGCM(anahtar).decrypt(nonce, gizli, None)
    with zipfile.ZipFile(io.BytesIO(duz)) as z:
        return {ad: z.read(ad) for ad in z.namelist()}
