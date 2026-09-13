"""Motor <-> ses uyumsuzlugu sessizce ucretsiz sese dusmesin + onbellek
zehirlenmesi kapali kalsin.

2026-09-13 sahasi: kurulu makinenin config'i `tts_engine="edge"` +
`tts_voice="01p4omegjS2n3rSDCM5u"` (bir ElevenLabs voice_id) tasiyordu.
edge-tts bunu ancak ilk sentezde reddediyor, acilis probu da motoru kalici
Piper'a sabitliyordu; sonra Piper sesleri ElevenLabs anahtar uzayina
yaziliyordu (51 dosya, 22050 Hz). Ag'a cikilmaz: tum motorlar sahte.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import web_server


class _SahteMotor:
    """EdgeEngine/PiperEngine/ElevenLabsEngine yerine — ag istegi yok."""

    name = "sahte"

    def __init__(self, voice="", **kw):
        self.voice_name = voice or "sahte"

    def synthesize(self, *a, **kw):
        return b"RIFFses"


class _SahteEdge(_SahteMotor):
    name = "edge"


class _SahtePiper(_SahteMotor):
    name = "piper"


@pytest.fixture
def sahte_motorlar(monkeypatch):
    import tts.engine_edge as ee
    import tts.engine_piper as ep
    monkeypatch.setattr(ee, "EdgeEngine", _SahteEdge)
    monkeypatch.setattr(ep, "PiperEngine", _SahtePiper)
    # Acilis probu ag'a cikmasin; motoru oldugu gibi birak (logger 2. arg).
    monkeypatch.setattr(web_server, "_probe_edge_or_pin_fallback",
                        lambda e, logger=None: e)
    monkeypatch.setattr(web_server, "_warm_tts_cache", lambda *a, **kw: None)


# --------------------------------------------------------------------------- #
# 1) Gecersiz tts_voice + tts_engine="edge"
# --------------------------------------------------------------------------- #

def _yukle(config):
    state = web_server.TTSState()
    web_server._load_tts_async(state, config, cache=None)
    return state


def test_elevenlabs_voice_id_edge_altinda_varsayilana_duser(sahte_motorlar):
    config = {"tts_engine": "edge", "tts_voice": "01p4omegjS2n3rSDCM5u"}
    state = _yukle(config)
    assert state.status == "hazir"
    # Motor EDGE'de kalir (Piper'a sabitlenmez) ve gecerli bir sesle konusur.
    assert state.engine.voice_name == web_server.DEFAULT_TTS_VOICE
    # Config de duzeltilir: onbellek anahtari sesten turetiliyor, yoksa
    # ucretsiz ses ElevenLabs anahtar uzayina yazilirdi.
    assert config["tts_voice"] == web_server.DEFAULT_TTS_VOICE


def test_gecerli_edge_sesi_DEGISTIRILMEZ(sahte_motorlar):
    config = {"tts_engine": "edge", "tts_voice": "tr-TR-AhmetNeural"}
    state = _yukle(config)
    assert state.engine.voice_name == "tr-TR-AhmetNeural"
    assert config["tts_voice"] == "tr-TR-AhmetNeural"


def test_elevenlabs_motorunda_voice_id_DOKUNULMAZ(sahte_motorlar, monkeypatch):
    """Kalip kontrolu YALNIZ edge icin; ElevenLabs voice_id'si gecerlidir."""
    import tts.engine_elevenlabs as el
    monkeypatch.setattr(el, "ElevenLabsEngine", _SahteMotor)
    config = {"tts_engine": "elevenlabs", "tts_voice": "01p4omegjS2n3rSDCM5u"}
    _yukle(config)
    assert config["tts_voice"] == "01p4omegjS2n3rSDCM5u"


@pytest.mark.parametrize("voice", [
    "", None, "tr_TR-dfki-medium", "01p4omegjS2n3rSDCM5u", "EmelNeural", "tr-TR-Emel",
])
def test_edge_ses_kalibi_reddedilenler(voice):
    cfg = {"tts_engine": "edge", "tts_voice": voice}
    assert web_server._edge_sesini_dogrula(cfg) == web_server.DEFAULT_TTS_VOICE


@pytest.mark.parametrize("voice", ["tr-TR-EmelNeural", "en-US-AriaNeural",
                                   "de-DE-KatjaNeural"])
def test_edge_ses_kalibi_kabul_edilenler(voice):
    cfg = {"tts_engine": "edge", "tts_voice": voice}
    assert web_server._edge_sesini_dogrula(cfg) == voice


# --------------------------------------------------------------------------- #
# 2) Onbellek zehirlenmesi
# --------------------------------------------------------------------------- #

class _SahteOnbellek:
    enabled = True

    def __init__(self):
        self.yazilanlar = {}

    def make_key(self, text, jest_id, yogunluk, voice):
        return f"{voice}|{text}"

    def get(self, key):
        return self.yazilanlar.get(key)

    def put(self, key, data):
        self.yazilanlar[key] = data


def _sentezle(engine, config):
    state = web_server.TTSState()
    state.engine = engine
    cache = _SahteOnbellek()
    web_server._tts_synth_cached(state, cache, config, "merhaba")
    return cache


def test_pipere_SABITLENMIS_motor_onbellege_YAZMAZ():
    """Acilis probu edge'i Piper'a sabitledi: duz PiperEngine'in last_engine'i
    yoktur — eski kontrol bu delikten ucretsiz sesi yaziyordu."""
    config = {"tts_engine": "edge", "tts_voice": "tr-TR-EmelNeural"}
    cache = _sentezle(_SahtePiper(), config)
    assert cache.yazilanlar == {}


def test_yedege_dusen_fallback_onbellege_YAZMAZ():
    from tts.engine_base import FallbackEngine

    class _BosEdge(_SahteEdge):
        def synthesize(self, *a, **kw):
            return b""

    engine = FallbackEngine(_BosEdge(), _SahtePiper())
    config = {"tts_engine": "edge", "tts_voice": "tr-TR-EmelNeural"}
    cache = _sentezle(engine, config)
    assert engine.last_engine == "piper"
    assert cache.yazilanlar == {}


def test_istenen_motor_uretince_onbellege_YAZAR():
    from tts.engine_base import FallbackEngine
    engine = FallbackEngine(_SahteEdge(), _SahtePiper())
    config = {"tts_engine": "edge", "tts_voice": "tr-TR-EmelNeural"}
    cache = _sentezle(engine, config)
    assert engine.last_engine == "edge"
    assert list(cache.yazilanlar.values()) == [b"RIFFses"]


def test_elevenlabs_isteginde_edge_yedegi_YAZMAZ():
    """ElevenLabs anahtari yokken edge sesi, on-uretilmis 44100 Hz parcalarin
    anahtarlarini golgelememeli."""
    from tts.engine_base import FallbackEngine

    class _BosEleven(_SahteMotor):
        name = "elevenlabs"

        def synthesize(self, *a, **kw):
            return b""

    engine = FallbackEngine(_BosEleven(), _SahteEdge())
    config = {"tts_engine": "elevenlabs", "tts_voice": "01p4omegjS2n3rSDCM5u"}
    cache = _sentezle(engine, config)
    assert engine.last_engine == "edge"
    assert cache.yazilanlar == {}
