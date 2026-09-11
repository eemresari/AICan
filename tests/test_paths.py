"""Tek yerden yol cozumleme (orchestrator/paths.py).

KAYNAKTAN calisirken hicbir yol degismez: config orchestrator/config.json'da,
loglar <depo>/logs, TTS onbellegi orchestrator/tts/cache, tarayici profili
<depo>/.tarayici_profili kalir. DONMUS (Nuitka) build'de yazilan her sey
%LOCALAPPDATA%\\Aican altina gider; Program Files'a kurulu EXE'nin yanina
yazilamaz.

`kaynak_oku` simi: ai/*.json ve web/ icerigi donmus build'de web.pak'tan
cozulmus bellek sozlugunden (PAKET), kaynakta diskten okunur. Tek sim, tum
yukleyiciler bunun uzerinden gecer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import paths

KOK = Path(__file__).resolve().parent.parent


@pytest.fixture
def donmus(monkeypatch, tmp_path):
    """FROZEN=True + LOCALAPPDATA gecici + exe dizini gecici."""
    monkeypatch.delenv("AICAN_DATA_ROOT", raising=False)
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    monkeypatch.setattr(paths.sys, "executable", str(exe_dir / "Aican.exe"))
    monkeypatch.delattr(paths.sys, "_MEIPASS", raising=False)
    return tmp_path


# --- kaynaktan calisirken: bugunku yollar AYNEN ---

def test_kaynakta_FROZEN_degil():
    assert paths.FROZEN is False


def test_kaynakta_kokler_depo(monkeypatch):
    monkeypatch.delenv("AICAN_DATA_ROOT", raising=False)
    assert Path(paths.resource_root()) == KOK
    assert Path(paths.data_root()) == KOK


def test_kaynakta_runtime_yollari_DEGISMEZ(monkeypatch):
    """Bu yollar bugunku davranisin birebir kopyasi; degisirse mevcut config,
    log ve onbellek bulunamaz olur."""
    monkeypatch.delenv("AICAN_DATA_ROOT", raising=False)
    assert Path(paths.config_path()) == KOK / "orchestrator" / "config.json"
    assert Path(paths.log_dir()) == KOK / "logs"
    assert Path(paths.session_log_path("../logs/session.log")) == KOK / "logs" / "session.log"
    assert Path(paths.stt_debug_dir()) == KOK / "logs" / "stt_debug"
    assert Path(paths.tts_cache_dir()) == KOK / "orchestrator" / "tts" / "cache"
    assert Path(paths.browser_profile_dir()) == KOK / ".tarayici_profili"
    assert Path(paths.elevenlabs_usage_path()) == KOK / "orchestrator" / "tts" / "elevenlabs_usage.json"
    assert Path(paths.activation_path()) == KOK / "aktivasyon.dat"


def test_kaynakta_config_gercekten_var():
    assert Path(paths.config_path()).is_file()


def test_session_log_mutlak_yol_aynen():
    assert Path(paths.session_log_path("C:/x/y.log")) == Path("C:/x/y.log")


# --- donmus build: her sey LOCALAPPDATA\\Aican altinda ---

def test_donmus_data_root_LOCALAPPDATA(donmus):
    assert Path(paths.data_root()) == donmus / "lad" / "Aican"
    assert Path(paths.resource_root()) == donmus / "exe"


def test_donmus_runtime_yollari_veri_kokunde(donmus):
    veri = donmus / "lad" / "Aican"
    assert Path(paths.config_path()) == veri / "config.json"
    assert Path(paths.log_dir()) == veri / "logs"
    assert Path(paths.session_log_path("../logs/session.log")) == veri / "logs" / "session.log"
    assert Path(paths.stt_debug_dir()) == veri / "logs" / "stt_debug"
    assert Path(paths.tts_cache_dir()) == veri / "tts" / "cache"
    assert Path(paths.browser_profile_dir()) == veri / ".tarayici_profili"
    assert Path(paths.elevenlabs_usage_path()) == veri / "elevenlabs_usage.json"
    assert Path(paths.activation_path()) == veri / "aktivasyon.dat"


def test_donmus_hicbir_yazma_yolu_exe_yaninda_DEGIL(donmus):
    exe = donmus / "exe"
    for yol in (paths.config_path(), paths.log_dir(), paths.tts_cache_dir(),
                paths.browser_profile_dir(), paths.elevenlabs_usage_path(),
                paths.activation_path()):
        assert exe not in Path(yol).parents, yol


def test_env_override_her_seyi_ezer(monkeypatch, tmp_path):
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path / "v"))
    assert Path(paths.data_root()) == tmp_path / "v"
    # Depo disinda bir veri kokunde duz (donmus) yerlesim kullanilir.
    assert Path(paths.config_path()) == tmp_path / "v" / "config.json"
    assert Path(paths.activation_path()) == tmp_path / "v" / "aktivasyon.dat"


# --- tohumlama ---

def test_seed_listesinde_aktivasyon_YOK_config_VAR():
    assert "config.json" in paths.SEED_FILES
    assert "aktivasyon.dat" not in paths.SEED_FILES


def test_donmus_ensure_seeded_config_tohumlar_aktivasyon_tohumlamaz(donmus):
    (donmus / "exe" / "config.json").write_text('{"a": 1}', encoding="utf-8")
    (donmus / "exe" / "aktivasyon.dat").write_text("x", encoding="utf-8")
    paths.ensure_seeded()
    veri = donmus / "lad" / "Aican"
    assert (veri / "config.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert not (veri / "aktivasyon.dat").exists()
    assert (veri / "logs").is_dir()


def test_donmus_ensure_seeded_mevcut_configi_EZMEZ(donmus):
    (donmus / "exe" / "config.json").write_text('{"a": 1}', encoding="utf-8")
    veri = donmus / "lad" / "Aican"
    veri.mkdir(parents=True)
    (veri / "config.json").write_text('{"a": 2}', encoding="utf-8")
    paths.ensure_seeded()
    assert json.loads((veri / "config.json").read_text(encoding="utf-8")) == {"a": 2}


def test_kaynakta_ensure_seeded_zararsiz(monkeypatch):
    """Kaynak ve hedef ayni dosya; kopyalama YAPILMAZ, dosya bozulmaz."""
    monkeypatch.delenv("AICAN_DATA_ROOT", raising=False)
    once = Path(paths.config_path()).read_bytes()
    paths.ensure_seeded()
    assert Path(paths.config_path()).read_bytes() == once


# --- kaynak_oku simi ---

def test_kaynak_oku_PAKET_bosken_diskten(monkeypatch):
    monkeypatch.setattr(paths, "PAKET", None)
    ham = paths.kaynak_oku("ai/gestures.json")
    assert ham == (KOK / "ai" / "gestures.json").read_bytes()
    assert "jestler" in json.loads(ham.decode("utf-8-sig"))


def test_kaynak_oku_PAKET_doluyken_bellekten(monkeypatch, donmus):
    """Donmus build'de diskte ai/ YOKTUR; PAKET doluysa diske hic bakilmaz."""
    monkeypatch.setattr(paths, "PAKET", {"ai/gestures.json": b'{"jestler": []}'})
    assert paths.kaynak_oku("ai/gestures.json") == b'{"jestler": []}'


