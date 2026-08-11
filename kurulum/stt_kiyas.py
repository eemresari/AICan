#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""STT kiyas — bu makinede hangi Whisper ayari en iyi? OLC, tahmin etme.

Neden gerekli: "large-v3-turbo large-v3'ten 4-8 kat hizli" rakamlari UZUN
ses transkripsiyonundan geliyor. Turbo ENCODER'i aynen koruyup DECODER'i
32 -> 4 katmana indiriyor. Sergideki sesler ise cok kisa ("basla", "atasozu",
tek kelime cevaplar) ve Whisper girdiyi her halukarda 30 sn'ye dolduruyor:
yani is encoder'da yogunlasiyor, decoder pay kucuk. Sonuc olarak KISA seste
turbo'nun avantaji reklam edilenden cok daha az olabilir. Hangi ayarin
kazandigi makineye ve ses tipine gore degisir -> burada olculur.

Ayrica: yanlis tanima, yavas tanimadan PAHALIDIR. Cocuk cevabi tekrar
soylemek zorunda kalinca tur bastan doner (game_engine bunu "en buyuk
gecikme" diye isaretliyor). Bu yuzden tablo yalniz sureyi degil DOGRULUGU
da veriyor; ikisine birden bakip sec.

Kullanim (proje kokunden):
  python kurulum/stt_kiyas.py                 # varsayilan 4 aday, oyun sozlugu
  python kurulum/stt_kiyas.py --ses D:\kayit  # KENDI kayitlarinla (en saglikli)
  python kurulum/stt_kiyas.py --tekrar 5      # her klip 5 kez (daha kararli sure)

UYARI: --ses verilmezse test klipleri edge-tts ile URETILIR. Sentetik ses
temizdir; SUREYI dogru olcer ama gurultulu salondaki cocuk sesini temsil
etmez. Dogruluk karsilastirmasi icin sahada `whisper_debug_save_audio: true`
ile gercek kayit toplayip --ses ile buraya vermek en dogrusu.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import unicodedata
from pathlib import Path

BURASI = Path(__file__).resolve().parent
ROOT = BURASI.parent
ORCH = ROOT / "orchestrator"
sys.path.insert(0, str(BURASI))
import donanim  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Sergide gercekten soylenen sozler — web_server.WHISPER_GAME_PROMPT ile ayni evren.
OYUN_SOZLUGU = [
    "başla", "hazırım", "tamam", "menü", "çıkış", "tekrar",
    "atasözü", "eş anlam", "zıt anlam", "doğru", "yanlış",
    "bir", "iki", "üç", "dört", "merhaba", "oyun oynayalım",
    "bilmiyorum", "geç", "devam",
]

# Denenecek adaylar: (etiket, model, compute_type, beam_size)
# float16 sabit — Blackwell'de int8 zaten calismiyor (bkz. config.sergi5090.json).
ADAYLAR = [
    ("large-v3      beam5", "large-v3",       "float16", 5),
    ("large-v3      beam1", "large-v3",       "float16", 1),
    ("large-v3-turbo beam5", "large-v3-turbo", "float16", 5),
    ("large-v3-turbo beam1", "large-v3-turbo", "float16", 1),
]


# Turkce'ye ozgu harfler -> ASCII. NFKD'ye BIRAKILAMAZ: 'ş' (s+cedilla)
# ayrisip 's' olurken 'ı' tek kod noktasi oldugu icin ayrismaz — sonuc yari
# sade, yari degil bir metin olur ve 'hazırım' ile 'hazirim' esitsiz cikar.
# Acik tablo tutarli davranir.
_TR_ASCII = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "i": "i",
    "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ç": "c", "Ç": "c",
    "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "â": "a", "î": "i", "û": "u",
})


def _sadelestir(s: str) -> str:
    """Karsilastirma icin normalize: kucuk harf, noktalama yok, Turkce sade.

    Aksana KARSI HOSGORULU olmak bilincli: Whisper zaman zaman Turkce
    isaretleri dusuruyor ve oyunun kendi cevap kabulu de bulanik esleme
    yapiyor. Kiyasin sorusu "harfi harfine ayni mi" degil, "oyun bu cevabi
    kabul eder miydi" — bu yuzden 'dogru' ile 'doğru' ayni sayilir."""
    s = s.translate(_TR_ASCII).lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    return " ".join("".join(c for c in s if c.isalnum() or c.isspace()).split())


def klipleri_hazirla(hedef: Path, sozler: list) -> list:
    """Yoksa edge-tts ile test klibi uret. (metin, wav_yolu) listesi doner."""
    hedef.mkdir(parents=True, exist_ok=True)
    ciftler, eksik = [], []
    for s in sozler:
        f = hedef / f"{_sadelestir(s).replace(' ', '_')}.wav"
        ciftler.append((s, f))
        if not f.is_file():
            eksik.append((s, f))
    if not eksik:
        print(f"  {len(ciftler)} test klibi hazir: {hedef}")
        return ciftler

    print(f"  {len(eksik)} klip uretiliyor (edge-tts, internet gerekir)...")
    try:
        import asyncio
        import edge_tts
        import imageio_ffmpeg
        import subprocess as sp
    except ImportError as e:
        print(f"  HATA: klip uretilemedi ({e}). --ses ile kendi kayitlarini ver.")
        return []
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    async def uret(metin: str, cikti: Path) -> None:
        mp3 = cikti.with_suffix(".mp3")
        await edge_tts.Communicate(metin, "tr-TR-EmelNeural").save(str(mp3))
        # Whisper 16 kHz mono PCM bekler; mp3'u ona cevir.
        sp.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(mp3),
                "-ar", "16000", "-ac", "1", str(cikti)], check=True)
        mp3.unlink(missing_ok=True)

    async def hepsi() -> None:
        for metin, f in eksik:
            await uret(metin, f)

    try:
        asyncio.run(hepsi())
    except Exception as e:  # noqa: BLE001
        print(f"  HATA: klip uretimi basarisiz ({e}). --ses ile kendi kayitlarini ver.")
        return []
    return ciftler


def kliplari_yukle(klasor: Path) -> list:
    """Kullanicinin verdigi klasor: her .wav icin referans metin, ayni adli
    .txt dosyasindan okunur (yoksa dogruluk olculmez, yalniz sure)."""
    ciftler = []
    for f in sorted(klasor.glob("*.wav")):
        txt = f.with_suffix(".txt")
        ref = txt.read_text(encoding="utf-8").strip() if txt.is_file() else ""
        ciftler.append((ref, f))
    return ciftler


