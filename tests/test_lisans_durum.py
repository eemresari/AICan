"""Aktivasyon dosyasi: makine bagi, sure sayimi, saat bekcisi.

HMAC ANAHTARI BIRINCIL BILESENDEN TURETILIR (parmak_izi.birincil): uc
bilesenin hepsinden turetilseydi, bir bilesen degisince dosya cozulemez ve
3'ten 2'si esigi anlamsiz kalirdi.

ICERIK ANAHTARI DOSYADA DURMAZ: her acilista lisans metninin imzasi
dogrulanip yukunden cikarilir. Tek dogrulama yolu, tek sir kaynagi.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

import lisans
import lisans_bicim
import lisans_durum
import paths

IZ = {"anakart": "a" * 16, "disk": "b" * 16, "mac": "c" * 16}


@pytest.fixture(autouse=True)
def gecici_veri(tmp_path, monkeypatch):
    """Testler gercek veri kokune (kaynaktan calisirken DEPO KOKU) yazmamali."""
    veri = tmp_path / "veri"
    veri.mkdir()
    monkeypatch.setenv("AICAN_DATA_ROOT", str(veri))


@pytest.fixture
def metin(monkeypatch):
    ozel = ed25519.Ed25519PrivateKey.generate()
    pem = ozel.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    acik = ozel.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(lisans, "ACIK_ANAHTAR_HEX", acik)
    yuk = dict(surum=1, urun=lisans.URUN, tip="demo", kurum="X", anahtar_no=1,
               paket_no=lisans.PAKET_NO, gecerlilik_gun=7,
               son_kullanim_ts=int(time.time()) + 86400 * 180,
               icerik_anahtari=base64.b64encode(b"k" * 32).decode())
    return lisans_bicim.uret(yuk, pem)


def test_yaz_oku_turu(metin):
    simdi = time.time()
    lisans_durum.yaz(metin, IZ, simdi)
    kayit = lisans_durum.oku()
    assert kayit["lisans"] == metin
    assert kayit["parmak_izi"] == IZ
    assert kayit["ilk_aktivasyon_ts"] == pytest.approx(simdi)


def test_ICERIK_ANAHTARI_dosyada_YOK(metin):
    """Sir tek yerde dursun: lisansin imzali yukunde."""
    lisans_durum.yaz(metin, IZ, time.time())
    ham = Path(paths.activation_path()).read_text("utf-8")
    assert "icerik_anahtari" not in ham


def test_hmac_kurcalama_reddedilir(metin):
    lisans_durum.yaz(metin, IZ, time.time())
    yol = Path(paths.activation_path())
    veri = json.loads(yol.read_text("utf-8"))
    veri["govde"] = veri["govde"][:-8] + "00000000"
    yol.write_text(json.dumps(veri), encoding="utf-8")
    assert lisans_durum.oku() is None


def test_baska_makinede_HMAC_TUTMAZ(metin, monkeypatch):
    """veri/ klasorunu ikinci bir makineye kopyalamak ise yaramamali."""
    lisans_durum.yaz(metin, IZ, time.time())
    monkeypatch.setattr(lisans_durum, "_hmac_anahtari",
                        lambda izi: b"baska-makine-anahtari")
    assert lisans_durum.oku() is None


def test_ilk_aktivasyon_korunur(metin):
    """Ikinci acilis sureyi SIFIRLAMAMALI."""
    ilk = time.time() - 86400 * 3
    lisans_durum.yaz(metin, IZ, ilk)
    kayit = lisans_durum.oku()
    lisans_durum.saati_ilerlet(kayit, time.time())
    assert lisans_durum.oku()["ilk_aktivasyon_ts"] == pytest.approx(ilk)


def test_saat_geri_alinirsa_reddedilir(metin):
    simdi = time.time()
    lisans_durum.yaz(metin, IZ, simdi)
    kayit = lisans_durum.oku()
    assert lisans_durum.saat_geri_mi(kayit, simdi - 86400 * 5)


def test_24_SAAT_HOSGORU_yanlis_alarm_vermez(metin):
    """Saat dilimi ve NTP duzeltmesi birkac saatlik geri sicrama yapabilir;
    musteriyi bunun icin kilitlemek kabul edilemez."""
    simdi = time.time()
    lisans_durum.yaz(metin, IZ, simdi)
    kayit = lisans_durum.oku()
    assert not lisans_durum.saat_geri_mi(kayit, simdi - 3600 * 5)


def test_KUCUK_olan_bitis_kazanir():
    """gecerlilik_gun ile son_kullanim_ts'in kucugu baglayicidir."""
    ilk = 1_000_000.0
    yuk = {"tip": "demo", "gecerlilik_gun": 30,
           "son_kullanim_ts": ilk + 86400 * 5}
    assert lisans_durum.bitis_ts(yuk, ilk) == ilk + 86400 * 5
    yuk2 = {"tip": "demo", "gecerlilik_gun": 3,
            "son_kullanim_ts": ilk + 86400 * 900}
    assert lisans_durum.bitis_ts(yuk2, ilk) == ilk + 86400 * 3


