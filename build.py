#!/usr/bin/env python3
"""Aican'i standalone EXE'ye derler (Nuitka) ve kurucusunu uretir (Inno Setup).

    python build.py                  # dist/web.pak + build/run_web.dist/Aican.exe
    python build.py --check          # yalniz on kontroller (anahtar, tohum, npx)
    python build.py --obfuscate-yok  # JS obfuscation adimini atla
    python build.py --konsol         # konsol penceresi acik (hata ayiklama)
    python build.py --kurucu         # mevcut dist'ten Inno kurucusu + ZIP + SHA-256

LISANS HATTI (docs/plans/2026-09-11-lisans-ve-kurucu-entegrasyonu.md, sapma #5/#6)
------------------------------------------------------------------------------
`web/` ve `ai/` pakete HAM GIRMEZ: standalone dist'te EXE'nin yaninda sergi on
yuzu (JS/HTML), oyun veri tablolari ve sistem promptu okunabilir dururdu. Onun
yerine `web/` once `dist/web-hazir/`'a kopyalanip obfuscate edilir, `ai/` ile
birlikte Lisans Merkezi'nin icerik anahtariyla `dist/web.pak`'e sifrelenir ve
EXE'ye o girer. `web_server.main()` lisans kapisindan gecince paketi BELLEKTE
cozer (`_paketi_yukle`) ve bellekten servis eder. Ham giren: lisans ekrani
(`lisans_web/` — paket cozulmeden once gosterilmek zorunda), `assets/` (16 MB
emoji PNG; gorsel, kaynak degil) ve tohum `config.json`.

NEDEN NUITKA, PyInstaller DEGIL: PyInstaller EXE'si bir arsivdir, kaynak
dakikalar icinde geri cikar. Nuitka C'ye derler; decompile edilemez.

NEDEN --standalone, --onefile DEGIL: onefile her acilista gecici dizine acilir
(acilis uzar, antivirus yanlis pozitifi artar) ve derleme sonrasi native DLL
tamamlamasi (CUDA cublas/cudnn, ctranslate2) yapilamaz. "Tek dosya" hissi
kurucunun isi.

ISCC ve Nuitka cagrilari `subprocess` uzerinden yapilir ve komutlar saf
fonksiyonlarla uretilir (`komutu_olustur`, `kurucu_komutu`): tests/test_build.py
ve tests/test_kurucu.py gercek derleme yapmadan bunlari kilitler.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parent
ORCH = KOK / "orchestrator"
for _p in (str(KOK), str(ORCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import surum  # noqa: E402

EXE_ADI = f"{surum.URUN_ADI}.exe"
GIRIS = "run_web.py"
DIST_ADI = "run_web.dist"          # Nuitka standalone: <giris adi>.dist

# Icerik anahtarinin durdugu yer. Lisans Merkezi ile AYNI depo; anahtar orada
# uretilir, burada yalnizca OKUNUR.
DEPO_ENV = "LUDEN_LISANS"
DEPO_KLASORU = ".luden-lisans"

# Tohum config: orchestrator/config.json dist kokune config.json olarak girer
# ve ilk acilista %LOCALAPPDATA%\Aican\config.json'a kopyalanir. Sergi
# makinesinin gercek ayarlarini tasiyor olabilir; API anahtari doluysa build
# DURUR (her kurulum musterinin ElevenLabs kredisini yakardi).
TOHUM_CONFIG = ORCH / "config.json"
GIZLI_CONFIG_ALANLARI = ("tts_elevenlabs_api_key",)
# Dist'e yazilan tohumda ZORLANAN alanlar (kullanici karari 2026-09-11):
# sergi makinesinin config'i test_mode=true / elevenlabs tasiyabilir; kalici
# lisansli musteri ilk acilista tam urunu ve anahtarsiz (ucretsiz) TTS'i
# gormeli. Demo lisansta test_mode'u zaten web_server zorla acar.
TOHUM_ZORLA = {"test_mode": False, "tts_engine": "edge"}

# Kurucuya (dist\*) SIZMAMASI gereken adlar. Veri koku frozen'da
# %LOCALAPPDATA% oldugu icin normalde dist temizdir; bu tarama "biri
# AICAN_DATA_ROOT=dist ile test etti ve unuttu" kazasina karsi.
# Her yerde yasak (alt klasorler dahil):
DIST_YASAK = ("aktivasyon.dat", "lisanslar.json", "logs", ".tarayici_profili")
DIST_YASAK_UZANTI = (".key",)
# Yalniz dist KOKUNDE yasak: ham kaynak dizinleri ve Tkinter girisi. Kok disi
# aranmaz — bir kutuphanenin "ai/" ya da "web/" alt paketi yanlis alarm olurdu.
DIST_KOK_YASAK = ("web", "ai", "main.py")

# Obfuscator'in DOKUNMADIGI alt klasorler (web/ altinda su an yok; ileride
# vendor JS konursa buraya yazilir — ucuncu parti minify kodu yeniden
# obfuscate etmek kazanc getirmez, kirilma riski getirir).
OBFUSCATE_DISI = ("vendor",)

# Piper cevrimdisi TTS yedegi: orchestrator/tts/voices/*.onnx .gitignore'da
# (60 MB, README'deki komutla iner). Varsa dist'e tts/voices olarak girer;
# yoksa build DURMAZ ama EXE'de piper yedegi calismaz (edge/elevenlabs
# cevrimici motorlar kalir) — uyari basilir.
PIPER_SESLER = ORCH / "tts" / "voices"

# CUDA calisma kutuphaneleri (pip nvidia-cublas-cu12, nvidia-cudnn-cu12).
# ctranslate2 bunlari GEC yukler (ctypes/LoadLibrary), Nuitka import
# analizinde gormez. --include-package-data=nvidia denenir; yetmezse
# build sonrasi `cuda_dll_tamamla` site-packages'tan dist/nvidia/<pkg>/bin'e
# kopyalar. web_server._add_cuda_dll_dirs frozen'da tam o yola bakar.
CUDA_PAKETLERI = ("cublas", "cudnn")


# ---------------------------------------------------------------------------
# On kontroller
# ---------------------------------------------------------------------------

def _depo_koku() -> Path:
    ozel = os.environ.get(DEPO_ENV)
    return Path(ozel) if ozel else Path.home() / DEPO_KLASORU


def icerik_anahtarini_oku() -> tuple:
    """(paket_no, 32 bayt anahtar) — Lisans Merkezi'nin deposundan.

    ANAHTAR BURADA URETILMEZ: uretilseydi her yeni build dagitilmis TUM
    lisanslari cope atardi (eski lisanslarin tasidigi anahtar yeni paketi
    cozemezdi). Rotasyon isteniyorsa paket_no depoda artirilir.
    """
    import lisans

    yol = _depo_koku() / "urunler" / lisans.URUN / "icerik.key"
    if not yol.exists():
        raise SystemExit(
            f"[build] icerik anahtari yok: {yol}\n"
            "Lisans Merkezi'ni acip bu urun icin anahtar uretin "
            "(01-Projects/LisansMerkezi -> MERKEZ.bat).")
    veri = json.loads(yol.read_text(encoding="utf-8"))
    paket_no, anahtar = int(veri["paket_no"]), base64.b64decode(veri["anahtar"])
    if paket_no != lisans.PAKET_NO:
        raise SystemExit(
            f"[build] paket_no uyusmuyor: icerik.key={paket_no}, "
            f"lisans.PAKET_NO={lisans.PAKET_NO}.\n"
            "EXE web.pak'i acmadan once bu ikisini karsilastirir; farkli "
            "olurlarsa her kurulum 'paket surumu uyusmuyor' der. lisans.py'yi "
            "depodaki numaraya cekin (ya da Merkez'de anahtari dondurun).")
    return paket_no, anahtar


def tohum_config_kontrol(yol: Path = TOHUM_CONFIG) -> dict:
    """Tohum config.json'u oku; gizli alan doluysa DUR. Sozlugu doner."""
    if not yol.is_file():
        raise SystemExit(f"[build] tohum config yok: {yol}")
    cfg = json.loads(yol.read_text(encoding="utf-8-sig"))
    dolu = [a for a in GIZLI_CONFIG_ALANLARI if str(cfg.get(a) or "").strip()]
    if dolu:
        raise SystemExit(
            f"[build] {yol.name} tohumunda gizli alan DOLU: {', '.join(dolu)}.\n"
            "Bu dosya EXE'nin yanina config.json olarak girer ve her kuruluma "
            "kopyalanir. Anahtari bosaltip (\"\") yeniden deneyin; sergi "
            "makinesinde anahtar %LOCALAPPDATA%\\Aican\\config.json'a elle girilir.")
    return cfg


def tohum_hazirla(kaynak: Path = TOHUM_CONFIG, hedef: Path = None) -> Path:
    """orchestrator/config.json -> dist/config.json: gizli alan kontrolu +
    TOHUM_ZORLA. Kaynak dosyaya dokunmaz; yazilan yolu doner."""
    hedef = Path(hedef) if hedef else KOK / "dist" / "config.json"
    cfg = tohum_config_kontrol(kaynak)
    cfg.update(TOHUM_ZORLA)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    print(f"[build] tohum config -> {hedef} ({', '.join(f'{k}={v}' for k, v in TOHUM_ZORLA.items())})")
    return hedef


def _ikon_yolu():
    """assets/ altinda .ico varsa EXE ikonu; yoksa None (Nuitka varsayilani)."""
    for aday in (KOK / "assets" / "aican.ico", KOK / "assets" / "icon.ico"):
        if aday.is_file():
            return aday
    return None


# ---------------------------------------------------------------------------
# Icerik paketi (web -> obfuscate -> + ai -> web.pak)
# ---------------------------------------------------------------------------

def obfuscator_komutu(girdi: Path, cikti: Path) -> list:
    """javascript-obfuscator cagrisi — muhafazakar ayarlar (SprayTarih ile ayni).

    rename-globals ACIK olsaydi dosyalar arasi paylasilan global adlar
    (app.js <-> led-panel.js, inline onclick'ler) yeniden adlandirilir ve
    sergi sessizce bos ekran acardi. control-flow-flattening LED cizim
    dongusunu yavaslatir; bedeli kazancindan buyuk.
    """
    npx = shutil.which("npx") or "npx"
    return [npx, "--yes", "javascript-obfuscator", str(girdi),
            "--output", str(cikti),
            "--compact", "true",
            "--rename-globals", "false",
            "--control-flow-flattening", "false",
            "--string-array", "true",
            "--string-array-encoding", "base64"]


