#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dayanikli model indirme — 'ollama pull' surekli geri sariyorsa bunu kullan.

SORUN: Ollama buyuk modelleri paralel akislarla (OLLAMA_MAX_TRANSFER_STREAMS,
varsayilan 4) indiriyor. Bagllanti sallanan bir agda akislardan biri kopunca o
parca bastan aliniyor ve ekrandaki "inen GB" GERI DUSUYOR. Sonsuz dongu gibi
gorunur; 18 GB'lik gemma4:26b'de sik yasanir.

COZUM: akis sayisini 1'e indir + kesilirse tekrar dene. Ollama tamamlanan
blob'lari diskte tutuyor, dolayisiyla her deneme KALDIGI YERDEN devam eder —
bu betik bunu otomatiklestirir.

Kullanim:
  python kurulum/model_indir.py                 # config.json'daki modeli indir
  python kurulum/model_indir.py gemma4:12b      # belirli bir model
  python kurulum/model_indir.py --akis 2        # akis sayisini elle ver
  python kurulum/model_indir.py --deneme 50     # daha inatci ol
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import donanim  # noqa: E402

BURASI = Path(__file__).resolve().parent
ORCH = BURASI.parent / "orchestrator"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def ollama_yolu() -> str | None:
    adaylar = ["ollama",
               str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
               r"C:\Program Files\Ollama\ollama.exe"]
    for aday in adaylar:
        try:
            if subprocess.run([aday, "--version"], capture_output=True, timeout=15).returncode == 0:
                return aday
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return None


def inen_gb() -> float:
    """Diskteki blob'larin toplami — ilerlemenin GERCEK olcusu.

    Ekrandaki yuzde yaniltici olabilir (kopan parca geri sayar); dosyalarin
    toplam boyutu ise yalnizca artar. Denemeler arasinda bunu karsilastirip
    'ilerliyor mu, takildi mi' sorusunu kesin cevapliyoruz."""
    blobs = Path.home() / ".ollama" / "models" / "blobs"
    if not blobs.is_dir():
        return 0.0
    return sum(f.stat().st_size for f in blobs.glob("*") if f.is_file()) / 2**30


def disk_bos_gb() -> float:
    import shutil as sh
    try:
        return sh.disk_usage(Path.home()).free / 2**30
    except OSError:
        return -1.0


