"""Build komutu ve surum damgasi kilitleri (plan G6, sapma #5/#6/#8).

web/ ve ai/ HAM GIRMEZ: standalone dist'te EXE'nin yaninda okunabilir kaynak
olarak dururdu (sergi on yuzu JS'te, oyun tablolari ve sistem promptu ai/'de).
Yerine sifreli web.pak + ham lisans ekrani + assets gider. Damga degerleri
surum.py'den gelir — elle yazilan ikinci bir kaynak, kurucu adiyla EXE
ozelliklerinin ayrismasi demektir. Gercek derleme YAPILMAZ: komutu_olustur
saf fonksiyondur, liste doner.
"""

from __future__ import annotations

import base64
import inspect
import json
import os
import re
from pathlib import Path

import pytest

import build
import lisans
import paths
import surum
import web_server

KOK = Path(__file__).resolve().parent.parent


def _komut() -> list:
    return build.komutu_olustur(KOK / "build")


def _data_bayraklari(komut) -> list:
    return [p for p in komut
            if p.startswith("--include-data-dir=") or p.startswith("--include-data-files=")]


# --------------------------------------------------------------------------- #
# Ne girer, ne girmez
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("ham", ["web", "ai"])
def test_web_ve_ai_HAM_gomulmez(ham):
    for p in _data_bayraklari(_komut()):
        hedef = p.split("=", 2)[-1].replace("\\", "/")
        assert hedef != ham and not hedef.startswith(ham + "/"), p


def test_web_pak_lisans_ekrani_assets_tohum_girer():
    komut = _komut()
    assert any(p.startswith("--include-data-files=") and p.endswith("=web.pak")
               for p in komut), komut
    assert any(p.startswith("--include-data-dir=") and p.endswith("=lisans_web")
               for p in komut), komut
    assert any(p.startswith("--include-data-dir=") and p.endswith("=assets")
               for p in komut), komut
    tohum = [p for p in komut if p.startswith("--include-data-files=")
             and p.endswith("=config.json")]
    assert len(tohum) == 1, komut
    # Ham orchestrator/config.json DEGIL — normalize edilmis dist/config.json.
    assert tohum[0].replace("\\", "/").endswith("/dist/config.json=config.json")
    assert "orchestrator/config.json" not in tohum[0].replace("\\", "/")


@pytest.mark.parametrize("yasak", ["main.py", "veri_uretim", "kurulum",
                                   "build_model", "test_runner"])
def test_gelistirme_dosyalari_veri_olarak_GIRMEZ(yasak):
    """Tkinter prototipi ve gelistirme araclari (sapma #8) pakete girmez."""
    for p in _data_bayraklari(_komut()):
        assert yasak not in p.replace("\\", "/"), p


def test_run_web_main_py_yi_import_etmez():
    """run_web -> web_server zinciri Tkinter main.py'ye gitmez; gitseydi
    nofollow bayragi olmadan tum tkinter yigini pakete girerdi."""
    for ad in ("run_web.py", "orchestrator/web_server.py", "orchestrator/game_engine.py",
               "orchestrator/llm_bridge.py", "orchestrator/word_llm.py"):
        metin = (KOK / ad).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import main\b|from main\b)", metin, re.M), ad
    assert "--nofollow-import-to=tkinter" in _komut()
    assert "--nofollow-import-to=main" in _komut()


def test_giris_run_web_ve_cikti_Aican_exe():
    komut = _komut()
    assert komut[-1].replace("\\", "/").endswith("/run_web.py")
    assert f"--output-filename={surum.URUN_ADI}.exe" in komut
    assert build.EXE_ADI == "Aican.exe"
    assert build.DIST_ADI == "run_web.dist"


def test_standalone_onefile_DEGIL():
    komut = _komut()
    assert "--standalone" in komut
    assert "--onefile" not in komut


@pytest.mark.parametrize("modul", ["lisans", "lisans_bicim", "lisans_durum",
                                   "lisans_ekrani", "parmak_izi", "web_paket",
                                   "surum", "cryptography", "web_server"])
def test_tembel_import_edilen_moduller_acikca_eklenir(modul):
    assert f"--include-module={modul}" in _komut()


def test_webview_HIC_elle_verilmez():
    """webview'i elle eklemek Nuitka'nin pywebview eklentisiyle catisir.

    Nuitka 4.2.1 + pywebview 5.4: --include-module=webview de
    "Conflict between user and plugin decision for module
    'webview.platforms.android'" ile derlemeyi durdurdu (2026-09-11 G0 spike).
    Eklenti arka ucu kendi secer; tembel import statik analizde izlenir.
    """
    komut = _komut()
    assert "--include-package=webview" not in komut
    assert "--include-module=webview" not in komut


def test_cryptography_PAKET_olarak_verilmez():
    """cryptography icin tum paket gerekmez, kullanilan alt moduller acikca."""
    komut = _komut()
    assert "--include-package=cryptography" not in komut
    assert "--include-module=cryptography.hazmat.primitives.ciphers.aead" in komut
    assert "--include-module=cryptography.hazmat.primitives.asymmetric.ed25519" in komut


@pytest.mark.parametrize("paket", ["faster_whisper", "ctranslate2", "onnxruntime", "nvidia"])
def test_ses_hatti_paket_verisi_girer(paket):
    assert f"--include-package-data={paket}" in _komut()


@pytest.mark.parametrize("paket", ["nvidia", "noisereduce", "edge_tts", "piper", "flask"])
def test_ses_hatti_paketleri_girer(paket):
    assert f"--include-package={paket}" in _komut()


def test_lisans_URETIM_modulleri_komutta_YOK():
    """Ozel anahtar EXE'ye girseydi her kopya lisans uretebilirdi."""
    for p in _komut():
        assert "lisans_uret" not in p and "imza_deposu" not in p, p


# --------------------------------------------------------------------------- #
# Konsol modu ve ikon
# --------------------------------------------------------------------------- #

def test_konsol_modu_hide_varsayilan_force_secenek():
    """KimyaLab 50275baa: attach kisayoldan acilinca EXE'yi sessizce oldurur,
    disable logging'i stderr'siz birakir; hide ikisini de cozer."""
    assert "--windows-console-mode=hide" in build.komutu_olustur(KOK / "build")
    assert "--windows-console-mode=force" in build.komutu_olustur(KOK / "build", konsol=True)
    assert not any(p.startswith("--windows-console-mode=attach") for p in _komut())


def test_ikon_yoksa_bayrak_yok_varsa_var():
    assert not any(p.startswith("--windows-icon-from-ico") for p in _komut())
    k = build.komutu_olustur(KOK / "build", ico=Path("x.ico"))
    assert any(p.startswith("--windows-icon-from-ico=") for p in k)


# --------------------------------------------------------------------------- #
# Surum damgasi
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bayrak", ["--company-name", "--product-name",
                                    "--product-version", "--file-version",
                                    "--file-description"])
def test_exe_damgasi_bayraklari_var(bayrak):
    assert any(p.startswith(bayrak + "=") for p in _komut()), bayrak


def test_damga_degerleri_surum_modulunden():
    komut = _komut()
    assert f"--product-version={surum.SURUM}" in komut
    assert f"--file-version={surum.DOSYA_SURUMU}" in komut
    assert f"--company-name={surum.SIRKET}" in komut
    assert f"--product-name={surum.URUN_ADI}" in komut
    assert f"--file-description={surum.ACIKLAMA}" in komut


def test_surum_bicimi():
    assert re.fullmatch(r"\d+\.\d+\.\d+", surum.SURUM), surum.SURUM
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", surum.DOSYA_SURUMU)
    assert surum.DOSYA_SURUMU.startswith(surum.SURUM + ".")
    assert surum.URUN_ADI == "Aican"
    assert surum.SIRKET == "Luden Studio"
    assert surum.SURUM in surum.KURUCU_ADI
    assert surum.KURUCU_ADI.startswith(surum.URUN_ADI)
    assert surum.ACIKLAMA.startswith(surum.URUN_ADI)


def test_stdout_utf8_yeniden_yapilandirilir():
    """cp1254 konsolda Nuitka ciktisi UnicodeEncodeError ile build'i
    durduruyordu (KimyaLab'da olculdu)."""
    assert "reconfigure" in inspect.getsource(build.main)


def test_derle_PYTHONPATH_ile_orchestrator_verir():
    """Nuitka run_web.py'nin sys.path.insert'ini calistirmaz; orchestrator/
    PYTHONPATH'e konmazsa `import web_server` derlemede bulunamaz."""
    assert "PYTHONPATH" in inspect.getsource(build.derle)


# --------------------------------------------------------------------------- #
# Icerik anahtari depodan OKUNUR, uretilmez
# --------------------------------------------------------------------------- #

