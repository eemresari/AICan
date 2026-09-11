"""Flask sunucusunun BELLEKTEN servis yolu (sifreli web.pak icin).

Donmus build'de web/ diskte HAM durmaz; web.pak lisans anahtariyla bellege
cozulur ve `create_app(config, paket=...)` o sozlukten servis eder. Diskten
servis (kaynaktan calistirma, paket=None) aynen kalir. /assets/ her iki
durumda da diskten gelir (16 MB emoji PNG, kaynak degil).

Arka plan yukleyicileri (Ollama warmup, Whisper, TTS) config bayraklariyla
kapali: testler mikrofona/GPU'ya/aga dokunmaz.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import paths
import web_paket
import web_server

KOK = Path(__file__).resolve().parent.parent


def _cfg() -> dict:
    cfg = json.loads((KOK / "orchestrator" / "config.json").read_text(encoding="utf-8-sig"))
    cfg.update(warmup_on_start=False, whisper_enabled=False, tts_enabled=False)
    return cfg


@pytest.fixture
def paket():
    """Gercek web/ + ai/ icerigi bellekte; web dosyalari ayirt edilebilir sahte
    govdeyle ezilir ki 'diskten mi bellekten mi geldi' kesin gorulsun."""
    d = web_paket.topla(KOK)
    d["web/AI_Body_v2.html"] = b"<h1>BELLEK sergi</h1>"
    d["web/Kontrol_Paneli.html"] = b"<h1>BELLEK kontrol</h1>"
    d["web/app.js"] = b"// BELLEK app"
    d["web/led-panel.js"] = b"// BELLEK led"
    d["web/sahte.woff2"] = b"wOF2"
    return d


@pytest.fixture
def istemci(monkeypatch, tmp_path, paket):
    """paket verilmis uygulama. Oturum logu tmp'ye; paths.PAKET test sonunda
    eski haline (monkeypatch kaydi create_app'in atamasindan ONCE alinir)."""
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path / "veri"))
    monkeypatch.setattr(paths, "PAKET", None)
    assets = tmp_path / "assets"
    (assets / "emojis").mkdir(parents=True)
    (assets / "emojis" / "diskten.png").write_bytes(b"\x89PNG disk")
    monkeypatch.setattr(web_server, "ASSETS_DIR", assets)
    monkeypatch.setattr(web_server, "EMOJI_BASE_DIR", assets / "emojis")
    app = web_server.create_app(_cfg(), paket=paket)
    return app.test_client()


# --------------------------------------------------------------------------- #
# yol_coz / icerik_turu — saf yordamlar
# --------------------------------------------------------------------------- #

def test_yol_coz_web_on_eki_ve_sorgu_dizesi():
    """`?v=` atilmazsa EXE'de hicbir dosya bulunamaz ve kiosk bos ekran acar."""
    assert web_server.yol_coz("app.js?v=1") == "web/app.js"
    assert web_server.yol_coz("/app.js?v=1#x") == "web/app.js"
    assert web_server.yol_coz("alt/dosya.css") == "web/alt/dosya.css"


def test_yol_coz_ust_dizin_kacisi_reddedilir():
    for kotu in ("../lisans.py", "a/../../x", "./app.js", "a//b", ""):
        with pytest.raises(KeyError):
            web_server.yol_coz(kotu)


@pytest.mark.parametrize("ad,tur", [
    ("web/app.js", "application/javascript"),
    ("web/AI_Body_v2.html", "text/html"),
    ("web/a.css", "text/css"),
    ("ai/gestures.json", "application/json"),
    ("x.svg", "image/svg+xml"),
    ("x.png", "image/png"),
    ("x.ico", "image/x-icon"),
    ("x.woff2", "font/woff2"),
    ("x.wav", "audio/wav"),
    ("bilinmeyen.xyz", "application/octet-stream"),
])
def test_icerik_turu(ad, tur):
    assert web_server.icerik_turu(ad).startswith(tur)


# --------------------------------------------------------------------------- #
# HTTP — bellekten
# --------------------------------------------------------------------------- #

def test_kok_sergi_sayfasi_bellekten(istemci):
    r = istemci.get("/")
    assert r.status_code == 200 and r.data == b"<h1>BELLEK sergi</h1>"
    assert r.content_type.startswith("text/html")
    assert "no-store" in r.headers["Cache-Control"]


def test_control_ve_kontrol_bellekten(istemci):
    for yol in ("/control", "/kontrol"):
        r = istemci.get(yol)
        assert r.status_code == 200 and r.data == b"<h1>BELLEK kontrol</h1>"


def test_surumlu_js_bellekten_dogru_mime(istemci):
    r = istemci.get("/app.js?v=1")
    assert r.status_code == 200 and r.data == b"// BELLEK app"
    assert r.content_type.startswith("application/javascript")
    assert "no-store" in r.headers["Cache-Control"]
    assert int(r.headers["Content-Length"]) == len(r.data)


def test_font_bellekten(istemci):
    r = istemci.get("/sahte.woff2")
    assert r.status_code == 200 and r.content_type.startswith("font/woff2")


def test_olmayan_yol_404(istemci):
    assert istemci.get("/yok.js").status_code == 404


def test_pakette_olmayan_disk_dosyasi_404(paket, monkeypatch, tmp_path):
    """Paket varken DISKE DUSULMEZ: web/control.js diskte var ama paketten
    cikarilinca 404 — lisanssiz icerik gorunmemeli."""
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path / "veri"))
    monkeypatch.setattr(paths, "PAKET", None)
    del paket["web/control.js"]
    assert (KOK / "web" / "control.js").is_file()
    c = web_server.create_app(_cfg(), paket=paket).test_client()
    assert c.get("/control.js").status_code == 404


def test_ust_dizin_kacisi_404(istemci):
    for yol in ("/../lisans.py", "/..%2Flisans.py", "/%2e%2e/lisans.py"):
        assert istemci.get(yol).status_code == 404, yol


def test_ai_dosyalari_URL_uzerinden_SERVIS_EDILMEZ(istemci):
    """Paket ai/ da icerir ama HTTP yalniz web/ altini gorur; system_prompt
    ve tablolar tarayicidan cekilemez."""
    assert istemci.get("/system_prompt.txt").status_code == 404
    assert istemci.get("/../ai/system_prompt.txt").status_code == 404
    assert istemci.get("/ai/system_prompt.txt").status_code == 404


def test_assets_diskten_kalir(istemci):
    r = istemci.get("/assets/emojis/diskten.png")
    assert r.status_code == 200 and r.data == b"\x89PNG disk"


def test_api_gestures_paketten(istemci):
    r = istemci.get("/api/gestures")
    assert r.status_code == 200 and r.get_json()["jestler"]


def test_create_app_paketi_paths_PAKET_e_baglar(istemci, paket):
    """Yukleyiciler (LLMBridge, GameEngine) ayni sozlukten okusun diye
    create_app paketi paths.PAKET'e koyar."""
    assert paths.PAKET is paket


def test_demo_parametresi_kabul_edilir(monkeypatch, tmp_path, paket):
    """G5 davranisi ekleyecek; simdilik imza kirilmasin."""
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path / "veri"))
    monkeypatch.setattr(paths, "PAKET", None)
    app = web_server.create_app(_cfg(), paket=paket, demo=True)
    assert app.test_client().get("/").status_code == 200


# --------------------------------------------------------------------------- #
# HTTP — paket yokken eski diskten servis AYNEN
# --------------------------------------------------------------------------- #

def test_paket_yokken_diskten_servis(monkeypatch, tmp_path):
    monkeypatch.setenv("AICAN_DATA_ROOT", str(tmp_path / "veri"))
    monkeypatch.setattr(paths, "PAKET", None)
    c = web_server.create_app(_cfg()).test_client()
    r = c.get("/app.js?v=1")
    assert r.status_code == 200
    assert r.data == (KOK / "web" / "app.js").read_bytes()
    assert "no-store" in r.headers["Cache-Control"]
    assert c.get("/").status_code == 200
    assert c.get("/control").status_code == 200
    assert c.get("/yok.js").status_code == 404
    assert paths.PAKET is None
