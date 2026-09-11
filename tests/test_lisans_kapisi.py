"""Acilis kapisi: lisans, ICERIK PAKETI ve donanim thread'lerinden once.

create_app icinde mikrofon/GPU (Whisper), Ollama warmup ve TTS thread'leri
basliyor; Flask de sifreli paketi servis ediyor. Ikisi de lisans dogrulanmadan
olmamali. Sira burada kilitlenir — bir gun "once sunucu kalksin, sonra bakariz"
diye yer degistirirse lisanssiz sergi acilir.

Kaynaktan calistirmada (paths.FROZEN False) kapi YOKTUR: gelistirme dongusu
bozulmamali; web/ ve ai/ zaten diskten okunuyor.
"""

from __future__ import annotations

import base64
import inspect
import re

import pytest

import lisans
import lisans_durum
import lisans_ekrani
import parmak_izi
import paths
import web_paket
import web_server

IZ = {"anakart": "a" * 16, "disk": "b" * 16, "mac": "c" * 16}


# --------------------------------------------------------------------------- #
# Sira kilidi
# --------------------------------------------------------------------------- #

def test_kapi_create_app_ve_app_run_dan_ONCE():
    kaynak = inspect.getsource(web_server.main)
    port = kaynak.index("_port_in_use(")
    kapi = kaynak.index("lisans_kapisi(")
    paket = kaynak.index("_paketi_yukle(")
    app = kaynak.index("create_app(")
    run = kaynak.index("app.run(")
    assert port < kapi < paket < app < run


def test_port_doluysa_kapiya_HIC_gelinmez():
    """Ikinci cift tik: sergi zaten acik. Lisans penceresi cikmamali; port
    dalinda return var ve kapi cagrisi ondan SONRA."""
    kaynak = inspect.getsource(web_server.main)
    port_dali = kaynak.index("_port_in_use(")
    donus = kaynak.index("return", port_dali)
    assert donus < kaynak.index("lisans_kapisi(")


def test_ensure_seeded_config_okumadan_ONCE():
    """Dondurulmus EXE'de config.json veri kokunde durur ve ilk acilista
    yoktur; port numarasi ondan okunur. Tohumlama ilk adim olmali."""
    kaynak = inspect.getsource(web_server.main)
    assert kaynak.index("ensure_seeded(") < kaynak.index("load_config(")


def test_demo_bayragi_yukten_gelir():
    kaynak = inspect.getsource(web_server.main)
    assert re.search(r'create_app\(config,\s*paket,\s*demo=\(yuk\.get\("tip"\)\s*==\s*"demo"\)\)',
                     kaynak)


# --------------------------------------------------------------------------- #
# lisans_kapisi — kaynaktan ve donmus
# --------------------------------------------------------------------------- #

def test_kaynaktan_calistirmada_kapi_YOK(monkeypatch):
    monkeypatch.setattr(parmak_izi, "al",
                        lambda: pytest.fail("kaynaktan calisirken parmak izi okunmamali"))
    monkeypatch.setattr(lisans_ekrani, "ac",
                        lambda m: pytest.fail("kaynaktan calisirken pencere acilmamali"))
    monkeypatch.setattr(web_server, "FILIGRAN", "eski")
    anahtar, yuk = web_server.lisans_kapisi(False)
    assert anahtar is None
    assert yuk["tip"] == "kalici"          # demo kilidi devreye girmez
    assert web_server.FILIGRAN == ""


def test_kaynaktan_paket_YUKLENMEZ(monkeypatch):
    """web.pak kaynakta aranmaz bile (dosya yok, olsa da acilmaz)."""
    monkeypatch.setattr(paths, "FROZEN", False)
    monkeypatch.setattr(web_paket, "paket_no_oku",
                        lambda v: pytest.fail("kaynakta web.pak okunmamali"))
    assert web_server._paketi_yukle(None) is None
    assert web_server._paketi_yukle(b"k" * 32) is None


def test_gecerli_aktivasyon_ANAHTARI_doner(monkeypatch):
    anahtar = b"k" * 32
    yuk = {"tip": "kalici", "icerik_anahtari": base64.b64encode(anahtar).decode()}
    monkeypatch.setattr(parmak_izi, "al", lambda: IZ)
    monkeypatch.setattr(lisans_durum, "oku", lambda: {"lisans": "x", "parmak_izi": IZ})
    monkeypatch.setattr(lisans_durum, "saati_ilerlet", lambda k: None)
    monkeypatch.setattr(lisans_ekrani, "durumu_belirle", lambda k, i: ("gecerli", yuk))
    monkeypatch.setattr(lisans_ekrani, "ac",
                        lambda m: pytest.fail("gecerli lisansta pencere acilmamali"))
    assert web_server.lisans_kapisi(True) == (anahtar, yuk)
    assert web_server.FILIGRAN == ""       # kalici lisansta filigran yok


def test_pencere_kapatilirsa_UYGULAMA_DURUR(monkeypatch):
    """'anahtar girmedim ama sergi acildi' korunmak istenen seyin ta kendisi."""
    monkeypatch.setattr(parmak_izi, "al", lambda: IZ)
    monkeypatch.setattr(lisans_durum, "oku", lambda: None)
    monkeypatch.setattr(lisans_ekrani, "durumu_belirle", lambda k, i: ("yok", None))
    monkeypatch.setattr(lisans_ekrani, "ac", lambda m: None)
    with pytest.raises(web_server.LisansReddedildi):
        web_server.lisans_kapisi(True)


