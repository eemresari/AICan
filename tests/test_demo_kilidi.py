"""Demo lisans kilidi (plan sapma #3) + filigran ucu (sapma #4).

Demo'da mevcut test modu ZORLA ACIK ve KILITLI: sohbet kapali, yalniz
TEST_OYUNLAR, Ollama'ya hic gidilmez (warmup thread'i bile baslamaz), model
yonetim uclari 403. Demo degilken (kaynaktan calistirma / kalici lisans) eski
davranis AYNEN: config.json'daki test_mode gecerli, POST ile degisir.

Arka plan yukleyicileri (Whisper, TTS) config bayraklariyla kapali: testler
mikrofona/GPU'ya dokunmaz. warmup_on_start bilerek ACIK birakilir — demo'da
baslamadigi _warmup_baslat sayilarak kanitlanir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import paths
import web_server

KOK = Path(__file__).resolve().parent.parent


def _cfg(**ezme) -> dict:
    cfg = json.loads((KOK / "orchestrator" / "config.json").read_text(encoding="utf-8-sig"))
    cfg.update(warmup_on_start=False, whisper_enabled=False, tts_enabled=False,
               test_mode=False)
    cfg.update(ezme)
    return cfg


@pytest.fixture
def kur(monkeypatch, tmp_path):
    """create_app'i tmp veri kokuyle kur; warmup cagrilarini say."""
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path / "veri"))
    monkeypatch.setattr(paths, "PAKET", None)
    sayac = {"warmup": 0}

    def sahte_warmup(bridge):
        sayac["warmup"] += 1
    monkeypatch.setattr(web_server, "_warmup_baslat", sahte_warmup)

    def _kur(demo: bool, **ezme):
        app = web_server.create_app(_cfg(**ezme), demo=demo)
        return app.test_client(), sayac
    return _kur


# --------------------------------------------------------------------------- #
# Demo: kilit
# --------------------------------------------------------------------------- #

def test_demo_test_modu_zorla_ACIK_ve_kilitli(kur):
    c, _ = kur(demo=True, test_mode=False)   # config kapali dese de
    r = c.get("/api/test_mode")
    assert r.status_code == 200
    d = r.get_json()
    assert d["on"] is True
    assert d["kilitli"] is True
    assert d["games"] == list(web_server.TEST_OYUNLAR)


def test_demo_POST_test_mode_403(kur, tmp_path):
    c, _ = kur(demo=True)
    for govde in ({"on": False}, {}, {"on": True}):
        r = c.post("/api/test_mode", json=govde)
        assert r.status_code == 403
        assert r.get_json() == {"error": "demo_kilidi"}
    # Kilit kalici: hala acik; config'e de yazilmadi (tmp veri kokunde dosya yok)
    assert c.get("/api/test_mode").get_json()["on"] is True
    assert not (tmp_path / "veri" / "config.json").exists()


def test_demo_ollama_yonetim_uclari_403(kur):
    c, _ = kur(demo=True)
    assert c.get("/api/models").status_code == 403
    assert c.post("/api/model", json={"name": "x"}).status_code == 403
    assert c.post("/api/pull", json={"name": "x"}).status_code == 403
    for r in (c.get("/api/models"), c.post("/api/model", json={"name": "x"})):
        assert r.get_json() == {"error": "demo_kilidi"}


def test_demo_warmup_BASLAMAZ(kur):
    _, sayac = kur(demo=True, warmup_on_start=True)
    assert sayac["warmup"] == 0


def test_demo_send_sohbet_kapali_LLMe_gitmez(kur, monkeypatch):
    """/api/send demo'da mevcut test modu yolundan cevaplar: sabit yonlendirme
    metni, LLM cagrisi yok. Yeni metin uydurulmadi — TEST_SOHBET_KAPALI_TEXT."""
    from llm_bridge import LLMBridge
    monkeypatch.setattr(LLMBridge, "request",
                        lambda self, text: pytest.fail("demo'da LLM'e gidilmemeli"))
    c, _ = kur(demo=True)
    r = c.post("/api/send", json={"text": "bana uzayi anlat"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["yanit"] == web_server.TEST_SOHBET_KAPALI_TEXT
    assert d["meta"]["test_mode"] is True


def test_demo_selam_dogrudan_oyun_menusu(kur):
    c, _ = kur(demo=True)
    d = c.post("/api/session/new", json={"reason": "greet"}).get_json()
    assert d["yanit"] == web_server.TEST_GREETING_TEXT
    anahtarlar = {b.get("key") for b in d.get("buttons", [])}
    assert anahtarlar and anahtarlar <= set(web_server.TEST_OYUNLAR)


# --------------------------------------------------------------------------- #
# Demo degil: eski davranis
# --------------------------------------------------------------------------- #

def test_normal_kilit_YOK_ve_toggle_calisir(kur, tmp_path):
    c, _ = kur(demo=False, test_mode=False)
    d = c.get("/api/test_mode").get_json()
    assert d["on"] is False and d["kilitli"] is False
    r = c.post("/api/test_mode", json={"on": True})
    assert r.status_code == 200 and r.get_json()["on"] is True
    assert c.get("/api/test_mode").get_json()["on"] is True
    r = c.post("/api/test_mode", json={})          # toggle
    assert r.status_code == 200 and r.get_json()["on"] is False


def test_normal_config_test_mode_gecerli(kur):
    c, _ = kur(demo=False, test_mode=True)
    d = c.get("/api/test_mode").get_json()
    assert d["on"] is True and d["kilitli"] is False


def test_normal_warmup_BASLAR(kur):
    _, sayac = kur(demo=False, warmup_on_start=True)
    assert sayac["warmup"] == 1


def test_normal_model_uclari_403_DEGIL(kur, monkeypatch):
    from llm_bridge import LLMBridge
    monkeypatch.setattr(LLMBridge, "list_local_models", lambda self: [])
    c, _ = kur(demo=False)
    r = c.get("/api/models")
    assert r.status_code == 200 and r.get_json()["models"] == []
    assert c.post("/api/model", json={}).status_code == 400   # ad bos -> eski dogrulama
    assert c.post("/api/pull", json={}).status_code == 400


# --------------------------------------------------------------------------- #
# /api/filigran
# --------------------------------------------------------------------------- #

def test_filigran_ucu_modul_degiskenini_verir(kur, monkeypatch):
    c, _ = kur(demo=True)
    monkeypatch.setattr(web_server, "FILIGRAN", "Kurum A — 01.01.2027 — #5")
    r = c.get("/api/filigran")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/json")
    assert "no-store" in r.headers["Cache-Control"]
    assert r.get_json() == {"metin": "Kurum A — 01.01.2027 — #5"}


def test_filigran_bos(kur, monkeypatch):
    c, _ = kur(demo=False)
    monkeypatch.setattr(web_server, "FILIGRAN", "")
    assert c.get("/api/filigran").get_json() == {"metin": ""}
