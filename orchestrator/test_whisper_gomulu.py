"""Gomulu Whisper modeli donmus build'de kullanilmali, kaynakta kullanilmamali.

Model gomulu degilse faster-whisper ILK acilista HF'den indirir: G0 spike'inda
large-v3-turbo ~12 dakika surdu ve o sure boyunca /api/transcribe 503 dondu.
Sergide ses TEK giris aygiti oldugu icin mikrofon o sure boyunca olu demektir;
internetsiz kurulumda ise hic calismaz.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths
import web_server


def _gomulu_kur(kok: Path, boyut: str) -> Path:
    d = kok / "whisper" / boyut
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"ct2")
    return d


def test_kaynaktan_calisirken_gomulu_model_ARANMAZ(monkeypatch, tmp_path):
    """Gelistiricide faster-whisper kendi HF onbellegini kullanir."""
    monkeypatch.setattr(paths, "FROZEN", False)
    _gomulu_kur(tmp_path, "large-v3-turbo")
    monkeypatch.setattr(paths, "resource_root", lambda: str(tmp_path))
    assert web_server._gomulu_whisper_modeli("large-v3-turbo") is None


def test_frozen_da_gomulu_model_yolu_donerse_o_kullanilir(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "FROZEN", True)
    d = _gomulu_kur(tmp_path, "large-v3-turbo")
    monkeypatch.setattr(paths, "resource_root", lambda: str(tmp_path))
    assert web_server._gomulu_whisper_modeli("large-v3-turbo") == str(d)


def test_frozen_da_model_yoksa_None(monkeypatch, tmp_path):
    """model.bin yoksa boyut adiyla devam edilir (indirme yolu)."""
    monkeypatch.setattr(paths, "FROZEN", True)
    (tmp_path / "whisper" / "large-v3-turbo").mkdir(parents=True)
    monkeypatch.setattr(paths, "resource_root", lambda: str(tmp_path))
    assert web_server._gomulu_whisper_modeli("large-v3-turbo") is None
