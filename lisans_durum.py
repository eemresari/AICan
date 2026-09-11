"""Aktivasyon dosyasi: makine bagi, sure sayimi, saat bekcisi.

%LOCALAPPDATA%/Aican/aktivasyon.dat = {"govde": <json>, "hmac": <hex>}

HMAC ANAHTARI BIRINCIL BILESENDEN TURETILIR (PBKDF2). Uc bilesenin hepsinden
turetilseydi bir bilesen degisince dosya cozulemez ve 3'ten 2'si esigi
anlamsiz kalirdi. Bedeli acikca kabul edildi: BIRINCIL bilesen (anakart)
degisirse yeniden aktivasyon gerekir.

ICERIK ANAHTARI BURADA SAKLANMAZ: her acilista `lisans` alaninin imzasi
dogrulanip yukunden cikarilir. Tek dogrulama yolu, tek sir kaynagi.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional

import parmak_izi
# orchestrator/paths.py — run_web.py ve pytest.ini orchestrator/'i sys.path'e
# koyar; web_server ile AYNI modul nesnesi olsun diye duz `import paths`.
import paths

DOSYA_ADI = "aktivasyon.dat"

# Saat dilimi ve NTP duzeltmeleri birkac saatlik geri sicrama yapabilir;
# musteriyi bunun icin kilitlemek kabul edilemez.
HOSGORU_SN = 86400


def _hmac_anahtari(izi: dict) -> bytes:
    """Birincil bilesenden turetilen HMAC anahtari."""
    ad, ozet = parmak_izi.birincil(izi)
    return hashlib.pbkdf2_hmac("sha256", f"{ad}:{ozet}".encode("ascii"),
                               b"aican-aktivasyon-v1", 100_000)


def _imzala(govde: str, izi: dict) -> str:
    return hmac.new(_hmac_anahtari(izi), govde.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def yaz(lisans_metni: str, izi: dict, simdi: Optional[float] = None) -> None:
    simdi = time.time() if simdi is None else simdi
    govde = json.dumps({
        "lisans": lisans_metni,
        "parmak_izi": izi,
        "ilk_aktivasyon_ts": simdi,
        "en_buyuk_gorulen_ts": simdi,
    }, separators=(",", ":"), sort_keys=True)
    hedef = Path(paths.activation_path())
    # Lisans kapisi ensure_seeded'dan ONCE calisir; veri koku henuz yok olabilir.
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(
        json.dumps({"govde": govde, "hmac": _imzala(govde, izi)}),
        encoding="utf-8")


def oku() -> Optional[dict]:
    """Aktivasyonu oku. HMAC tutmazsa None — sessiz kabul YOK."""
    yol = Path(paths.activation_path())
    if not yol.exists():
        return None
    try:
        sarmal = json.loads(yol.read_text(encoding="utf-8"))
        govde = sarmal["govde"]
        kayit = json.loads(govde)
        beklenen = _imzala(govde, kayit["parmak_izi"])
    except Exception:      # noqa: BLE001 — bozuk dosya da "gecersiz"dir
        return None
    if not hmac.compare_digest(beklenen, sarmal.get("hmac", "")):
        return None
    return kayit


def bitis_ts(yuk: dict, ilk_aktivasyon_ts: float) -> Optional[float]:
    """Iki takvim sinirinin KUCUGU baglayicidir.

    gecerlilik_gun ilk aktivasyondan sayilir (havuzdaki anahtar rafta
    beklerken yanmasin). son_kullanim_ts mutlak tavandir (ayni lisansin baska
    makinede yeniden aktive edilerek sonsuza uzamasini engeller).
    """
    if yuk.get("tip") == "kalici":
        return None
    adaylar = []
    gun = yuk.get("gecerlilik_gun")
    if gun:
        adaylar.append(ilk_aktivasyon_ts + gun * 86400)
    tavan = yuk.get("son_kullanim_ts")
    if tavan:
        adaylar.append(float(tavan))
    return min(adaylar) if adaylar else None


def saat_geri_mi(kayit: dict, simdi: Optional[float] = None) -> bool:
    simdi = time.time() if simdi is None else simdi
    return simdi < kayit.get("en_buyuk_gorulen_ts", 0) - HOSGORU_SN


def saati_ilerlet(kayit: dict, simdi: Optional[float] = None) -> None:
    """Gorulen en buyuk zamani guncelle. ilk_aktivasyon_ts KORUNUR."""
    simdi = time.time() if simdi is None else simdi
    if simdi <= kayit.get("en_buyuk_gorulen_ts", 0):
        return
    kayit["en_buyuk_gorulen_ts"] = simdi
    govde = json.dumps(kayit, separators=(",", ":"), sort_keys=True)
    Path(paths.activation_path()).write_text(
        json.dumps({"govde": govde,
                    "hmac": _imzala(govde, kayit["parmak_izi"])}),
        encoding="utf-8")
