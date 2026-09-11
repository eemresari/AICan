"""Makine parmak izi ve 3'ten 2'si esigi.

NEDEN ESIK: sergi PC'sinin ekran karti ya da ag karti degisince musteri
kilitlenmemeli; makine komple degisince durmali. Tek bilesene baglamak ilkini,
uc bilesene birden baglamak ikincisini bozardi.

Bu dosya PowerShell/WMI CAGIRMAZ — bilesenler enjekte edilir.
"""

from __future__ import annotations

import pytest

import parmak_izi

TAM = {"anakart": "a" * 16, "disk": "b" * 16, "mac": "c" * 16}


def test_ozet_16_hane_ve_kararli():
    a = parmak_izi._ozetle("ABC-123")
    assert len(a) == 16 and a == parmak_izi._ozetle("ABC-123")
    assert a != parmak_izi._ozetle("ABC-124")


def test_bosluk_ve_buyuk_kucuk_harf_onemsiz():
    """WMI ciktisi bazen bosluklu, bazen kucuk harfli gelir; ayni makine iki
    farkli parmak izi uretmemeli."""
    assert parmak_izi._ozetle("  abc-123 ") == parmak_izi._ozetle("ABC-123")


def test_uc_bilesen_toplanir(monkeypatch):
    monkeypatch.setattr(parmak_izi, "_bilesenleri_topla",
                        lambda: {"anakart": "U1", "disk": "D1", "mac": "M1"})
    izi = parmak_izi.al()
    assert set(izi) == {"anakart", "disk", "mac"}
    assert all(v and len(v) == 16 for v in izi.values())


def test_bir_bilesen_degisince_TUTAR():
    """Ekran/ag karti degisimi senaryosu."""
    simdiki = dict(TAM, mac="z" * 16)
    assert parmak_izi.tutuyor_mu(TAM, simdiki)


def test_iki_bilesen_degisince_TUTMAZ():
    simdiki = dict(TAM, mac="z" * 16, disk="y" * 16)
    assert not parmak_izi.tutuyor_mu(TAM, simdiki)


def test_none_bilesen_ESLESME_SAYMAZ():
    """Okunamayan bilesen 'esitim' demez; iki None uc uca gelip yanlis
    kurulumu acmamali."""
    kayitli = dict(TAM, disk=None)
    simdiki = dict(TAM, disk=None, mac="z" * 16)
    assert not parmak_izi.tutuyor_mu(kayitli, simdiki)


def test_iki_bilesen_okunamazsa_HATA(monkeypatch):
    monkeypatch.setattr(parmak_izi, "_bilesenleri_topla",
                        lambda: {"anakart": "U1", "disk": None, "mac": None})
    with pytest.raises(parmak_izi.ParmakIziYok):
        parmak_izi.al()


def test_birincil_anakart_yoksa_diske_duser():
    ad, ozet = parmak_izi.birincil(TAM)
    assert ad == "anakart"
    ad2, _ = parmak_izi.birincil(dict(TAM, anakart=None))
    assert ad2 == "disk"


def test_powershell_KONSOL_PENCERESI_ACMAZ(monkeypatch):
    """windows-console-mode=disable EXE'de her subprocess yeni bir konsol
    penceresi acar (lisans ekraninda yanip sonen terminaller). Windows'ta
    CREATE_NO_WINDOW gecilmeli."""
    import subprocess
    import sys
    yakalanan = {}

    class Sonuc:
        stdout = "x"

    def sahte_run(*a, **k):
        yakalanan.update(k)
        return Sonuc()
    monkeypatch.setattr(subprocess, "run", sahte_run)
    assert parmak_izi._powershell("1") == "x"
    if sys.platform == "win32":
        assert yakalanan.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW
