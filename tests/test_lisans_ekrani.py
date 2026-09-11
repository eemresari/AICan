"""Lisans kapisinin KARAR YORDAMI (pencere acmadan).

Her hata durumu KENDI mesajini uretmeli: "gecersiz anahtar" deyip suresi
dolmus bir musteriyi destege yollamak kabul edilemez.

SprayTarih tests/test_lisans_ekrani.py uyarlamasi (urun adi Aican).
"""

from __future__ import annotations

import base64
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

import lisans
import lisans_bicim
import lisans_ekrani

IZ = {"anakart": "a" * 16, "disk": "b" * 16, "mac": "c" * 16}


@pytest.fixture
def imzali(monkeypatch):
    ozel = ed25519.Ed25519PrivateKey.generate()
    pem = ozel.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    acik = ozel.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(lisans, "ACIK_ANAHTAR_HEX", acik)

    def uret(**ezme):
        yuk = dict(surum=1, urun=lisans.URUN, tip="demo", kurum="X",
                   anahtar_no=1, paket_no=lisans.PAKET_NO, gecerlilik_gun=7,
                   son_kullanim_ts=int(time.time()) + 86400 * 180,
                   icerik_anahtari=base64.b64encode(b"k" * 32).decode())
        yuk.update(ezme)
        return lisans_bicim.uret(yuk, pem)
    return uret


def _kayit(metin, ilk, en_buyuk=None):
    return {"lisans": metin, "parmak_izi": IZ, "ilk_aktivasyon_ts": ilk,
            "en_buyuk_gorulen_ts": en_buyuk if en_buyuk else ilk}


def test_aktivasyon_yoksa_YOK(imzali):
    durum, yuk = lisans_ekrani.durumu_belirle(None, IZ, time.time())
    assert durum == "yok" and yuk is None


def test_gecerli_aktivasyon(imzali):
    simdi = time.time()
    durum, yuk = lisans_ekrani.durumu_belirle(
        _kayit(imzali(), simdi - 86400), IZ, simdi)
    assert durum == "gecerli"
    assert base64.b64decode(yuk["icerik_anahtari"]) == b"k" * 32


def test_sure_dolunca_DOLDU(imzali):
    simdi = time.time()
    durum, _ = lisans_ekrani.durumu_belirle(
        _kayit(imzali(gecerlilik_gun=1), simdi - 86400 * 3), IZ, simdi)
    assert durum == "doldu"


def test_baska_makinede_BASKA_MAKINE(imzali):
    simdi = time.time()
    baska = {"anakart": "z" * 16, "disk": "y" * 16, "mac": "c" * 16}
    durum, _ = lisans_ekrani.durumu_belirle(
        _kayit(imzali(), simdi - 60), baska, simdi)
    assert durum == "baska_makine"


def test_saat_geri_alinirsa_SAAT(imzali):
    simdi = time.time()
    kayit = _kayit(imzali(), simdi - 86400, en_buyuk=simdi)
    durum, _ = lisans_ekrani.durumu_belirle(kayit, IZ, simdi - 86400 * 5)
    assert durum == "saat"


def test_BASKA_OYUNUN_anahtari_URUN(imzali):
    """SprayTarih anahtari Aican'a girilirse net mesaj almali."""
    simdi = time.time()
    durum, _ = lisans_ekrani.durumu_belirle(
        _kayit(imzali(urun="spraytarih"), simdi - 60), IZ, simdi)
    assert durum == "urun"


def test_KALICI_lisans_dolmaz(imzali):
    simdi = time.time()
    metin = imzali(tip="kalici", gecerlilik_gun=None, son_kullanim_ts=None)
    durum, _ = lisans_ekrani.durumu_belirle(
        _kayit(metin, simdi - 86400 * 3650), IZ, simdi)
    assert durum == "gecerli"