def web_hazirla(obfuscate: bool = True) -> Path:
    """web/ -> dist/web-hazir/ (obfuscate) ; + ai/ -> dist/web.pak.

    Donen deger dist/web.pak. web-hazir/ paketlendikten sonra silinir —
    dist/ altinda okunabilir kopya kalmasin.
    """
    import web_paket

    dist = KOK / "dist"
    hazir = dist / "web-hazir"
    if hazir.exists():
        shutil.rmtree(hazir)
    dist.mkdir(parents=True, exist_ok=True)
    shutil.copytree(KOK / "web", hazir)

    if not obfuscate:
        print("[build] obfuscation ATLANDI (--obfuscate-yok)")
    else:
        if shutil.which("npx") is None:
            raise SystemExit(
                "[build] npx bulunamadi: JS obfuscation icin Node.js gerekir "
                "(winget install OpenJS.NodeJS.LTS). Gecici cozum: --obfuscate-yok "
                "(web.pak yine sifrelenir ama JS icinde okunabilir kalir).")
        sayac = 0
        for js in sorted(hazir.rglob("*.js")):
            if any(d in js.relative_to(hazir).parts for d in OBFUSCATE_DISI):
                continue
            sonuc = subprocess.run(obfuscator_komutu(js, js), cwd=KOK,
                                   capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
            if sonuc.returncode != 0:
                raise SystemExit(
                    f"[build] obfuscation basarisiz ({js.name}):\n"
                    f"{sonuc.stderr.strip()}\n"
                    "node/npx kurulu mu? Gecici cozum: --obfuscate-yok")
            sayac += 1
        print(f"[build] {sayac} JS dosyasi obfuscate edildi")

    paket_no, anahtar = icerik_anahtarini_oku()
    pak = dist / "web.pak"
    pak.write_bytes(web_paket.paketle(KOK, anahtar, paket_no, web_kok=hazir))
    shutil.rmtree(hazir)
    print(f"[build] web paketi: {pak.name} "
          f"({pak.stat().st_size / 1024:.0f} KB, sifreli, paket_no={paket_no})")
    return pak


# ---------------------------------------------------------------------------
# Nuitka
# ---------------------------------------------------------------------------

def komutu_olustur(cikti_dizini=None, konsol: bool = False, ico=None) -> list:
    """Nuitka komut satiri — SAF: dosya sistemine dokunmaz, liste doner.

    `ico` None ise assets'e bakilmaz (testler deterministik kalsin); main()
    _ikon_yolu() sonucunu gecirir.
    """
    cikti_dizini = Path(cikti_dizini) if cikti_dizini else KOK / "build"
    dist = KOK / "dist"
    cmd = [
        sys.executable, "-m", "nuitka",
        "--assume-yes-for-downloads",
        "--standalone",
        # --- Windows kaynak damgasi ---
        # Damgasiz EXE'nin "Ozellikler > Ayrintilar" sekmesi bombostur;
        # SmartScreen'de "Daha fazla bilgi"ye tiklayan kullanici yayinci adi
        # bulamayinca dosyayi silmeye egilimli. Sertifika yok; tek kimlik
        # isareti bu. Degerler surum.py'den gelir — tek kaynak.
        f"--company-name={surum.SIRKET}",
        f"--product-name={surum.URUN_ADI}",
        f"--product-version={surum.SURUM}",
        f"--file-version={surum.DOSYA_SURUMU}",
        f"--file-description={surum.ACIKLAMA}",
        f"--copyright={surum.SIRKET}",
        # --- veri: ham web/ ve ai/ YOK (bkz. modul docstring'i) ---
        f"--include-data-files={dist / 'web.pak'}=web.pak",
        f"--include-data-dir={KOK / 'lisans_web'}=lisans_web",
        f"--include-data-dir={KOK / 'assets'}=assets",
        # Tohum config: tohum_hazirla() ile normalize edilmis dist/config.json
        # (ham orchestrator/config.json DEGIL) -> dist kokune config.json
        # (paths.ensure_seeded kopyalar).
        f"--include-data-files={dist / 'config.json'}=config.json",
        # --- lisans katmani: web_server.main() icinde TEMBEL import ---
        # Acikca listele ki biri lazy import'u tasidiginda EXE'de
        # "No module named lisans" cikmasin. lisans_bicim Merkez kopyasidir.
        "--include-module=lisans",
        "--include-module=lisans_bicim",
        "--include-module=lisans_durum",
        "--include-module=lisans_ekrani",
        "--include-module=parmak_izi",
        "--include-module=web_paket",
        "--include-module=surum",
        # pywebview: lisans_ekrani icinde tembel `import webview`. webview
        # HIC elle verilmez — ne --include-package ne --include-module.
        # Nuitka'nin pywebview eklentisi platform arka ucunu kendisi secer;
        # elle eklemek onunla catisir: Nuitka 4.2.1 + pywebview 5.4'te
        # --include-module=webview de "FATAL: pywebview: Conflict between user
        # and plugin decision for module 'webview.platforms.android'" verip
        # derlemeyi 80. saniyede durdurdu (2026-09-11, G0 spike'inda olculdu;
        # KimyaLab'da ayni catisma --include-package ile gorulmustu).
        # Tembel import'u Nuitka statik analizde zaten izler.
        # cryptography: lisans_bicim (ed25519) ve web_paket (AESGCM) fonksiyon
        # icinde import eder. Kullanilan alt moduller acikca; tum paket degil
        # (--include-package=cryptography tum arka uclari surukler, gerekmez).
        "--include-module=cryptography",
        "--include-module=cryptography.hazmat.primitives.serialization",
        "--include-module=cryptography.hazmat.primitives.asymmetric.ed25519",
        "--include-module=cryptography.hazmat.primitives.ciphers.aead",
        # --- orchestrator/ modulleri: run_web.py sys.path'e ekleyip import
        # eder; Nuitka bunu calistirmaz, PYTHONPATH ile bulur (bkz. derle()).
        # TTS motorlari _load_tts_async icinde tembel import.
        "--include-module=web_server",
        "--include-module=tts.cache",
        "--include-module=tts.engine_base",
        "--include-module=tts.engine_edge",
        "--include-module=tts.engine_piper",
        "--include-module=tts.engine_elevenlabs",
        "--include-module=tts.emotion_voice_map",
        # --- ses hatti: native ikili / veri tasiyan paketler ---
        "--include-package-data=faster_whisper",
        "--include-package-data=ctranslate2",
        "--include-package-data=onnxruntime",
        "--include-package=nvidia",
        "--include-package-data=nvidia",
        "--include-package-data=imageio_ffmpeg",     # ffmpeg.exe (perde kaydirma)
        "--include-package=noisereduce",
        "--include-package=edge_tts",
        "--include-package=piper",
        "--include-package=flask",
        # --- build DISI (sapma #8): Tkinter prototipi ve gelistirme araclari ---
        # run_web.py -> web_server bunlari import ETMEZ (teyit edildi); yine de
        # kilitli: biri yanlislikla import ederse tkinter yigini pakete girmesin.
        "--nofollow-import-to=main",
        "--nofollow-import-to=matrix_sim",
        "--nofollow-import-to=gesture_engine",
        "--nofollow-import-to=build_model",
        "--nofollow-import-to=test_runner",
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=pytest",
    ]

    # KONSOL: "hide" — cift tiklayinca konsol acilir ama ANINDA gizlenir
    # (urun gibi durur); terminalden calistirilinca mevcut konsolu kullanir.
    # KimyaLab'in 2026-09-11 karariyla ayni (50275baa):
    #   "attach" OLMAZ: Explorer/kisayoldan acilinca ebeveynde konsol yoktur,
    #   AttachConsole basarisiz olur, stdin/stdout/stderr ucu birden gecersiz
    #   kalir -> EXE 1 sn'de rc=1 ile sessizce olur, hata kutusu bile cikmaz.
    #   "disable" OLMAZ: web_server logging'i stderr'e yazar; stdout/stderr
    #   None iken StreamHandler ilk logda patlar. "hide" akislari her zaman
    #   gecerli tutar; Flask/Whisper loglari terminalden acilinca gorunur.
    cmd.append("--windows-console-mode=" + ("force" if konsol else "hide"))

    if ico:
        cmd.append(f"--windows-icon-from-ico={ico}")

    # Piper ses modeli (varsa). engine_piper `__file__/../voices` okur; frozen'da
    # bu dist/tts/voices'tir.
    if PIPER_SESLER.is_dir() and any(PIPER_SESLER.glob("*.onnx")):
        cmd.append(f"--include-data-dir={PIPER_SESLER}=tts/voices")

    cmd += [
        f"--output-filename={EXE_ADI}",
        f"--output-dir={cikti_dizini}",
        str(KOK / GIRIS),
    ]
    return cmd


def derle(cmd: list, gunluk: Path) -> int:
    """Nuitka'yi calistir; ciktiyi ekrana + gunluk dosyasina ak. Cikis kodu doner.

    PYTHONPATH: run_web.py calisma zamaninda orchestrator/'i sys.path'e ekler;
    Nuitka statik analiz yapar, bunu gormez. orchestrator/ (web_server, paths,
    tts.*) ve kok (lisans*, web_paket, surum) PYTHONPATH ile verilir.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ORCH), str(KOK)]
                                        + [p for p in [env.get("PYTHONPATH", "")] if p])
    gunluk.parent.mkdir(parents=True, exist_ok=True)
    basla = time.time()
    satirlar: list = []
    with subprocess.Popen(cmd, cwd=KOK, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True,
                          encoding="utf-8", errors="replace", bufsize=1) as sr:
        for satir in sr.stdout:
            try:
                print(satir, end="")
            except UnicodeEncodeError:
                print(satir.encode("ascii", "replace").decode("ascii"), end="")
            satirlar.append(satir)
        kod = sr.wait()
    gunluk.write_text("".join(satirlar), encoding="utf-8")
    print(f"\n[build] Nuitka bitti: cikis {kod}, {time.time() - basla:.0f} sn "
          f"(gunluk: {gunluk})")
    return kod


# ---------------------------------------------------------------------------
# Build sonrasi: CUDA DLL tamamlama + dogrulama
# ---------------------------------------------------------------------------

def _site_packages() -> str:
    import sysconfig
    return sysconfig.get_paths()["purelib"]


def cuda_dll_tamamla(dist_dir, site=None) -> int:
    """site-packages/nvidia/<pkg>/bin/*.dll -> dist/nvidia/<pkg>/bin (eksikse).

    Nuitka --include-package-data=nvidia namespace paketi her surumde ayni
    guvenilirlikte islemez; ctranslate2 cublas64_12.dll'i ILK transkripsiyonda
    LoadLibrary ile arar, yoksa "hazir" gorunen model cokertir. Kopyalanan
    dosya sayisi doner.
    """
    site = Path(site or _site_packages())
    kopya = 0
    for pkg in CUDA_PAKETLERI:
        kaynak = site / "nvidia" / pkg / "bin"
        if not kaynak.is_dir():
            continue
        hedef = Path(dist_dir) / "nvidia" / pkg / "bin"
        for dll in sorted(kaynak.glob("*.dll")):
            if (hedef / dll.name).is_file():
                continue
            hedef.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dll, hedef / dll.name)
            kopya += 1
    return kopya


def verify_dist(dist_dir) -> bool:
    """Paket gercekten calisabilir mi ve ham kaynak sizmis mi?"""
    dist_dir = Path(dist_dir)
    ok = True
    gerekli = [
        (EXE_ADI, "calistirilabilir"),
        ("web.pak", "sifreli icerik paketi"),
        (os.path.join("lisans_web", "index.html"), "lisans ekrani"),
        ("config.json", "tohum config"),
    ]
    for rel, ne in gerekli:
        if not (dist_dir / rel).is_file():
            print(f"[build] EKSIK ({ne}): {rel}")
            ok = False
    if not (dist_dir / "assets" / "emojis").is_dir():
        print("[build] EKSIK (emoji gorselleri): assets/emojis")
        ok = False
    for pkg in CUDA_PAKETLERI:
        b = dist_dir / "nvidia" / pkg / "bin"
        if not (b.is_dir() and any(b.glob("*.dll"))):
            print(f"[build] UYARI: nvidia/{pkg}/bin yok — CUDA Whisper EXE'de "
                  "calismaz (CPU'ya duser).")
    yasak = dist_yasaklari(dist_dir)
    if yasak:
        print("[build] dist'te HAM/gizli icerik var — web.pak anlamsiz. Dagitmayin:")
        for rel in yasak:
            print("        - " + rel)
        ok = False
    return ok


def _config_gizli_dolu(yol: Path) -> bool:
    try:
        cfg = json.loads(yol.read_text(encoding="utf-8-sig"))
    except Exception:      # noqa: BLE001 — okunamayan config yasak sayilmaz
        return False
    return any(str(cfg.get(a) or "").strip() for a in GIZLI_CONFIG_ALANLARI)


def dist_yasaklari(dist_dir) -> list:
    """Kurucuya girmemesi gereken dosya/klasorlerin dist icindeki listesi."""
    dist_dir = str(dist_dir)
    bulunan = []
    for ad in DIST_KOK_YASAK:
        if os.path.exists(os.path.join(dist_dir, ad)):
            bulunan.append(ad)
    for root, dirs, files in os.walk(dist_dir):
        for ad in list(dirs) + files:
            tam = os.path.join(root, ad)
            rel = os.path.relpath(tam, dist_dir)
            if ad in DIST_YASAK or ad.lower().endswith(DIST_YASAK_UZANTI):
                bulunan.append(rel)
            elif ad == "config.json" and _config_gizli_dolu(Path(tam)):
                bulunan.append(rel + " (gizli alan dolu)")
        # Yasak klasorun altina inmeye gerek yok; bir kez raporla.
        dirs[:] = [d for d in dirs if d not in DIST_YASAK]
    return bulunan


# ---------------------------------------------------------------------------
# Kurucu (Inno Setup)
# ---------------------------------------------------------------------------

ISS_DOSYASI = KOK / "installer" / "Aican.iss"
INNO_KLASORU = "Inno Setup 6"


def iscc_adaylari() -> list:
    r"""ISCC.exe'nin bulunabilecegi yerler, olasilik sirasiyla.

    OLCULDU (KimyaLab): `winget install JRSoftware.InnoSetup` derleyiciyi
    Program Files'a DEGIL, kullanici basina %LOCALAPPDATA%\Programs altina
    koyuyor. Yollar ortam degiskenlerinden turetilir — surucu harfi elle
    yazilmaz.
    """
    kokler = [os.environ.get("LOCALAPPDATA", ""),
              os.environ.get("ProgramFiles(x86)", ""),
              os.environ.get("ProgramFiles", "")]
    adaylar = []
    for kok in kokler:
        if not kok:
            continue
        adaylar.append(Path(kok) / "Programs" / INNO_KLASORU / "ISCC.exe")
        adaylar.append(Path(kok) / INNO_KLASORU / "ISCC.exe")
    return adaylar


def iscc_yolu():
    """ISCC.exe nerede? Once ISCC ortam degiskeni, sonra PATH, sonra adaylar."""
    ozel = os.environ.get("ISCC")
    if ozel and Path(ozel).exists():
        return Path(ozel)
    bulunan = shutil.which("ISCC")
    if bulunan:
        return Path(bulunan)
    for aday in iscc_adaylari():
        if aday.exists():
            return aday
    return None


def kurucu_komutu(iscc) -> list:
    """ISCC cagrisi — SAF. Surum/urun/kurucu adi surum.py'den /D ile gecer."""
    return [str(iscc),
            f"/DSURUM={surum.SURUM}",
            f"/DURUN={surum.URUN_ADI}",
            f"/DKURUCU_ADI={surum.KURUCU_ADI}",
            str(ISS_DOSYASI)]


def sha256(yol) -> str:
    ozet = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            ozet.update(parca)
    return ozet.hexdigest()


KURULUM_TXT = """{urun} {surum} — Kurulum

1. {kurucu}.exe dosyasini calistirin (yonetici izni ister; Program Files'a kurar).
2. Windows SmartScreen uyarisi cikarsa: "Daha fazla bilgi" -> "Yine de calistir".
   (Kurucu imzasiz; yayinci "{sirket}" olarak EXE ozelliklerinde gorunur.)
3. Ilk acilista lisans penceresi gelir: Luden Studio'dan aldiginiz anahtari girin.
4. On kosullar: NVIDIA ekran karti + ilk acilista internet (konusma tanima
   modeli iner). Kalici lisansta sohbet icin Ollama ayrica kurulur.

Ayrintili kilavuz, hata tablosu ve Ollama adimlari: docs/KURULUM.md
(ayni ZIP icinde KURULUM.md olarak da bulunur, varsa).

Dosya butunlugu: yandaki .sha256 dosyasindaki ozet, ZIP'in SHA-256'siyla
eslesmelidir (PowerShell: Get-FileHash <zip> -Algorithm SHA256).
"""


def kurulum_txt_metni() -> str:
    return KURULUM_TXT.format(urun=surum.URUN_ADI, surum=surum.SURUM,
                              kurucu=surum.KURUCU_ADI, sirket=surum.SIRKET)


def kurucu_uret(dist_dir) -> int:
    """build/run_web.dist -> (dist taramasi) -> ISCC -> ZIP (+KURULUM.txt) -> SHA-256.

    ZIP'in sebebi: tarayicilar ve e-posta gecitleri ciplak .exe indirmesini
    engelliyor ya da uyariyor. ZIP gecidi gecer; yaninda yayinlanan .sha256
    dosyasiyla bozulmadigi/degistirilmedigi gosterilir.
    """
    dist_dir = Path(dist_dir)
    exe = dist_dir / EXE_ADI
    if not exe.is_file():
        print(f"[kurucu] {exe} yok — once `python build.py` calistir.")
        return 1

    # Standalone dist'in TAMAMI kurucuya girer; hassas/ham bir sey sizmis
    # olmasin. (KimyaLab'daki "yalniz EXE" kuralinin standalone karsiligi.)
    yasak = dist_yasaklari(dist_dir)
    if yasak:
        print("[kurucu] dist'te kurucuya GIRMEMESI gereken dosyalar var:")
        for rel in yasak:
            print("         - " + rel)
        print("         Temizleyip yeniden deneyin (build/ silinip yeniden derlenebilir).")
        return 1

    iscc = iscc_yolu()
    if iscc is None:
        print("[kurucu] ISCC.exe bulunamadi. Inno Setup 6 kurulu degil.")
        print("         Kurulum:  winget install JRSoftware.InnoSetup")
        print(r"         Baska yere kurulduysa:  set ISCC=<tam yol>\ISCC.exe")
        return 1

    komut = kurucu_komutu(iscc)
    print("[kurucu] " + " ".join(komut))
    kod = subprocess.call(komut, cwd=KOK)
    if kod != 0:
        print(f"[kurucu] ISCC basarisiz (cikis {kod})")
        return kod

    setup = KOK / "dist" / f"{surum.KURUCU_ADI}.exe"
    if not setup.exists():
        print(f"[kurucu] ISCC bitti ama {setup} yok.")
        return 1
    return paketle_ve_ozetle(setup)


def paketle_ve_ozetle(setup: Path) -> int:
    """Kurucu EXE -> yaninda .zip (+KURULUM.txt, varsa docs/KURULUM.md) ve .sha256."""
    zip_yolu = setup.with_suffix(".zip")
    with zipfile.ZipFile(zip_yolu, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(setup, arcname=setup.name)
        # Kisa not ZIP'in ICINE girer: ZIP baskasina iletildiginde e-posta
        # metni arkada kalir; SmartScreen adimi o kisiye de ulasmali.
        z.writestr("KURULUM.txt", kurulum_txt_metni())
        kilavuz = KOK / "docs" / "KURULUM.md"
        if kilavuz.exists():
            z.write(kilavuz, arcname="KURULUM.md")
        else:
            print(f"[kurucu] UYARI: {kilavuz} yok — ZIP'te yalniz kisa KURULUM.txt var.")

    ozet = sha256(zip_yolu)
    sha_yolu = zip_yolu.with_suffix(".zip.sha256")
    # `sha256sum -c` / Get-FileHash ile karsilastirilabilir standart bicim.
    sha_yolu.write_text(f"{ozet} *{zip_yolu.name}\n", encoding="utf-8")

    mb = zip_yolu.stat().st_size / (1024 * 1024)
    print(f"\n[kurucu] TAMAM  {zip_yolu}  ({mb:.1f} MB)")
    print(f"[kurucu] SHA-256: {ozet}  -> {sha_yolu.name}")
    print("[kurucu] Ozeti indirme sayfasinda/e-postada yayinla — "
          "kullanici dosyayi dogrulayabilsin.")
    return 0


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Aican EXE build")
    parser.add_argument("--check", action="store_true",
                        help="sadece on kontrolleri calistir, derleme yapma")
    parser.add_argument("--out", default=str(KOK / "build"),
                        help="cikti dizini (varsayilan: build/)")
    parser.add_argument("--obfuscate-yok", action="store_true",
                        help="JS obfuscation adimini atla")
    parser.add_argument("--konsol", action="store_true",
                        help="konsol penceresi acik kalsin (hata ayiklama)")
    parser.add_argument("--kurucu", action="store_true",
                        help="derlemeyi atla; mevcut build/run_web.dist'ten "
                             "Inno Setup kurucusu + ZIP + SHA-256 uret")
    args = parser.parse_args(argv)

    # KONSOL KOD SAYFASI: Turkce Windows'ta stdout cp1254'tur ve Nuitka'nin
    # cikisindaki bazi karakterler orada kodlanamaz; derleme degil yazdirma
    # hatasiyla duruyordu (KimyaLab'da olculdu).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:      # noqa: BLE001
        pass

    if args.kurucu:
        return kurucu_uret(Path(args.out) / DIST_ADI)

    # On kontroller: anahtar, tohum, obfuscator.
    icerik_anahtarini_oku()
    tohum_config_kontrol()
    if not args.obfuscate_yok and shutil.which("npx") is None:
        print("[build] npx yok — obfuscation icin Node.js gerekir; "
              "ya kurun ya --obfuscate-yok verin.")
        return 1
    if not (PIPER_SESLER.is_dir() and any(PIPER_SESLER.glob("*.onnx"))):
        print(f"[build] UYARI: {PIPER_SESLER} bos — Piper cevrimdisi TTS yedegi "
              "EXE'ye girmeyecek (edge/elevenlabs cevrimici motorlar kalir).")
    if args.check:
        print("[build] On kontroller tamam.")
        return 0

    try:
        import nuitka  # noqa: F401
    except ImportError:
        print("[build] Nuitka kurulu degil:\n"
              "        .venv\\Scripts\\python.exe -m pip install nuitka")
        return 1

    # Paket ONCE hazirlanmali: komut uretilecek dosyaya isaret ediyor.
    web_hazirla(obfuscate=not args.obfuscate_yok)
    tohum_hazirla()

    cmd = komutu_olustur(args.out, konsol=args.konsol, ico=_ikon_yolu())
    print("[build] " + " ".join(cmd) + "\n")
    print("[build] Ilk derleme 15+ dakika surebilir (faster-whisper + CUDA ~2 GB).\n")
    rc = derle(cmd, KOK / "dist" / "build.log")
    if rc != 0:
        return rc

    dist = Path(args.out) / DIST_ADI
    print(f"[build] {cuda_dll_tamamla(dist)} CUDA DLL'i tamamlandi.")
    if not verify_dist(dist):
        print("\n[build] Paket EKSIK/KIRLI. Dagitmayin.")
        return 1
    print(f"\n[build] Hazir: {dist / EXE_ADI}")
    print("        Kurucu icin:  python build.py --kurucu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
