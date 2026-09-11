"""Makine parmak izi — lisansi kuruldugu bilgisayara baglar.

NE ISE YARAR: kurulum klasorunu (veri/aktivasyon.dat dahil) baska bir makineye
kopyalamak ise yaramaz. Lisans DOSYASININ yeniden aktive edilmesini engellemez
— cevrimdisi bir sistemde bunun caresi yoktur (spec bolum 3).

ESIK 3'TEN 2'SI: sergi PC'sinin ekran karti ya da ag karti degisince musteri
kilitlenmemeli; makine komple degisince durmali.
"""

from __future__ import annotations

import hashlib
import subprocess
import uuid
from typing import Optional

BILESEN_ADLARI = ("anakart", "disk", "mac")
ESIK = 2
_ZAMAN_ASIMI = 8.0


class ParmakIziYok(RuntimeError):
    """Uc bilesenden en az ikisi okunamadi."""


def _ozetle(ham: str) -> str:
    """Ham degeri 16 haneli kararli bir ozete cevir.

    Bosluk ve buyuk/kucuk harf normalize edilir: WMI ciktisi makineden
    makineye bicim degistiriyor, ayni makine iki farkli izi uretmemeli.
    """
    duz = " ".join(str(ham).split()).upper()
    return hashlib.sha256(duz.encode("utf-8")).hexdigest()[:16]


def _powershell(ifade: str) -> Optional[str]:
    """Tek satirlik PowerShell ifadesini calistir; basarisizsa None."""
    try:
        sonuc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ifade],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_ZAMAN_ASIMI,
            # Konsolsuz EXE'de yeni konsol penceresi acilmasin.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:      # noqa: BLE001 — powershell yok, zaman asimi, izin...
        return None
    cikti = (sonuc.stdout or "").strip()
    return cikti or None


def _bilesenleri_topla() -> dict:
    """Ham bilesenler. TESTLER BUNU EZER — gercek cagri yapilmaz."""
    return {
        "anakart": _powershell(
            "(Get-CimInstance Win32_ComputerSystemProduct).UUID"),
        "disk": _powershell(
            "(Get-CimInstance Win32_DiskDrive | "
            "Sort-Object DeviceID | Select-Object -First 1).SerialNumber"),
        "mac": format(uuid.getnode(), "012x"),
    }


def al() -> dict:
    """Simdiki makinenin parmak izi: ad -> ozet ya da None."""
    ham = _bilesenleri_topla()
    izi = {ad: (_ozetle(ham[ad]) if ham.get(ad) else None)
           for ad in BILESEN_ADLARI}
    if sum(1 for v in izi.values() if v) < ESIK:
        raise ParmakIziYok(
            "Bu bilgisayarin kimligi okunamadi (en az iki bilesen gerekli).")
    return izi


def tutuyor_mu(kayitli: dict, simdiki: dict) -> bool:
    """Kayitli izle simdiki iz ESIK kadar bilesende ortusuyor mu?

    None esleme SAYILMAZ: iki okunamayan bilesen 'esitim' deyip yanlis
    kurulumu acmamali.
    """
    eslesen = sum(1 for ad in BILESEN_ADLARI
                  if kayitli.get(ad) and kayitli.get(ad) == simdiki.get(ad))
    return eslesen >= ESIK


def birincil(izi: dict) -> tuple:
    """HMAC anahtarinin turetilecegi TEK kararli bilesen.

    NEDEN TEK: HMAC anahtari uc bilesenin hepsinden turetilseydi, bir bilesen
    degisince dosya cozulemez ve 3'ten 2'si esigi anlamsiz kalirdi. Sira
    kararliliga gore: anakart > disk > mac.
    """
    for ad in BILESEN_ADLARI:
        if izi.get(ad):
            return ad, izi[ad]
    raise ParmakIziYok("Parmak izinde tek bir okunabilir bilesen bile yok.")