def test_kaynak_oku_PAKET_doluyken_olmayan_yol(monkeypatch):
    monkeypatch.setattr(paths, "PAKET", {"web/app.js": b""})
    with pytest.raises(FileNotFoundError):
        paths.kaynak_oku("ai/yok.json")


def test_kaynak_oku_mutlak_yol_her_zaman_diskten(monkeypatch, tmp_path):
    """Test enjeksiyonu (categories_path=...) mutlak yol verir; pakette olamaz."""
    monkeypatch.setattr(paths, "PAKET", {})
    d = tmp_path / "x.json"
    d.write_text("[1]", encoding="utf-8")
    assert paths.kaynak_oku(str(d)) == b"[1]"


def test_kaynak_rel_orchestrator_goreli_yolu_pakete_cevirir():
    """config.json'daki '../ai/system_prompt.txt' orchestrator/'a gorelidir."""
    assert paths.kaynak_rel("../ai/system_prompt.txt") == "ai/system_prompt.txt"
    assert paths.kaynak_rel("..\\ai\\gestures.json") == "ai/gestures.json"
    assert Path(paths.kaynak_rel("C:/mutlak/x.txt")) == Path("C:/mutlak/x.txt")


# --- mevcut yukleyiciler simden gecer ---

_PAKET = {
    "ai/word_categories.json": json.dumps({"bilim": ["Atomcuk", "Nötrino"]}).encode(),
    "ai/es_zit_anlam_cocuklar_30_30.json": json.dumps(
        {"paketkelime": {"zit": ["paketzit"]}}).encode(),
    "ai/atasozu50.json": json.dumps([{"bas": "Paket bas", "tamam": ["paket son"]}]).encode(),
    "ai/dogru_yanlis.json": json.dumps(
        [{"ifade": "Paket ifade", "dogru": True, "aciklama": "p"}]).encode(),
    "ai/gestures.json": json.dumps({"jestler": [
        {"id": "paketjest", "duygu_valansi": 0.9, "uyarilma_seviyesi": 0.9}]}).encode(),
    "ai/system_prompt.txt": "PAKET PROMPT".encode(),
}