def test_pencereden_gecince_anahtar_yuk_ve_filigran(monkeypatch):
    anahtar = b"z" * 32
    yuk = {"tip": "demo", "kurum": "Konya Bilim Merkezi", "anahtar_no": 7,
           "son_kullanim_ts": 1_800_000_000,
           "icerik_anahtari": base64.b64encode(anahtar).decode()}
    acilan = []
    monkeypatch.setattr(parmak_izi, "al", lambda: IZ)
    monkeypatch.setattr(lisans_durum, "oku", lambda: None)
    monkeypatch.setattr(lisans_durum, "saati_ilerlet", lambda k: None)
    monkeypatch.setattr(lisans_ekrani, "durumu_belirle", lambda k, i: ("yok", None))
    monkeypatch.setattr(lisans_ekrani, "ac", lambda m: acilan.append(m) or yuk)
    donen_anahtar, donen_yuk = web_server.lisans_kapisi(True)
    assert donen_anahtar == anahtar
    assert donen_yuk["tip"] == "demo"
    assert acilan == [lisans_ekrani.DURUMLAR["yok"]]
    assert "Konya Bilim Merkezi" in web_server.FILIGRAN
    assert "#7" in web_server.FILIGRAN


def test_parmak_izi_okunamazsa_anlamli_hata(monkeypatch):
    def patlat():
        raise parmak_izi.ParmakIziYok("kimlik okunamadi")
    monkeypatch.setattr(parmak_izi, "al", patlat)
    with pytest.raises(web_server.LisansReddedildi, match="kimlik"):
        web_server.lisans_kapisi(True)


def test_LisansReddedildi_SystemExit_turevi():
    """main() SystemExit'i yeniden firlatir, genel except'e dusmez; mesaj
    konsolsuz EXE'de _fatal ile gosterilir."""
    assert issubclass(web_server.LisansReddedildi, SystemExit)


# --------------------------------------------------------------------------- #
# _paketi_yukle — donmus
# --------------------------------------------------------------------------- #

@pytest.fixture
def donmus_kok(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(paths, "resource_root", lambda: str(tmp_path))
    return tmp_path


def test_paket_dogru_anahtarla_bellege(donmus_kok):
    anahtar = b"k" * 32
    (donmus_kok / "web.pak").write_bytes(web_paket.sozlugu_paketle(
        {"web/app.js": b"// x", "ai/gestures.json": b"[]"}, anahtar, lisans.PAKET_NO))
    d = web_server._paketi_yukle(anahtar)
    assert d == {"web/app.js": b"// x", "ai/gestures.json": b"[]"}


def test_paket_yoksa_LisansReddedildi(donmus_kok):
    with pytest.raises(web_server.LisansReddedildi, match="cozulemedi"):
        web_server._paketi_yukle(b"k" * 32)


def test_paket_yanlis_anahtar_LisansReddedildi(donmus_kok):
    (donmus_kok / "web.pak").write_bytes(web_paket.sozlugu_paketle(
        {"web/app.js": b"// x"}, b"k" * 32, lisans.PAKET_NO))
    with pytest.raises(web_server.LisansReddedildi, match="cozulemedi"):
        web_server._paketi_yukle(b"z" * 32)


def test_paket_no_uyusmazsa_SURUM_mesaji(donmus_kok):
    """EXE ile web.pak ayri surumden: 'gecersiz anahtar' degil, kurulum
    uyusmazligi soylenir (dogru anahtarla bile cozulmeye kalkilmaz)."""
    anahtar = b"k" * 32
    (donmus_kok / "web.pak").write_bytes(web_paket.sozlugu_paketle(
        {"web/app.js": b"// x"}, anahtar, lisans.PAKET_NO + 1))
    with pytest.raises(web_server.LisansReddedildi, match="surumu uyusmuyor"):
        web_server._paketi_yukle(anahtar)


# --------------------------------------------------------------------------- #
# Filigran metni
# --------------------------------------------------------------------------- #

def test_filigran_kalici_lisansta_BOS():
    assert web_server.filigran_metni({"tip": "kalici", "kurum": "X", "anahtar_no": 1}) == ""
    assert web_server.filigran_metni(None) == ""


def test_filigran_demoda_kurum_tarih_no():
    metin = web_server.filigran_metni({"tip": "demo", "kurum": "Kurum A", "anahtar_no": 12,
                                       "son_kullanim_ts": 1_800_000_000})
    assert metin.startswith("Kurum A")
    assert re.search(r"\d{2}\.\d{2}\.\d{4}", metin)
    assert metin.endswith("#12")


def test_filigran_kurumsuz_demo():
    assert web_server.filigran_metni({"tip": "demo", "anahtar_no": 3}) == "Demo — #3"


# --------------------------------------------------------------------------- #
# Frontend tarafi — statik kilit
# --------------------------------------------------------------------------- #

def test_frontend_filigrani_okur_ve_kilidi_taniyor():
    from pathlib import Path
    kok = Path(web_server.__file__).resolve().parent.parent / "web"
    app_js = (kok / "app.js").read_text(encoding="utf-8")
    assert "/api/filigran" in app_js
    assert "kilitli" in app_js
    control_js = (kok / "control.js").read_text(encoding="utf-8")
    assert "kilitli" in control_js
    assert "testModeLocked" in control_js
