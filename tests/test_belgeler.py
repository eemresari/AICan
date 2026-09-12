"""Musteriye giden belgelerin (KURULUM.md, TESLIM.md) urun gerceklerinden
sapmadigini kilitler (plan G8, docs/plans/2026-09-11-lisans-ve-kurucu-entegrasyonu.md).

Mesajlar `lisans_ekrani.DURUMLAR`'dan, model adi `orchestrator/config.json`'dan,
kurucu adi `surum.py`'den IMPORT edilir: bunlardan biri degisirse bu test
kirilir ve belgenin guncellenmedigi hemen ortaya cikar. Belge metnini burada
tekrar yazmiyoruz, yalniz kilitliyoruz.
"""

from __future__ import annotations

import json
from pathlib import Path

import lisans_ekrani
import surum

KOK = Path(__file__).resolve().parent.parent
KURULUM_MD = KOK / "docs" / "KURULUM.md"
TESLIM_MD = KOK / "docs" / "TESLIM.md"


def _oku(yol: Path) -> str:
    return yol.read_text(encoding="utf-8")


def test_belgeler_var():
    assert KURULUM_MD.is_file()
    assert TESLIM_MD.is_file()


def test_smartscreen_metinleri_spraytarih_ile_birebir():
    """SprayTarih docs/KURULUM.md'deki ayni iki cumle — kelimesi kelimesine."""
    metin = _oku(KURULUM_MD)
    assert "Daha fazla bilgi" in metin
    assert "Yine de çalıştır" in metin


def test_yedi_lisans_durumunun_hepsi_KURULUM_MD_de_geciyor():
    # durumu_belirle'nin donebilecegi 7 durum: yok, doldu, baska_makine, saat,
    # gecersiz, surum, urun (bkz. lisans_ekrani.py).
    assert len(lisans_ekrani.DURUMLAR) == 7
    metin = _oku(KURULUM_MD)
    for durum, mesaj in lisans_ekrani.DURUMLAR.items():
        assert mesaj in metin, f"durum={durum!r} mesaji KURULUM.md'de yok: {mesaj!r}"


def test_on_kosullar_NVIDIA_ve_internet_KURULUM_MD_de():
    metin = _oku(KURULUM_MD)
    assert "NVIDIA" in metin
    assert "internet" in metin.lower()


def test_ollama_pull_satirinda_config_daki_model_adi():
    cfg = json.loads((KOK / "orchestrator" / "config.json").read_text(encoding="utf-8"))
    model = cfg["ollama_model"]
    metin = _oku(KURULUM_MD)
    assert f"ollama pull {model}" in metin


def test_dusunemiyorum_hata_tablosunda():
    assert "Şu an düşünemiyorum" in _oku(KURULUM_MD)


def test_KURULUM_MD_ilk_acilis_INDIRMESI_vaat_etmez():
    """Whisper modeli ve Piper sesi artik kurucunun icinde geliyor
    (build.verify_dist ikisini de zorunlu tutuyor), yani musteriye "ilk
    acilista iner, bekleyin" demek YANLIS. Eski metin oyle diyordu."""
    metin = _oku(KURULUM_MD)
    assert "Whisper modeli iniyor" not in metin
    assert "indirme beklemesi yoktur" in metin


def test_KURULUM_MD_internetsiz_calismayi_dogru_anlatir():
    """Cevrimdisi Piper yedegi pakete girdigi icin internet artik ZORUNLU
    degil; yalnizca sesli yanit kalitesini etkiliyor."""
    metin = _oku(KURULUM_MD)
    assert "tamamen çevrimdışı çalışmaz" not in metin
    assert "çevrimdışı" in metin


def test_gpu_yoksa_bilinmiyor_denir_kesin_iddia_yok():
    """Plan acikca yasakliyor: 'CPU'ya duser, yavas' YAZMA, 'GPU'suz makine
    desteklenmez' de YAZMA — 'bilinmiyor' de, elle test bekliyor."""
    metin = _oku(KURULUM_MD)
    assert "bilinmiyor" in metin.lower()
    assert "cpu'ya düşer" not in metin.lower()
    assert "desteklenmez" not in metin.lower()


def test_aktivasyon_ve_log_yolu_KURULUM_MD_de():
    metin = _oku(KURULUM_MD)
    assert r"%LOCALAPPDATA%\Aican" in metin
    assert "logs" in metin


def test_teslim_md_kurucu_adini_surumden_tasir():
    metin = _oku(TESLIM_MD)
    assert surum.KURUCU_ADI in metin


def test_teslim_md_dogrulama_maddelerine_isaret_ediyor():
    metin = _oku(TESLIM_MD)
    assert "Doğrulama" in metin