def _profil_uyusmazligi(model: str) -> bool:
    """config.json bu makineye AIT MI? Degilse indirmeyi durdur.

    Gercek vaka (sergi PC'si, 2026-08-11): kullanici bu betigi calistirdi ve
    18 GB'lik gemma4:26b yerine 2,6 GB'lik qwen3:4b inmeye basladi. Sebep,
    config.json'in hala LAPTOP profili olmasiydi — KUR.bat'in profil adimi ya
    hic kosmamis ya da kart taninmadigi icin 'laptop' onerip oylece kabul
    edilmisti.

    Bu yalniz yanlis model demek degil: ayni dosya whisper_compute_type'i da
    veriyor ve laptop profili int8_float16 istiyor — RTX 50 serisinde CALISMAZ.
    Yani yanlis modeli indirmek, arkasinda cok daha buyuk bir yanlis kurulumun
    habercisi. Sessizce indirmek yerine burada durup soyluyoruz."""
    gpu = donanim.birincil_gpu()
    if gpu is None:
        return False
    onerilen = donanim.profil_oner(gpu, ORCH)
    beklenen_dosya = ORCH / donanim.PROFILLER[onerilen][0]
    if beklenen_dosya.name == "config.json" or not beklenen_dosya.is_file():
        return False
    try:
        beklenen_model = json.loads(
            beklenen_dosya.read_text(encoding="utf-8-sig"))["ollama_model"]
    except Exception:  # noqa: BLE001
        return False
    if beklenen_model == model:
        return False
    print(f"\n  !! DUR — config.json bu makineye ait gorunmuyor.")
    print(f"     kart          : {gpu.ad} ({gpu.vram_gb:.0f} GB)")
    print(f"     onerilen profil: {onerilen}  ->  {beklenen_model}")
    print(f"     config.json'da : {model}")
    print(f"\n     Profil adimi uygulanmamis. Yanlis modeli indirmeden once duzelt —")
    print(f"     ayni dosya Whisper ayarini da veriyor ve yanlis profil RTX 50")
    print(f"     serisinde int8 isteyip ses tanimayi CPU'ya dusurur.\n")
    print(f"     Duzeltme:")
    print(f"       copy \"{beklenen_dosya}\" \"{ORCH / 'config.json'}\"")
    print(f"     Sonra bu betigi tekrar calistir.")
    print(f"     (Yine de bu modeli indirmek istiyorsan: MODEL_INDIR.bat {model})\n")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Dayanikli Ollama model indirme")
    p.add_argument("model", nargs="?", help="model etiketi (bos: config.json'dan)")
    p.add_argument("--akis", type=int, default=1,
                   help="es zamanli indirme akisi (varsayilan 1 = en dayanikli)")
    p.add_argument("--deneme", type=int, default=30, help="en fazla deneme (varsayilan 30)")
    a = p.parse_args()

    model = a.model
    if not model:
        try:
            model = json.loads((ORCH / "config.json").read_text(encoding="utf-8-sig"))["ollama_model"]
        except Exception as e:  # noqa: BLE001
            return int(bool(print(f"HATA: config.json'dan model okunamadi: {e}")))
        print(f"  (model config.json'dan okundu: {model})")
        if _profil_uyusmazligi(model):
            return 1

    yol = ollama_yolu()
    if yol is None:
        print("HATA: Ollama bulunamadi. Once kurulum/KUR.bat calistir.")
        return 1

    print(f"\n=== DAYANIKLI MODEL INDIRME ===\n  model : {model}\n  ollama: {yol}")

    bos = disk_bos_gb()
    if bos >= 0:
        print(f"  disk  : {bos:.0f} GB bos")
        gerek = donanim.model_vram_ihtiyaci(model)
        if gerek and bos < gerek * 1.3:
            print(f"  !! UYARI: {model} ~{gerek:.0f} GB — disk dar, indirme sessizce kesilebilir.")

    # KRITIK AYAR: paralel akis sayisi. Sallanan agda 4 akis birbirini
    # dusuruyor; 1'e indirmek yavas ama KESINTISIZ indirir.
    os.environ["OLLAMA_MAX_TRANSFER_STREAMS"] = str(a.akis)
    subprocess.run(["setx", "OLLAMA_MAX_TRANSFER_STREAMS", str(a.akis)],
                   capture_output=True)     # sonraki oturumlar icin de kalsin
    print(f"  akis  : {a.akis} (OLLAMA_MAX_TRANSFER_STREAMS)")
    print("\n  NOT: Ollama'yi sistem tepsisinden CIKIP yeniden acmadiysan bu ayar")
    print("  sunucu tarafinda gecerli olmayabilir. Indirme yine geri sariyorsa:")
    print("  tepsi ikonu -> Quit Ollama, sonra bu betigi tekrar calistir.\n")

    onceki = inen_gb()
    print(f"  diskteki blob'lar: {onceki:.2f} GB (buradan devam edilecek)\n")

    for deneme in range(1, a.deneme + 1):
        print(f"--- deneme {deneme}/{a.deneme} " + "-" * 40)
        kod = subprocess.run([yol, "pull", model]).returncode
        simdi = inen_gb()
        if kod == 0:
            print(f"\n  TAMAM — {model} indi.  (diskte {simdi:.2f} GB)")
            return 0
        artis = simdi - onceki
        print(f"\n  Kesildi (kod {kod}). Bu denemede +{artis:.2f} GB indi, "
              f"toplam {simdi:.2f} GB.")
        if artis < 0.01 and deneme >= 3:
            print("  !! Uc denemedir ilerleme YOK — sorun ag degil baska bir sey olabilir:")
            print("     - disk dolu mu?")
            print("     - antivirus ~/.ollama/models/blobs klasorunu kilitliyor mu?")
            print("     - VPN/proxy acik mi? (kapat, tekrar dene)")
            print("     - telefon hotspot'u ile dene — kurumsal ag sik sik SSL kesiyor")
        onceki = simdi
        time.sleep(3)

    print(f"\n  {a.deneme} denemede bitmedi. Diskte {inen_gb():.2f} GB birikti —")
    print("  betigi tekrar calistirirsan KALDIGI YERDEN devam eder.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