def test_kalici_lisansta_bitis_YOK():
    yuk = {"tip": "kalici", "gecerlilik_gun": None, "son_kullanim_ts": None}
    assert lisans_durum.bitis_ts(yuk, 1_000_000.0) is None


def test_aktivasyon_VERI_KOKUNDE_paketin_disinda(monkeypatch, tmp_path):
    """aktivasyon.dat EXE'nin yanina (salt okunur paket) degil, yazilabilir veri
    kokune gider; ensure_seeded onu TOHUMLAMAZ (config.yaml gibi bir sablonu
    yoktur — baska makinenin aktivasyonu HMAC tutmadigi icin anlamsiz bir
    "baska bilgisayar" hatasi verirdi)."""
    yol = Path(paths.activation_path())
    assert yol.parent == Path(paths.data_root())
    assert yol.name == lisans_durum.DOSYA_ADI
    paths.ensure_seeded()
    assert not yol.exists()
    assert not (Path(paths.resource_root()) / lisans_durum.DOSYA_ADI).exists()


def test_gecerlilik_gun_YOKSA_mutlak_tavan_baglayicidir():
    """Lisans Merkezi'nin dakikalik TEST anahtari boyledir: gecerlilik_gun
    bos, yalniz son_kullanim_ts dolu (uretim.test_ver). `if gun:` kontrolu
    `if gun is not None:` diye "duzeltilirse" ilk aktivasyon + 0 gun = aninda
    dolmus bir anahtar cikar; None birakilmasi bilinclidir."""
    ilk = 1_000_000.0
    yuk = {"tip": "demo", "gecerlilik_gun": None, "son_kullanim_ts": ilk + 60}
    assert lisans_durum.bitis_ts(yuk, ilk) == ilk + 60


def test_iki_sinir_da_yoksa_sinirsiz():
    yuk = {"tip": "demo", "gecerlilik_gun": None, "son_kullanim_ts": None}
    assert lisans_durum.bitis_ts(yuk, 1_000_000.0) is None


def test_veri_koku_YOKKEN_yaz_klasoru_ACAR(metin, monkeypatch, tmp_path):
    """Donmus EXE'de lisans kapisi ensure_seeded'dan ONCE calisir; o ana kadar
    %LOCALAPPDATA%\Aican yoktur. yaz() klasoru kendisi acmali —
    aksi halde FileNotFoundError, ekranda 'anahtar gecerli degil' (sahte)."""
    yeni = tmp_path / "henuz" / "yok"
    monkeypatch.setenv("AICAN_DATA_ROOT", str(yeni))
    lisans_durum.yaz(metin, {"anakart": "a", "disk": "b", "mac": "c"})
    assert (yeni / "aktivasyon.dat").exists()
