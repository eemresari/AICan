"""Lisans kapisi: karar yordami + mini pencere.

PAKETIN DISINDA OLMAK ZORUNDA: web.pak sifreliyse sergi arayuzu (web/) de
onun icindedir; "lisans gir" ekrani lisans olmadan acilamaz. Bu yuzden ekran
ayri bir HTML dosyasidir (lisans_web/index.html), EXE'nin yanina HAM girer ve
webview.create_window(html=...) ile acilir — Flask sunucusu HIC baslatilmaz.

HER HATA KENDI MESAJINI VERIR: "gecersiz anahtar" deyip suresi dolmus bir
musteriyi destege yollamak kabul edilemez.

SprayTarih kopyasi; yalniz urun adi ve `paths` import'u farkli (orchestrator/
sys.path'tedir, bkz. pytest.ini / run_web.py).
"""

from __future__ import annotations

import time
from typing import Optional

import lisans
import lisans_durum
import parmak_izi
import paths

DURUMLAR = {
    "yok": "Bu bilgisayarda kayitli bir anahtar yok. "
           "Lisans dosyanizi secin ya da anahtar metnini yapistirin.",
    "doldu": "Sureniz doldu. Devam etmek icin yeni bir anahtar girin.",
    "baska_makine": "Bu kurulum baska bir bilgisayara ait. "
                    "Bu makine icin yeni bir anahtar gerekiyor.",
    "saat": "Sistem saati geri alinmis gorunuyor. "
            "Saati duzeltip programi yeniden baslatin.",
    "gecersiz": "Bu anahtar gecerli degil.",
    "surum": "Bu anahtar programin eski bir surumu icin uretilmis.",
    "urun": "Bu anahtar Aican icin degil; baska bir oyunun anahtari.",
}


def durumu_belirle(kayit: Optional[dict], izi: dict,
                   simdi: Optional[float] = None) -> tuple:
    """Aktivasyonun durumu. Saf yordam — pencere acmaz, dosya yazmaz.

    Sira onemli: makine bagi sureden ONCE bakilir, cunku kopyalanmis bir
    kuruluma "sureniz doldu" demek yanlis yonlendirir.
    """
    simdi = time.time() if simdi is None else simdi
    if not kayit:
        return "yok", None
    if not parmak_izi.tutuyor_mu(kayit.get("parmak_izi", {}), izi):
        return "baska_makine", None
    if lisans_durum.saat_geri_mi(kayit, simdi):
        return "saat", None
    try:
        yuk = lisans.dogrula(kayit["lisans"], simdi=simdi)
    except lisans.UrunHatasi:
        return "urun", None
    except lisans.SurumHatasi:
        return "surum", None
    except lisans.SuresiGecmis:
        return "doldu", None
    except lisans.LisansHatasi:
        return "gecersiz", None
    bitis = lisans_durum.bitis_ts(yuk, kayit["ilk_aktivasyon_ts"])
    if bitis is not None and simdi > bitis:
        return "doldu", None
    return "gecerli", yuk


def aktive_et(metin: str, simdi: Optional[float] = None) -> dict:
    """Yeni bir anahtari dogrula ve bu makineye bagla.

    lisans.LisansHatasi ve parmak_izi.ParmakIziYok yukari cikar; cagiran
    taraf DURUMLAR'dan uygun mesaji secer.
    """
    simdi = time.time() if simdi is None else simdi
    yuk = lisans.dogrula(metin, simdi=simdi)
    izi = parmak_izi.al()
    lisans_durum.yaz(metin, izi, simdi)
    return yuk


def _sayfa() -> str:
    from pathlib import Path
    return (Path(paths.resource_root()) / "lisans_web" / "index.html").read_text(
        encoding="utf-8")


class Kapi:
    """pywebview js_api koprusu. Iki teslim yolu, tek dogrulama yolu."""

    def __init__(self):
        self.yuk = None
        self._pencere = None

    def pencereyi_bagla(self, pencere) -> None:
        self._pencere = pencere

    def dosya_sec(self) -> dict:
        import webview

        secim = self._pencere.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=("Lisans dosyasi (*.dat)", "Tum dosyalar (*.*)"))
        if not secim:
            return {"ok": False, "mesaj": ""}
        from pathlib import Path
        return self.metin_gonder(
            Path(secim[0]).read_text(encoding="utf-8", errors="replace"))

    def metin_gonder(self, metin: str) -> dict:
        try:
            self.yuk = aktive_et(metin)
        except lisans.UrunHatasi:
            return {"ok": False, "mesaj": DURUMLAR["urun"]}
        except lisans.SurumHatasi:
            return {"ok": False, "mesaj": DURUMLAR["surum"]}
        except lisans.SuresiGecmis:
            return {"ok": False, "mesaj": DURUMLAR["doldu"]}
        except lisans.LisansHatasi:
            return {"ok": False, "mesaj": DURUMLAR["gecersiz"]}
        except parmak_izi.ParmakIziYok as e:
            return {"ok": False, "mesaj": str(e)}
        except Exception as e:  # noqa: BLE001 — JS'in genel catch'i "gecersiz" der; sebep gorunsun
            return {"ok": False, "mesaj": f"Aktivasyon kaydedilemedi: {e}"}
        if self._pencere is not None:
            self._pencere.destroy()
        return {"ok": True, "mesaj": ""}


def ac(mesaj: str) -> Optional[dict]:
    """Lisans penceresini ac; aktivasyon basarili olduysa yuku don.

    FLASK SUNUCUSU BASLATILMAZ: o zaten sifreli paketi servis edecek ve bu
    noktada icerik anahtari elde yok.
    """
    import webview

    kapi = Kapi()
    sayfa = _sayfa().replace("{{MESAJ}}", mesaj)
    pencere = webview.create_window("Aican — Lisans", html=sayfa,
                                    js_api=kapi, width=560, height=440,
                                    resizable=False)
    kapi.pencereyi_bagla(pencere)
    webview.start()
    return kapi.yuk
