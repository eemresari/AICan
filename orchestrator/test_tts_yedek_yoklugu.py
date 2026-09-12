"""Piper cevrimdisi yedegi YOKKEN birincil TTS motoru ayakta kalmali.

G0 build spike'inda olculdu (2026-09-11): EXE'de `tts/voices/*.onnx` yoktu,
PiperEngine kurulusta exception atti, exception `_load_tts_async`'in dis
try blogunu tetikledi ve `tts_engine="edge"` olmasina ragmen TTS TAMAMEN
oldu ("TTS yuklenemedi: Piper ses modeli yok"). Sergi sessiz kaldi.
Yedegin yoklugu birincili oldurmemeli.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import web_server


class _SahteMotor:
    """EdgeEngine/ElevenLabsEngine yerine — ag istegi yok."""

    def __init__(self, voice="", **kw):
        self.voice_name = voice or "sahte"

    def synth(self, *a, **kw):
        return b"ses"


@pytest.fixture
def piper_yok(monkeypatch):
    """PiperEngine kurulusu patlasin (ses dosyasi yok senaryosu)."""
    import tts.engine_piper as ep

    def _patla(*a, **kw):
        raise RuntimeError("Piper ses modeli yok: tr_TR-dfki-medium.onnx")

    monkeypatch.setattr(ep, "PiperEngine", _patla)
    import tts.engine_edge as ee
    monkeypatch.setattr(ee, "EdgeEngine", _SahteMotor)
    # Acilis probu ag'a cikmasin; motoru oldugu gibi birak.
    monkeypatch.setattr(web_server, "_probe_edge_or_pin_fallback", lambda e: e)
    monkeypatch.setattr(web_server, "_warm_tts_cache", lambda *a, **kw: None)


def _durum(config, piper_yok_fixture=None):
    state = web_server.TTSState()
    web_server._load_tts_async(state, config, cache=None)
    return state


def test_edge_birincil_piper_yedegi_yoksa_TTS_yasar(piper_yok):
    state = _durum({"tts_engine": "edge", "tts_fallback_enabled": True})
    assert state.status == "hazir", f"TTS olmus: {state.error}"
    assert state.engine is not None


def test_elevenlabs_birincil_piper_yedegi_yoksa_TTS_yasar(piper_yok, monkeypatch):
    import tts.engine_elevenlabs as el
    monkeypatch.setattr(el, "ElevenLabsEngine", _SahteMotor)
    state = _durum({"tts_engine": "elevenlabs", "tts_fallback_enabled": True})
    assert state.status == "hazir", f"TTS olmus: {state.error}"
    assert state.engine is not None


def test_piper_BIRINCILKEN_yoklugu_hata_olarak_kalir(piper_yok):
    """Piper tek motorsa sessizce 'hazir' deme — durum 'hata' olmali."""
    state = _durum({"tts_engine": "piper"})
    assert state.status == "hata"
