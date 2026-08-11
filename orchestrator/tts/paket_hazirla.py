"""SERGI PC PAKETI — sergiye tasinacak ses varliklarini bir klasorde toplar.

Neden gerekli: `orchestrator/tts/cache/` ve `orchestrator/tts/voices/` .gitignore'da
(sirasiyla ~800 MB ve ~61 MB) — git pull ile GELMEZLER. Kod git'ten, ses varliklari
elden (USB/ag) tasinir.

Neden "hepsini kopyala" degil: onbellekte ARTIK KULLANILMAYAN parcalar birikir
(yogunluk/metin/veri degisince eski anahtarlar olu kalir). Bu betik yalnizca
gen_batch_elevenlabs.build_units'in URETTIGI CANLI anahtarlari kopyalar —
runtime'in gercekten isteyecegi kume. Boylece paket yariya iner ve sergiye
"acaba eksik mi" sorusu kalmadan gider.

Kullanim (orchestrator/ dizininden):
  python -m tts.paket_hazirla                 # RAPOR: ne kadar, kac dosya (kopyalamaz)
  python -m tts.paket_hazirla --kopyala       # paketi olustur
  python -m tts.paket_hazirla --kopyala --hedef D:\aican_paket
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # orchestrator/ path'e

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from game_engine import GameEngine                       # noqa: E402
from web_server import load_config, DEFAULT_TTS_VOICE    # noqa: E402
from tts.cache import WavCache                           # noqa: E402
import tts.gen_batch_elevenlabs as GB                    # noqa: E402

TTS_DIR = Path(__file__).resolve().parent


def canli_anahtarlar(cache: WavCache, voice: str, tum_veri: bool = True) -> set:
    """Runtime'in isteyebilecegi TUM cache anahtarlari (batch ile ayni kume).

    tum_veri=True: ai/ altindaki her soru seti varyanti icin de enumere eder."""
    keys = set()
    uretecler = (GB.veri_kombinasyonlari() if tum_veri
                 else [("aktif", GameEngine(bridge=None))])
    for _, ge in uretecler:
        for u in GB.build_units(ge):
            for chunk, sig, yog in GB.unit_key_map(u):
                keys.add(cache.make_key(chunk, sig, yog, voice))
    return keys


def _mb(n: int) -> str:
    return f"{n / 2**20:,.0f} MB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kopyala", action="store_true", help="Paketi gercekten olustur")
    ap.add_argument("--hedef", default=str(TTS_DIR / "sergi_paketi"),
                    help="Paket klasoru (varsayilan: tts/sergi_paketi)")
    ap.add_argument("--yalniz-aktif", action="store_true",
                    help="Yalnizca AKTIF soru setini kapsa (kucuk paket, sergi PC ayni surumdeyse)")
    args = ap.parse_args()

    cfg = load_config()
    voice = cfg.get("tts_voice", DEFAULT_TTS_VOICE)
    cache = WavCache(TTS_DIR / "cache", max_files=99999, enabled=True)

    keys = canli_anahtarlar(cache, voice, tum_veri=not args.yalniz_aktif)
    var, yok, boyut = [], [], 0
    for k in sorted(keys):
        f = cache.dir / f"{k}.wav"
        if f.exists():
            var.append(f)
            boyut += f.stat().st_size
        else:
            yok.append(k)

    tum = list(cache.dir.glob("*.wav"))
    tum_boyut = sum(f.stat().st_size for f in tum)
    voices = TTS_DIR / "voices"
    v_boyut = sum(f.stat().st_size for f in voices.rglob("*") if f.is_file()) if voices.is_dir() else 0

    print(f"\n=== SERGI PAKETI (ses={voice}) ===\n")
    print(f"  onbellekteki tum dosyalar : {len(tum):5}  {_mb(tum_boyut)}")
    print(f"  CANLI (pakete girecek)    : {len(var):5}  {_mb(boyut)}")
    print(f"  olu/artik (girmeyecek)    : {len(tum) - len(var):5}  {_mb(tum_boyut - boyut)}")
    print(f"  piper cevrimdisi sesleri  : {'':5}  {_mb(v_boyut)}  (tts/voices — git'te YOK)")
    print(f"  PAKET TOPLAMI             : {'':5}  {_mb(boyut + v_boyut)}\n")

    if yok:
        print(f"  !! UYARI: {len(yok)} canli anahtarin sesi YOK — sergide ucretsiz sese duser.")
        print("     Once uret: python -m tts.gen_batch_elevenlabs --run --yes\n")

    if not args.kopyala:
        print("  Rapor bitti (hicbir sey kopyalanmadi). Olusturmak icin: --kopyala\n")
        return

    hedef = Path(args.hedef)
    h_cache = hedef / "cache"
    h_cache.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(var, 1):
        hf = h_cache / f.name
        if not hf.exists() or hf.stat().st_size != f.stat().st_size:
            shutil.copy2(f, hf)
        if i % 500 == 0:
            print(f"  {i}/{len(var)} kopyalandi...")
    if voices.is_dir():
        shutil.copytree(voices, hedef / "voices", dirs_exist_ok=True)

    (hedef / "OKU.txt").write_text(
        "AICAN — sergi PC ses paketi\n"
        "===========================\n\n"
        "Sergi PC'sinde AICan deposu guncel (git pull) OLDUKTAN SONRA:\n\n"
        "  1) cache/  icerigini  ->  orchestrator/tts/cache/   altina kopyala\n"
        "  2) voices/ icerigini  ->  orchestrator/tts/voices/  altina kopyala\n"
        "  3) ELEVENLABS_API_KEY ortam degiskenini ayarla (nadir isskalar da\n"
        "     Mert sesiyle gelsin; yoksa edge -> piper yedegine duser)\n"
        "  4) Dogrula:  cd orchestrator\n"
        "               python -m tts.gen_batch_elevenlabs --eksik\n"
        "     EKSIK = 0 gormelisin. Degilse sesler ucretsiz yedege duser.\n"
        "  5) Sunucuyu baslat ve bir tur oyna; hazir ekrani / es-zit tanitimi /\n"
        "     menu / oyun sonu repliklerini DINLE.\n",
        encoding="utf-8")

    print(f"\n  PAKET HAZIR: {hedef}")
    print(f"  {len(var)} ses dosyasi + piper sesleri + OKU.txt  ({_mb(boyut + v_boyut)})\n")


if __name__ == "__main__":
    main()