def _depo(tmp_path, paket_no=None, anahtar=b"q" * 32) -> Path:
    depo = tmp_path / "depo"
    (depo / "urunler" / "aican").mkdir(parents=True)
    (depo / "urunler" / "aican" / "icerik.key").write_text(json.dumps(
        {"paket_no": lisans.PAKET_NO if paket_no is None else paket_no,
         "anahtar": base64.b64encode(anahtar).decode()}), encoding="utf-8")
    return depo


def test_icerik_anahtari_depodan_okunur(tmp_path, monkeypatch):
    monkeypatch.setenv("LUDEN_LISANS", str(_depo(tmp_path)))
    assert build.icerik_anahtarini_oku() == (lisans.PAKET_NO, b"q" * 32)


def test_icerik_anahtari_yoksa_build_DURUR(tmp_path, monkeypatch):
    monkeypatch.setenv("LUDEN_LISANS", str(tmp_path))
    with pytest.raises(SystemExit, match="icerik anahtari yok"):
        build.icerik_anahtarini_oku()


def test_icerik_anahtari_HOME_altinda_da_aranir(tmp_path, monkeypatch):
    monkeypatch.delenv("LUDEN_LISANS", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(SystemExit, match=r"\.luden-lisans"):
        build.icerik_anahtarini_oku()


def test_paket_no_uyusmazsa_build_DURUR(tmp_path, monkeypatch):
    monkeypatch.setenv("LUDEN_LISANS", str(_depo(tmp_path, paket_no=lisans.PAKET_NO + 1)))
    with pytest.raises(SystemExit, match="paket_no uyusmuyor"):
        build.icerik_anahtarini_oku()


def test_icerik_anahtari_URETILMEZ():
    kaynak = inspect.getsource(build.icerik_anahtarini_oku)
    assert "token_bytes" not in kaynak and "urandom" not in kaynak


# --------------------------------------------------------------------------- #
# Tohum config: API anahtari doluysa DUR
# --------------------------------------------------------------------------- #

def test_tohum_config_dolu_api_anahtari_build_DURDURUR(tmp_path):
    yol = tmp_path / "config.json"
    yol.write_text(json.dumps({"tts_elevenlabs_api_key": "sk-gizli", "web_port": 1}),
                   encoding="utf-8")
    with pytest.raises(SystemExit, match="tts_elevenlabs_api_key"):
        build.tohum_config_kontrol(yol)


def test_tohum_config_bos_anahtar_gecer(tmp_path):
    yol = tmp_path / "config.json"
    yol.write_text(json.dumps({"tts_elevenlabs_api_key": "", "web_port": 1}),
                   encoding="utf-8")
    assert build.tohum_config_kontrol(yol)["web_port"] == 1


def test_depodaki_tohum_config_temiz():
    """orchestrator/config.json gercekten gizli alan tasimiyor (commit kilidi)."""
    build.tohum_config_kontrol()


# --------------------------------------------------------------------------- #
# Tohum normalizasyonu: dist/config.json musteri ilk acilisina uygun
# --------------------------------------------------------------------------- #

def test_tohum_hazirla_test_mode_KAPALI_tts_edge(tmp_path):
    """Sergi makinesinin config'i test_mode=true / elevenlabs tasiyabilir;
    kalici lisansli musteri ilk acilista tam urun + anahtarsiz TTS gormeli."""
    kaynak = tmp_path / "config.json"
    kaynak.write_text(json.dumps({
        "test_mode": True, "tts_engine": "elevenlabs",
        "tts_elevenlabs_api_key": "", "web_port": 1, "ollama_model": "x",
    }), encoding="utf-8")
    hedef = tmp_path / "dist" / "config.json"
    out = build.tohum_hazirla(kaynak, hedef)
    assert out == hedef and hedef.is_file()
    cfg = json.loads(hedef.read_text(encoding="utf-8"))
    assert cfg["test_mode"] is False
    assert cfg["tts_engine"] == "edge"
    # Diger alanlar dokunulmadan gecer.
    assert cfg["web_port"] == 1 and cfg["ollama_model"] == "x"
    # Kaynak dosya DEGISMEZ (sergi makinesinin ayarlari).
    assert json.loads(kaynak.read_text(encoding="utf-8"))["test_mode"] is True


def test_tohum_hazirla_dolu_anahtarda_DURUR(tmp_path):
    kaynak = tmp_path / "config.json"
    kaynak.write_text(json.dumps({"tts_elevenlabs_api_key": "sk-x"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="tts_elevenlabs_api_key"):
        build.tohum_hazirla(kaynak, tmp_path / "dist" / "config.json")
    assert not (tmp_path / "dist" / "config.json").exists()


def test_main_tohum_hazirla_komuttan_ONCE():
    """dist/config.json komut uretilmeden once yazilmis olmali."""
    import inspect
    src = inspect.getsource(build.main)
    assert 0 < src.index("tohum_hazirla(") < src.index("komutu_olustur(")


# --------------------------------------------------------------------------- #
# Obfuscation
# --------------------------------------------------------------------------- #

def test_obfuscator_muhafazakar_ayarlar():
    k = build.obfuscator_komutu(Path("a.js"), Path("b.js"))
    assert k[k.index("--rename-globals") + 1] == "false"
    assert k[k.index("--control-flow-flattening") + 1] == "false"


def test_web_hazirla_obfuscate_yok_gercek_paket_uretir(tmp_path, monkeypatch):
    """--obfuscate-yok: npx'siz makinede de web.pak cikar; icinde web/ + ai/
    var, assets yok, web-hazir/ geride kalmaz."""
    import web_paket
    monkeypatch.setenv("LUDEN_LISANS", str(_depo(tmp_path)))
    monkeypatch.setattr(build, "KOK", tmp_path / "proje")
    kok = tmp_path / "proje"
    (kok / "web").mkdir(parents=True)
    (kok / "web" / "app.js").write_text("var a=1;", encoding="utf-8")
    (kok / "ai").mkdir()
    (kok / "ai" / "gestures.json").write_text("{}", encoding="utf-8")
    (kok / "assets").mkdir()
    (kok / "assets" / "x.png").write_bytes(b"png")

    pak = build.web_hazirla(obfuscate=False)

    assert pak == kok / "dist" / "web.pak"
    assert not (kok / "dist" / "web-hazir").exists()
    assert web_paket.paket_no_oku(pak.read_bytes()) == lisans.PAKET_NO
    d = web_paket.coz(pak.read_bytes(), b"q" * 32)
    assert d == {"web/app.js": b"var a=1;", "ai/gestures.json": b"{}"}


def test_web_hazirla_npx_yoksa_obfuscate_ile_DURUR(tmp_path, monkeypatch):
    monkeypatch.setattr(build.shutil, "which", lambda ad: None)
    monkeypatch.setattr(build, "KOK", tmp_path / "proje")
    (tmp_path / "proje" / "web").mkdir(parents=True)
    (tmp_path / "proje" / "ai").mkdir()
    with pytest.raises(SystemExit, match="npx"):
        build.web_hazirla(obfuscate=True)


# --------------------------------------------------------------------------- #
# verify_dist / cuda_dll_tamamla
# --------------------------------------------------------------------------- #

def _sahte_dist(tmp_path: Path) -> Path:
    d = tmp_path / "run_web.dist"
    (d / "lisans_web").mkdir(parents=True)
    (d / "lisans_web" / "index.html").write_text("x", encoding="utf-8")
    (d / "assets" / "emojis").mkdir(parents=True)
    (d / "Aican.exe").write_bytes(b"MZ")
    (d / "web.pak").write_bytes(b"AIPAK1\n")
    (d / "config.json").write_text('{"tts_elevenlabs_api_key": ""}', encoding="utf-8")
    gomulu = d / build.WHISPER_HEDEF / build._tohum_whisper_boyutu()
    gomulu.mkdir(parents=True)
    (gomulu / "model.bin").write_bytes(b"ct2")
    sesler = d / build.PIPER_HEDEF
    sesler.mkdir(parents=True)
    (sesler / "tr_TR-dfki-medium.onnx").write_bytes(b"onnx")
    return d


def test_verify_dist_tam_paket(tmp_path):
    assert build.verify_dist(_sahte_dist(tmp_path))


# Whisper modeli ve Piper sesi de ZORUNLU. Whisper: sergide ses TEK giris
# aygiti, model yoksa EXE ilk acilista HF'den indirmeye calisir (G0 spike:
# ~12 dk mikrofon olu), internetsizse hic calismaz. Piper: birincil motor
# edge CEVRIMICI, yedek ses pakette yoksa ag kesilince sergi sessiz kalir.
@pytest.mark.parametrize("eksik", [
    "web.pak", "config.json", "Aican.exe",
    f"{build.WHISPER_HEDEF}/{build._tohum_whisper_boyutu()}/model.bin",
    f"{build.PIPER_HEDEF}/tr_TR-dfki-medium.onnx",
])
def test_verify_dist_eksik_dosya_RED(tmp_path, eksik):
    d = _sahte_dist(tmp_path)
    (d / eksik).unlink()
    assert not build.verify_dist(d)


@pytest.mark.parametrize("ham", ["web", "ai"])
def test_verify_dist_ham_kaynak_varsa_RED(tmp_path, ham):
    d = _sahte_dist(tmp_path)
    (d / ham).mkdir()
    (d / ham / "x").write_text("x", encoding="utf-8")
    assert not build.verify_dist(d)


def test_cuda_dll_tamamla_site_packages_tan_kopyalar(tmp_path):
    site = tmp_path / "site"
    (site / "nvidia" / "cublas" / "bin").mkdir(parents=True)
    (site / "nvidia" / "cublas" / "bin" / "cublas64_12.dll").write_bytes(b"x")
    (site / "nvidia" / "cudnn" / "bin").mkdir(parents=True)
    (site / "nvidia" / "cudnn" / "bin" / "cudnn64_9.dll").write_bytes(b"y")
    dist = tmp_path / "dist"
    (dist / "nvidia" / "cudnn" / "bin").mkdir(parents=True)
    (dist / "nvidia" / "cudnn" / "bin" / "cudnn64_9.dll").write_bytes(b"eski")

    assert build.cuda_dll_tamamla(dist, site=site) == 1
    assert (dist / "nvidia" / "cublas" / "bin" / "cublas64_12.dll").read_bytes() == b"x"
    assert (dist / "nvidia" / "cudnn" / "bin" / "cudnn64_9.dll").read_bytes() == b"eski"
    assert build.cuda_dll_tamamla(dist, site=site) == 0


# --------------------------------------------------------------------------- #
# _add_cuda_dll_dirs: frozen'da dist/nvidia, kaynakta site-packages
# --------------------------------------------------------------------------- #

def test_cuda_dll_frozen_da_resource_root_nvidia(tmp_path, monkeypatch):
    kok = tmp_path / "dist"
    cublas = kok / "nvidia" / "cublas" / "bin"
    cublas.mkdir(parents=True)
    cudnn = kok / "nvidia" / "cudnn" / "bin"
    cudnn.mkdir(parents=True)
    (kok / "nvidia" / "bos").mkdir()          # bin'siz: alinmaz
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(paths, "resource_root", lambda: str(kok))
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("PATH", "ESKI")
    eklenen = []
    monkeypatch.setattr(os, "add_dll_directory", lambda p: eklenen.append(p), raising=False)

    web_server._add_cuda_dll_dirs()

    assert eklenen == [str(cublas), str(cudnn)]
    assert os.environ["PATH"].split(os.pathsep)[:2] == [str(cublas), str(cudnn)]
    assert os.environ["PATH"].endswith("ESKI")


def test_cuda_dll_frozen_da_site_packages_e_BAKMAZ(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(paths, "resource_root", lambda: str(tmp_path))
    kokler = web_server._cuda_dll_kokleri()
    assert kokler == [tmp_path / "nvidia"]
    assert not any("site-packages" in str(k) for k in kokler)


def test_cuda_dll_kaynakta_site_packages(monkeypatch):
    monkeypatch.setattr(paths, "FROZEN", False)
    import sysconfig
    kokler = web_server._cuda_dll_kokleri()
    assert Path(sysconfig.get_paths()["purelib"]) / "nvidia" in kokler
    assert all(k.name == "nvidia" for k in kokler)


def test_tohum_tts_motoru_ve_sesi_BIRLIKTE_zorlanir():
    """Motor edge'e cevrilirken ses de gecerli bir edge sesi olmali.

    Gelistirme config'i elevenlabs + ElevenLabs ses kimligi tasir. Yalniz
    motoru zorlamak edge'e gecersiz bir ses adi birakiyordu; edge-tts
    "Invalid voice" ile reddedince sergi tamamen sessiz kaliyordu — ustelik
    ad kurulusta dogrulanmadigi icin log "TTS hazir" diyordu (2026-09-11 G0).
    """
    assert build.TOHUM_ZORLA["tts_engine"] == "edge"
    ses = build.TOHUM_ZORLA["tts_voice"]
    assert ses.startswith("tr-TR-") and ses.endswith("Neural"), (
        f"edge sesi 'tr-TR-...Neural' bicimindedir, bulunan: {ses!r}")


def test_tohum_whisper_boyutu_config_ten_okunur():
    """Gomulecek model adi tohum config'den gelir (web_server ile ayni kaynak)."""
    import json as _json
    cfg = _json.loads(build.TOHUM_CONFIG.read_text(encoding="utf-8-sig"))
    assert build._tohum_whisper_boyutu() == cfg["whisper_model_size"]
