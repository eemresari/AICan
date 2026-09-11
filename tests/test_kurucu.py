r"""Kurucu paketi kilitleri (plan G7, standalone dist).

KimyaLab'da kural "yalniz EXE girer"di (onefile). Aican standalone: EXE
yaninda yuzlerce DLL/.pyd + CUDA var, `run_web.dist\*` recursesubdirs ile
girmek ZORUNDA. Kural su hale gelir: ISCC'den ONCE dist taranir; aktivasyon,
anahtar dosyasi, lisans listesi, log, tarayici profili, ham web/ ai/, Tkinter
main.py ya da API anahtari dolu config.json bulunursa build durur. Veri koku
frozen'da %LOCALAPPDATA% oldugu icin dist normalde temizdir — bu tarama
kazaya karsi. ISCC/ZIP/SHA akisi subprocess.call monkeypatch'iyle, gercek
Inno Setup olmadan dogrulanir.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import zipfile
from pathlib import Path

import pytest

import build
import surum

KOK = Path(__file__).resolve().parent.parent
ISS = KOK / "installer" / "Aican.iss"

# Kardes urunlerin GUID'leri — kopyada kalmis olmasin.
KIMYALAB_GUID = "1DC99EBF-CEA1-46E6-81BF-ECB8265A0FF6"
SPRAYTARIH_GUID = "D57F7590-27BB-4E79-A02D-54B9FE7DAFF8"


def _iss_metni() -> str:
    return ISS.read_text(encoding="utf-8")


def _source_satirlari() -> list:
    return [s.strip() for s in _iss_metni().splitlines()
            if s.strip().lower().startswith("source:")]


# --------------------------------------------------------------------------- #
# .iss
# --------------------------------------------------------------------------- #

def test_iss_dosyasi_var():
    assert ISS.exists()
    assert build.ISS_DOSYASI == ISS


def test_tek_kaynak_satiri_ve_run_web_dist():
    satirlar = _source_satirlari()
    assert len(satirlar) == 1, satirlar
    assert r"..\build\run_web.dist\*" in satirlar[0], satirlar[0]
    assert "recursesubdirs" in satirlar[0]
    assert "createallsubdirs" in satirlar[0]


def test_iss_GUID_yeni_ve_bicimi_dogru():
    """Kopyalanan .iss'te kardes GUID kalirsa iki oyun Windows'ta AYNI program
    sayilir: biri digerini kaldirir/ustune yazar."""
    metin = _iss_metni()
    assert KIMYALAB_GUID not in metin
    assert SPRAYTARIH_GUID not in metin
    m = re.search(r"^AppId=\{\{([0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12})\}$",
                  metin, re.M)
    assert m, "AppId={{UUID4 buyuk harf}} bekleniyor"
    kod = "\n".join(s for s in metin.splitlines() if not s.lstrip().startswith(";"))
    assert "KimyaLab" not in kod and "SprayTarih" not in kod


def test_iss_surumu_elle_yazmiyor():
    metin = _iss_metni()
    assert "AppVersion={#SURUM}" in metin
    assert "OutputBaseFilename={#KURUCU_ADI}" in metin
    setup_bolumu = metin.split("[Setup]", 1)[1].split("[", 1)[0]
    assert not re.search(r"=\s*\d+\.\d+\.\d+", setup_bolumu), setup_bolumu


def test_iss_define_lari_disaridan_alir():
    metin = _iss_metni()
    for ad in ("SURUM", "URUN", "KURUCU_ADI"):
        assert f"#ifndef {ad}" in metin, ad
    assert "{#URUN}.exe" in metin
    assert "Turkish.isl" in metin


def test_iss_kisayol_Aican_exe_ve_LOCALAPPDATA_korunur():
    metin = _iss_metni()
    assert 'Filename: "{app}\\{#URUN}.exe"' in metin
    # Aktivasyon veri kokunde; kaldirmada silinmez: [UninstallDelete] YOK.
    assert "[UninstallDelete]" not in metin
    assert "LOCALAPPDATA" in metin and "aktivasyon" in metin.lower()


# --------------------------------------------------------------------------- #
# kurucu_uret akisi
# --------------------------------------------------------------------------- #

def _temiz_dist(tmp_path: Path) -> Path:
    d = tmp_path / "run_web.dist"
    d.mkdir()
    (d / "Aican.exe").write_bytes(b"MZ")
    (d / "web.pak").write_bytes(b"AIPAK1\n")
    (d / "python312.dll").write_bytes(b"x")
    (d / "config.json").write_text(json.dumps({"tts_elevenlabs_api_key": ""}),
                                   encoding="utf-8")
    (d / "lisans_web").mkdir()
    (d / "lisans_web" / "index.html").write_text("x", encoding="utf-8")
    (d / "nvidia" / "cublas" / "bin").mkdir(parents=True)
    (d / "nvidia" / "cublas" / "bin" / "cublas64_12.dll").write_bytes(b"x")
    return d


def test_kurucu_komutu_saf_ve_surum_gecirir():
    komut = build.kurucu_komutu(Path("ISCC.exe"))
    assert komut[0] == "ISCC.exe"
    assert f"/DSURUM={surum.SURUM}" in komut
    assert f"/DURUN={surum.URUN_ADI}" in komut
    assert f"/DKURUCU_ADI={surum.KURUCU_ADI}" in komut
    assert komut[-1].endswith("Aican.iss")


def test_kurucu_uret_ISCC_yi_subprocess_ile_cagirir(tmp_path, monkeypatch):
    yakalanan = []
    d = _temiz_dist(tmp_path)
    monkeypatch.setattr(build, "iscc_yolu", lambda: Path("ISCC.exe"))
    monkeypatch.setattr(build.subprocess, "call",
                        lambda komut, **k: yakalanan.append(komut) or 1)
    assert build.kurucu_uret(d) == 1        # ISCC 1 dondu -> aynen iletilir
    assert yakalanan == [build.kurucu_komutu(Path("ISCC.exe"))]


def test_exe_yoksa_ISCC_aranmaz(tmp_path, monkeypatch):
    d = tmp_path / "run_web.dist"
    d.mkdir()
    monkeypatch.setattr(build, "iscc_yolu",
                        lambda: pytest.fail("EXE yokken ISCC aranmamali"))
    assert build.kurucu_uret(d) == 1


def test_ISCC_yoksa_cikis_1(tmp_path, monkeypatch):
    d = _temiz_dist(tmp_path)
    monkeypatch.setattr(build, "iscc_yolu", lambda: None)
    monkeypatch.setattr(build.subprocess, "call",
                        lambda *a, **k: pytest.fail("ISCC yokken cagri olmamali"))
    assert build.kurucu_uret(d) == 1


# --------------------------------------------------------------------------- #
# dist taramasi — her yasak sinif
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("yasak", ["aktivasyon.dat", "lisanslar.json",
                                   "ozel.key", "icerik.KEY", "main.py"])
def test_dist_te_yasak_DOSYA_varsa_build_DURUR(tmp_path, monkeypatch, yasak):
    d = _temiz_dist(tmp_path)
    (d / yasak).write_text("x", encoding="utf-8")
    monkeypatch.setattr(build, "iscc_yolu",
                        lambda: pytest.fail("yasak dosya varken ISCC cagrilmamali"))
    assert build.kurucu_uret(d) == 1
    assert build.dist_yasaklari(d)


@pytest.mark.parametrize("yasak", ["logs", ".tarayici_profili", "web", "ai"])
def test_dist_te_yasak_KLASOR_varsa_build_DURUR(tmp_path, monkeypatch, yasak):
    d = _temiz_dist(tmp_path)
    (d / yasak).mkdir()
    (d / yasak / "x").write_text("x", encoding="utf-8")
    monkeypatch.setattr(build, "iscc_yolu",
                        lambda: pytest.fail("yasak klasor varken ISCC cagrilmamali"))
    assert build.kurucu_uret(d) == 1


def test_dist_te_API_anahtari_dolu_config_varsa_build_DURUR(tmp_path, monkeypatch):
    d = _temiz_dist(tmp_path)
    (d / "config.json").write_text(json.dumps({"tts_elevenlabs_api_key": "sk-x"}),
                                   encoding="utf-8")
    monkeypatch.setattr(build, "iscc_yolu",
                        lambda: pytest.fail("anahtarli config varken ISCC cagrilmamali"))
    assert build.kurucu_uret(d) == 1
    assert any("config.json" in y for y in build.dist_yasaklari(d))


def test_yasak_tarama_alt_klasorlere_de_bakar(tmp_path):
    d = _temiz_dist(tmp_path)
    (d / "orchestrator").mkdir()
    (d / "orchestrator" / "aktivasyon.dat").write_text("x", encoding="utf-8")
    (d / "orchestrator" / "logs").mkdir()
    bulunan = build.dist_yasaklari(d)
    assert any(b.endswith("aktivasyon.dat") for b in bulunan)
    assert any(b.endswith("logs") for b in bulunan)


def test_kutuphane_alt_paketi_ai_web_YANLIS_ALARM_degil(tmp_path):
    """web/ ve ai/ yalniz dist KOKUNDE yasak; bir kutuphanenin alt paketi
    (ornegin some_lib/ai/) build'i durdurmamali."""
    d = _temiz_dist(tmp_path)
    (d / "some_lib" / "ai").mkdir(parents=True)
    (d / "some_lib" / "web").mkdir()
    assert build.dist_yasaklari(d) == []


