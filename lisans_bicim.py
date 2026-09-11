"""Imzali lisans bicimi: uretim (merkez) ve dogrulama (oyun).

BICIM (tek satir ASCII — dosya ve yapistirma AYNI sey):
    LDN1.<base64url(yuk_json)>.<base64url(ed25519_imza)>
Imza "LDN1.<base64url(yuk_json)>" baytlari uzerinden hesaplanir.

OYUNDA HIC KEY YOKTUR, yalniz ACIK anahtar durur: imzayi dogrulayabilir,
URETEMEZ. Ozel anahtar sadece Lisans Merkezi'nin calistigi makinededir.
EXE'yi parcalayan biri tek bir key cikaramaz, uretemez.

BU DOSYA URUNE OZEL SABIT TASIMAZ. Acik anahtar, urun kodu ve paket no
dogrula()'ya PARAMETRE gelir. Sebep: dosya her urune BIREBIR kopyalanir;
icinde urune ozel bir sabit olsaydi kopyalar ayrisir ve dagitilmis keyler
dogrulanamaz hale gelirdi. Kopyalarin ayni kaldigini
tests/test_kopya_senkron.py kilitler.

ICERIK ANAHTARI YUKUN ICINDE acik durur ve bu bir kayip DEGILDIR: lisansa
sahip kisi zaten oyunu calistirabiliyor. Korunan sey, lisansi OLMAYAN kisinin
sifreli oyun paketini cozememesidir.
"""

from __future__ import annotations

import base64
import json
import time

BASLIK = "LDN1"


class LisansHatasi(Exception):
    """Lisans kabul edilemedi."""


class ImzaHatasi(LisansHatasi):
    """Imza tutmuyor ya da yuk kurcalanmis."""


class UrunHatasi(LisansHatasi):
    """Lisans baska bir urun icin uretilmis."""


class SurumHatasi(LisansHatasi):
    """Lisans baska bir paket surumu icin uretilmis."""


class SuresiGecmis(LisansHatasi):
    """Mutlak son kullanim tarihi gecmis."""


def _b64e(ham: bytes) -> str:
    return base64.urlsafe_b64encode(ham).decode("ascii").rstrip("=")


def _b64d(metin: str) -> bytes:
    return base64.urlsafe_b64decode(metin + "=" * (-len(metin) % 4))


def _govde(yuk: dict) -> str:
    duz = json.dumps(yuk, separators=(",", ":"), ensure_ascii=False,
                     sort_keys=True)
    return f"{BASLIK}.{_b64e(duz.encode('utf-8'))}"


def uret(yuk: dict, ozel_anahtar_pem: bytes) -> str:
    """Yuku imzala. YALNIZ Lisans Merkezi'nde cagrilir."""
    from cryptography.hazmat.primitives import serialization

    ozel = serialization.load_pem_private_key(ozel_anahtar_pem, password=None)
    govde = _govde(yuk)
    imza = ozel.sign(govde.encode("ascii"))
    return f"{govde}.{_b64e(imza)}"


def dogrula(metin: str, acik_anahtar_hex: str, urun: str, paket_no: int,
            simdi: float = None) -> dict:
    """Lisans metnini dogrula ve yuku don.

    Bosluk/satir sonu temizlenir: e-postadan yapistirilan blok bunlari tasir
    ve kullaniciyi 'gecersiz anahtar' diye geri cevirmek kabul edilemez.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    simdi = time.time() if simdi is None else simdi

    temiz = "".join(str(metin).split())
    parcalar = temiz.split(".")
    if len(parcalar) != 3 or parcalar[0] != BASLIK:
        raise LisansHatasi("Bu bir lisans anahtari degil.")

    govde = f"{parcalar[0]}.{parcalar[1]}"
    try:
        acik = ed25519.Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(acik_anahtar_hex))
        acik.verify(_b64d(parcalar[2]), govde.encode("ascii"))
    except (InvalidSignature, ValueError):
        raise ImzaHatasi("Bu anahtar gecerli degil.") from None

    try:
        yuk = json.loads(_b64d(parcalar[1]))
    except Exception:      # noqa: BLE001 — bozuk base64 / bozuk json
        raise ImzaHatasi("Bu anahtar gecerli degil.") from None

    # Urun kontrolu IMZADAN SONRA: yuke ancak imza tuttuktan sonra guvenilir.
    yuk_urun = yuk.get("urun")
    if yuk_urun != urun:
        raise UrunHatasi(
            f"Bu anahtar bu program icin degil ({yuk_urun} anahtari).")

    if yuk.get("paket_no") != paket_no:
        raise SurumHatasi(
            "Bu anahtar programin eski bir surumu icin uretilmis.")

    son = yuk.get("son_kullanim_ts")
    if son is not None and simdi > son:
        raise SuresiGecmis("Bu anahtarin kullanim suresi dolmus.")

    return yuk