def test_makine_bagi_SUREDEN_ONCE_bakilir(imzali):
    """Kopyalanmis bir kuruluma 'sureniz doldu' demek yanlis yonlendirir."""
    simdi = time.time()
    baska = {"anakart": "z" * 16, "disk": "y" * 16, "mac": "x" * 16}
    durum, _ = lisans_ekrani.durumu_belirle(
        _kayit(imzali(gecerlilik_gun=1), simdi - 86400 * 3), baska, simdi)
    assert durum == "baska_makine"


def test_HER_DURUMUN_kendi_mesaji():
    assert set(lisans_ekrani.DURUMLAR) == {
        "yok", "doldu", "baska_makine", "saat", "gecersiz", "surum", "urun"}
    mesajlar = list(lisans_ekrani.DURUMLAR.values())
    assert len(set(mesajlar)) == len(mesajlar), "iki durum ayni mesaji veriyor"
    assert all(m.strip() for m in mesajlar)


def test_sayfa_MESAJ_yer_tutucusu_tasir():
    """ac() mesaji buraya yaziyor; yer tutucu kaybolursa kullanici neden
    lisans istendigini goremez."""
    assert "{{MESAJ}}" in lisans_ekrani._sayfa()


def test_sayfa_ve_mesajlar_Aican_diyor():
    """SprayTarih kopyasi; urun adi eksik kalirsa musteri baska oyunun
    penceresini gordugunu sanir."""
    sayfa = lisans_ekrani._sayfa()
    assert "SprayTarih" not in sayfa and "KimyaLab" not in sayfa
    assert "Aican" in sayfa
    assert "Aican" in lisans_ekrani.DURUMLAR["urun"]
    tum = " ".join(lisans_ekrani.DURUMLAR.values())
    assert "SprayTarih" not in tum and "KimyaLab" not in tum


def test_sayfa_pakete_degil_diske_bakar(monkeypatch, tmp_path):
    """Lisans ekrani web.pak'in DISINDA: paths.PAKET dolu olsa da
    resource_root()/lisans_web/index.html diskten okunur (anahtar henuz yok)."""
    import paths
    (tmp_path / "lisans_web").mkdir()
    (tmp_path / "lisans_web" / "index.html").write_text("DISK {{MESAJ}}", encoding="utf-8")
    monkeypatch.setattr(paths, "resource_root", lambda: str(tmp_path))
    monkeypatch.setattr(paths, "PAKET", {"web/app.js": b"x"})
    assert lisans_ekrani._sayfa() == "DISK {{MESAJ}}"


def test_beklenmeyen_hata_SAHTE_gecersiz_demez(monkeypatch):
    """Dosya yazilamadi gibi bir hata 'anahtar gecerli degil' diye gosterilirse
    kullanici anahtari suclar (yasandi: veri klasoru yokken). Gercek sebep
    mesajda gorunmeli."""
    def patlat(metin):
        raise OSError("disk yazilamadi")
    monkeypatch.setattr(lisans_ekrani, "aktive_et", patlat)
    kopru = lisans_ekrani.Kapi()
    sonuc = kopru.metin_gonder("LDN1.x.y")
    assert sonuc["ok"] is False
    assert "disk yazilamadi" in sonuc["mesaj"]
    assert "gecerli degil" not in sonuc["mesaj"]


def test_aktive_et_dosyayi_veri_kokune_yazar(imzali, monkeypatch, tmp_path):
    """Aktivasyon paths.activation_path()'e gider (AICAN_DATA_ROOT ile tmp);
    ardindan durumu_belirle 'gecerli' der ve yuk icerik anahtarini tasir."""
    import lisans_durum
    import parmak_izi
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(parmak_izi, "al", lambda: IZ)
    yuk = lisans_ekrani.aktive_et(imzali())
    assert yuk["tip"] == "demo"
    assert (tmp_path / "aktivasyon.dat").is_file()
    durum, yuk2 = lisans_ekrani.durumu_belirle(lisans_durum.oku(), IZ)
    assert durum == "gecerli" and yuk2["icerik_anahtari"] == yuk["icerik_anahtari"]