def aday_olc(model_adi: str, compute: str, beam: int, ciftler: list,
             tekrar: int, prompt: str) -> dict:
    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    try:
        model = WhisperModel(model_adi, device="cuda", compute_type=compute)
    except Exception as e:  # noqa: BLE001
        return {"hata": str(e)}
    yukleme = time.perf_counter() - t0

    # Isinma: ilk cagri CUDA cekirdeklerini derler, olcume katilmamali.
    model.transcribe(str(ciftler[0][1]), language="tr", beam_size=beam,
                     vad_filter=False, without_timestamps=True)

    sureler, dogru, olculen = [], 0, 0
    for ref, wav in ciftler:
        for _ in range(tekrar):
            t = time.perf_counter()
            segments, _ = model.transcribe(
                str(wav), language="tr", vad_filter=True,
                beam_size=beam, condition_on_previous_text=False,
                initial_prompt=prompt or None, without_timestamps=True)
            metin = " ".join(s.text for s in segments).strip()
            sureler.append((time.perf_counter() - t) * 1000)
        if ref:
            olculen += 1
            dogru += int(_sadelestir(metin) == _sadelestir(ref))
    del model
    return {
        "yukleme_s": yukleme,
        "p50": statistics.median(sureler),
        "p95": sorted(sureler)[max(0, int(len(sureler) * 0.95) - 1)],
        "ort": statistics.mean(sureler),
        "dogru": dogru, "olculen": olculen,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Whisper ayar kiyaslamasi")
    p.add_argument("--ses", type=Path, help="kendi kayitlarinin klasoru (wav + ayni adli txt)")
    p.add_argument("--tekrar", type=int, default=3, help="her klip kac kez (varsayilan 3)")
    p.add_argument("--prompt", default="", help="initial_prompt (bos: oyun promptu)")
    a = p.parse_args()

    gpu = donanim.birincil_gpu()
    print("\n=== STT KIYAS ===")
    print(f"  GPU: {gpu if gpu else 'YOK — bu kiyas GPU ister'}")
    if gpu is None:
        print("  NVIDIA karti bulunamadi; olcum anlamsiz olur. Cikiliyor.")
        return 1

    if a.ses:
        ciftler = kliplari_yukle(a.ses)
        kaynak = f"kendi kayitlarin ({a.ses})"
        if not ciftler:
            print(f"  HATA: {a.ses} icinde .wav bulunamadi.")
            return 1
    else:
        ciftler = klipleri_hazirla(BURASI / "_stt_klip", OYUN_SOZLUGU)
        kaynak = "edge-tts ile URETILEN sentetik klipler"
        if not ciftler:
            return 1

    prompt = a.prompt
    if not prompt:
        try:
            sys.path.insert(0, str(ORCH))
            from web_server import WHISPER_GAME_PROMPT
            prompt = WHISPER_GAME_PROMPT
        except Exception:  # noqa: BLE001
            pass

    print(f"  klip sayisi: {len(ciftler)}  ·  her biri {a.tekrar} kez  ·  kaynak: {kaynak}")
    if not a.ses:
        print("  !! Sentetik ses TEMIZ — SUREYI dogru olcer ama gurultulu salondaki")
        print("     cocuk sesini TEMSIL ETMEZ. Dogruluk icin sahada gercek kayit topla:")
        print("     config.json whisper_debug_save_audio: true -> sonra --ses ile ver.")
    print()

    sonuc = {}
    for etiket, model_adi, compute, beam in ADAYLAR:
        print(f"  olculuyor: {etiket} ...", flush=True)
        sonuc[etiket] = aday_olc(model_adi, compute, beam, ciftler, a.tekrar, prompt)

    print("\n" + "=" * 72)
    print(f"  {'ayar':<22}{'p50 ms':>9}{'p95 ms':>9}{'yukleme':>10}{'dogruluk':>12}")
    print("  " + "-" * 68)
    for etiket, r in sonuc.items():
        if "hata" in r:
            print(f"  {etiket:<22}  HATA: {r['hata'][:40]}")
            continue
        dog = (f"{100 * r['dogru'] // r['olculen']}%  ({r['dogru']}/{r['olculen']})"
               if r["olculen"] else "—")
        print(f"  {etiket:<22}{r['p50']:>9.0f}{r['p95']:>9.0f}"
              f"{r['yukleme_s']:>9.1f}s{dog:>12}")
    print("=" * 72)

    gecerli = {k: v for k, v in sonuc.items() if "hata" not in v}
    if gecerli:
        hizli = min(gecerli.items(), key=lambda kv: kv[1]["p50"])
        print(f"\n  En hizli: {hizli[0]}  ({hizli[1]['p50']:.0f} ms)")
        if any(v["olculen"] for v in gecerli.values()):
            iyi = max(gecerli.items(),
                      key=lambda kv: (kv[1]["dogru"], -kv[1]["p50"]))
            print(f"  En dogru: {iyi[0]}  "
                  f"({iyi[1]['dogru']}/{iyi[1]['olculen']}, {iyi[1]['p50']:.0f} ms)")

    print("\n  ONEMLI — modelden once BUNA bak:")
    try:
        cfg = json.loads((ORCH / "config.json").read_text(encoding="utf-8-sig"))
        sessizlik = cfg.get("voice_input_silence_ms_game", cfg.get("voice_input_silence_ms"))
        print(f"  voice_input_silence_ms_game = {sessizlik} ms")
        print(f"  Cocuk sustuktan sonra kayit bu kadar BEKLIYOR, STT ondan SONRA basliyor.")
        print(f"  Yani algilanan gecikme ~= {sessizlik} + (yukaridaki p50). Model degistirerek")
        print(f"  kazanacagin milisaniye, bu esigi kisaltarak kazanacagindan kucuk olabilir.")
    except Exception:  # noqa: BLE001
        pass
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
