"""web/ + ai/ agacinin sifreli icerik paketi (web.pak).

TEHDIT: standalone EXE'nin yaninda web/ ve ai/ ham dururlarsa oyunun on yuzu
(app.js, control.js, led-panel.js), oyun veri tablolari (atasozu, es/zit,
dogru/yanlis) ve sistem promptu okunabilir kaynak olarak kalir — Nuitka'nin
korudugu Python tarafi degil, urunun kendisi. Paket bu yolu kapatir.

ANAHTAR EXE'DE DEGIL: cagiran taraf onu lisanstan getirir. assets/ (16 MB
emoji PNG) pakete GIRMEZ: gorsel, kaynak degil; diskten servis edilir.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

import pytest

import paths
import web_paket

KOK = Path(__file__).resolve().parent.parent


@pytest.fixture
def agac(tmp_path):
    """Depo yerlesiminin kucuk kopyasi: web/ + ai/ + assets/ + kokte py."""
    web = tmp_path / "web"
    web.mkdir()
    (web / "AI_Body_v2.html").write_text("<h1>Aican</h1>", encoding="utf-8")
    (web / "app.js").write_text("const x = 1;", encoding="utf-8")
    ai = tmp_path / "ai"
    ai.mkdir()
    (ai / "atasozu.json").write_text('[{"bas": "Damlaya"}]', encoding="utf-8")
    (ai / "system_prompt.txt").write_text("Sen Aican'sın.", encoding="utf-8")
    (ai / "Modelfile").write_text("FROM gemma3:4b", encoding="utf-8")
    assets = tmp_path / "assets" / "emojis" / "selam"
    assets.mkdir(parents=True)
    (assets / "frame_000.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "lisans.py").write_text("GIZLI = 1", encoding="utf-8")
    return tmp_path


def test_topla_web_ve_ai_posix_anahtarla(agac):
    dosyalar = web_paket.topla(agac)
    assert set(dosyalar) == {"web/AI_Body_v2.html", "web/app.js",
                             "ai/atasozu.json", "ai/system_prompt.txt"}
    assert dosyalar["web/app.js"] == b"const x = 1;"


def test_assets_ve_Modelfile_ve_kok_dosyalar_pakete_GIRMEZ(agac):
    """assets/ gorsel (diskten servis), Modelfile uretilmis (.gitignore),
    kokteki py dosyalari kaynak — hicbiri paket icerigi degil."""
    anahtarlar = set(web_paket.topla(agac))
    assert not any(a.startswith("assets/") for a in anahtarlar)
    assert "ai/Modelfile" not in anahtarlar
    assert "lisans.py" not in anahtarlar


def test_web_kok_ayri_verilebilir(agac, tmp_path):
    """build.py obfuscate edilmis web-hazir/ dizinini verir; anahtar yine web/."""
    hazir = tmp_path / "web-hazir"
    hazir.mkdir()
    (hazir / "app.js").write_text("var _0x=1;", encoding="utf-8")
    dosyalar = web_paket.topla(agac, web_kok=hazir)
    assert dosyalar["web/app.js"] == b"var _0x=1;"
    assert "web/AI_Body_v2.html" not in dosyalar
    assert "ai/atasozu.json" in dosyalar


def test_paketle_coz_bayt_bayt_ayni(agac):
    anahtar = secrets.token_bytes(32)
    dosyalar = web_paket.coz(web_paket.paketle(agac, anahtar, 1), anahtar)
    assert dosyalar == web_paket.topla(agac)
    assert dosyalar["web/AI_Body_v2.html"] == b"<h1>Aican</h1>"


def test_pakette_DUZ_METIN_yok(agac):
    """Paketin kendisi grep'lendiginde icerik gorunmemeli."""
    ham = web_paket.paketle(agac, secrets.token_bytes(32), 1)
    assert ham.startswith(web_paket.BASLIK)
    assert b"Aican</h1>" not in ham
    assert b"Damlaya" not in ham
    assert b"app.js" not in ham


def test_yanlis_anahtar_reddedilir(agac):
    ham = web_paket.paketle(agac, secrets.token_bytes(32), 1)
    with pytest.raises(Exception):
        web_paket.coz(ham, secrets.token_bytes(32))


def test_bozuk_baslik_anlamli_hata():
    with pytest.raises(ValueError, match="paket"):
        web_paket.coz(b"bu bir paket degil", secrets.token_bytes(32))


def test_SprayTarih_paketi_reddedilir():
    """Sihir urune ozel: baska urunun web.pak'i yanlislikla yuklenmesin."""
    with pytest.raises(ValueError, match="paket"):
        web_paket.paket_no_oku(b"STPAK1\n\x00\x00\x00\x01" + b"\x00" * 20)


def test_paket_no_ANAHTARSIZ_okunur(agac):
    """EXE, lisansi cozmeden once 'bu anahtar bu surum icin mi' diyebilmeli."""
    ham = web_paket.paketle(agac, secrets.token_bytes(32), 7)
    assert web_paket.paket_no_oku(ham) == 7


def test_paket_no_bozuk_veride_hata():
    with pytest.raises(ValueError, match="paket"):
        web_paket.paket_no_oku(b"kisa")


def test_gercek_depo_paketi_PAKET_simine_oturur(monkeypatch):
    """Gercek web/ + ai/ paketlenip cozulunce paths.PAKET'e konur ve config'in
    isaret ettigi her kaynak bellekten okunur; ai/Modelfile ve assets/ yoktur."""
    anahtar = secrets.token_bytes(32)
    dosyalar = web_paket.coz(web_paket.paketle(KOK, anahtar, 3), anahtar)
    assert "web/app.js" in dosyalar and "web/AI_Body_v2.html" in dosyalar
    assert "ai/Modelfile" not in dosyalar
    assert not any(a.startswith("assets/") for a in dosyalar)
    monkeypatch.setattr(paths, "PAKET", dosyalar)
    cfg = json.loads((KOK / "orchestrator" / "config.json").read_text(encoding="utf-8-sig"))
    jestler = json.loads(paths.kaynak_oku(paths.kaynak_rel(cfg["gestures_path"])))
    assert jestler["jestler"]
    assert paths.kaynak_oku(paths.kaynak_rel(cfg["system_prompt_path"]))