def test_temiz_dist_yasak_uretmez(tmp_path):
    assert build.dist_yasaklari(_temiz_dist(tmp_path)) == []


# --------------------------------------------------------------------------- #
# ISCC bulma
# --------------------------------------------------------------------------- #

def test_ISCC_ortam_degiskeni_her_seyi_EZER(monkeypatch, tmp_path):
    sahte = tmp_path / "ISCC.exe"
    sahte.write_text("", encoding="utf-8")
    monkeypatch.setenv("ISCC", str(sahte))
    monkeypatch.setattr(build.shutil, "which",
                        lambda ad: pytest.fail("ISCC env varken PATH aranmamali"))
    assert build.iscc_yolu() == sahte


def test_ISCC_env_gecersizse_PATH_ve_adaylar(monkeypatch, tmp_path):
    monkeypatch.setenv("ISCC", str(tmp_path / "yok.exe"))
    monkeypatch.setattr(build.shutil, "which", lambda ad: None)
    aday = tmp_path / "Programs" / "Inno Setup 6" / "ISCC.exe"
    aday.parent.mkdir(parents=True)
    aday.write_text("", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pfx86"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    assert build.iscc_yolu() == aday


def test_aday_sirasi_LOCALAPPDATA_sonra_ProgramFiles(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Kullanici\AppData\Local")
    monkeypatch.setenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    adaylar = [a.as_posix().lower() for a in build.iscc_adaylari()]
    assert adaylar[0].endswith("appdata/local/programs/inno setup 6/iscc.exe")
    i_x86 = next(i for i, a in enumerate(adaylar)
                 if a.endswith("program files (x86)/inno setup 6/iscc.exe"))
    i_pf = next(i for i, a in enumerate(adaylar)
                if a.endswith("program files/inno setup 6/iscc.exe"))
    assert 0 < i_x86 < i_pf


def test_adaylarda_SURUCU_HARFI_hardcode_YOK():
    kaynak = inspect.getsource(build.iscc_adaylari)
    govde = kaynak.split('"""')[-1]
    assert "C:" not in govde, govde


# --------------------------------------------------------------------------- #
# ZIP + SHA-256
# --------------------------------------------------------------------------- #

def test_zip_kurucu_ve_KURULUM_txt_tasir_sha256_dogru(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "KOK", tmp_path)       # docs/KURULUM.md yok -> uyari
    (tmp_path / "dist").mkdir()
    setup = tmp_path / "dist" / f"{surum.KURUCU_ADI}.exe"
    setup.write_bytes(b"MZ kurucu")

    assert build.paketle_ve_ozetle(setup) == 0

    zip_yolu = setup.with_suffix(".zip")
    with zipfile.ZipFile(zip_yolu) as z:
        adlar = set(z.namelist())
        assert adlar == {setup.name, "KURULUM.txt"}
        metin = z.read("KURULUM.txt").decode("utf-8")
    assert surum.KURUCU_ADI in metin
    assert "docs/KURULUM.md" in metin
    assert "Daha fazla bilgi" in metin and "Yine de calistir" in metin

    sha_yolu = tmp_path / "dist" / f"{surum.KURUCU_ADI}.zip.sha256"
    ozet, ad = sha_yolu.read_text(encoding="utf-8").split()
    assert ozet == hashlib.sha256(zip_yolu.read_bytes()).hexdigest()
    assert ad == "*" + zip_yolu.name


def test_zip_KURULUM_md_varsa_onu_da_tasir(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "KOK", tmp_path)
    (tmp_path / "dist").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "KURULUM.md").write_text("# uzun kilavuz", encoding="utf-8")
    setup = tmp_path / "dist" / f"{surum.KURUCU_ADI}.exe"
    setup.write_bytes(b"MZ")
    build.paketle_ve_ozetle(setup)
    with zipfile.ZipFile(setup.with_suffix(".zip")) as z:
        assert set(z.namelist()) == {setup.name, "KURULUM.txt", "KURULUM.md"}


def test_kurucu_uret_ISCC_basarili_ama_cikti_yoksa_1(tmp_path, monkeypatch):
    d = _temiz_dist(tmp_path)
    monkeypatch.setattr(build, "KOK", tmp_path)
    monkeypatch.setattr(build, "iscc_yolu", lambda: Path("ISCC.exe"))
    monkeypatch.setattr(build.subprocess, "call", lambda komut, **k: 0)
    assert build.kurucu_uret(d) == 1


def test_kurucu_uret_ucdan_uca(tmp_path, monkeypatch):
    """ISCC sahte: cagrilinca dist/<KURUCU_ADI>.exe yazar; ZIP + SHA cikar."""
    d = _temiz_dist(tmp_path)
    monkeypatch.setattr(build, "KOK", tmp_path)
    (tmp_path / "dist").mkdir()
    monkeypatch.setattr(build, "iscc_yolu", lambda: Path("ISCC.exe"))

    def sahte_iscc(komut, **k):
        (tmp_path / "dist" / f"{surum.KURUCU_ADI}.exe").write_bytes(b"MZ")
        return 0
    monkeypatch.setattr(build.subprocess, "call", sahte_iscc)

    assert build.kurucu_uret(d) == 0
    assert (tmp_path / "dist" / f"{surum.KURUCU_ADI}.zip").exists()
    assert (tmp_path / "dist" / f"{surum.KURUCU_ADI}.zip.sha256").exists()


def test_main_kurucu_bayragi_dist_yolunu_kurar(monkeypatch):
    goruldu = []
    monkeypatch.setattr(build, "kurucu_uret", lambda d: goruldu.append(Path(d)) or 0)
    assert build.main(["--kurucu"]) == 0
    assert goruldu == [KOK / "build" / "run_web.dist"]