def test_GameEngine_tablolari_PAKETten_okur(monkeypatch):
    monkeypatch.setattr(paths, "PAKET", dict(_PAKET))
    from game_engine import GameEngine
    ge = GameEngine(bridge=None)
    assert "atomcuk" in ge._ai_pool.get("a", [])
    assert "paketkelime" in ge._providers["eszit"].data
    assert ge._providers["atasozu"].items[0]["bas"] == "Paket bas"
    assert ge._providers["dogruyanlis"].items[0]["ifade"] == "Paket ifade"


def test_word_llm_yedek_havuzu_PAKETten_okur(monkeypatch):
    monkeypatch.setattr(paths, "PAKET", dict(_PAKET))
    import word_llm
    monkeypatch.setattr(word_llm, "_yedek_havuz_cache", None)
    assert "nötrino" in word_llm._yedek_havuz().get("n", [])


def test_emotion_voice_map_gestures_PAKETten_okur(monkeypatch):
    monkeypatch.setattr(paths, "PAKET", dict(_PAKET))
    from tts import emotion_voice_map as evm
    evm._load_va.cache_clear()
    try:
        assert evm._load_va(evm._DEFAULT_GESTURES)["paketjest"] == (0.9, 0.9)
    finally:
        evm._load_va.cache_clear()


def test_LLMBridge_prompt_ve_jestleri_PAKETten_okur(monkeypatch):
    monkeypatch.setattr(paths, "PAKET", dict(_PAKET))
    from llm_bridge import LLMBridge
    cfg = json.loads(Path(paths.config_path()).read_text(encoding="utf-8-sig"))
    b = LLMBridge(cfg, KOK / "orchestrator")
    assert b.system_prompt == "PAKET PROMPT"
    assert b.valid_ids == {"paketjest"}


def test_web_server_api_gestures_PAKETten_okur_ve_depoya_yazmaz(monkeypatch, tmp_path):
    """/api/gestures diskteki ai/gestures.json'i degil, simi kullanir. Oturum
    logu da AICAN_DATA_ROOT altina gider; depo koku kirlenmez."""
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path / "veri"))
    monkeypatch.setattr(paths, "PAKET", dict(_PAKET))
    import web_server
    cfg = json.loads((KOK / "orchestrator" / "config.json").read_text(encoding="utf-8-sig"))
    # Arka plan yukleyicileri kapali: test Ollama/Whisper/TTS'e dokunmaz.
    cfg.update(warmup_on_start=False, whisper_enabled=False, tts_enabled=False)
    app = web_server.create_app(cfg)
    r = app.test_client().get("/api/gestures")
    assert r.status_code == 200
    assert [j["id"] for j in r.get_json()["jestler"]] == ["paketjest"]
    assert (tmp_path / "veri" / "logs" / "session.log").exists()
