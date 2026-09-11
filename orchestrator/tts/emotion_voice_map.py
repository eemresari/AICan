"""aican seslendirme — duygu -> prosodi esleme.

gestures.json'daki her jest icin duygu_valansi (V, -1..1) ve uyarilma_seviyesi
(A, 0..1) degerlerini Piper TTS prosodi parametrelerine cevirir. Klasik 2 boyutlu
duygu modeli (valans-uyarilma):

  - Uyarilma (A) yuksek  -> hizli, gur, canli tonlama, kisa duraklar, yuksek perde
  - Valans (V) pozitif    -> parlak/yuksek perde; negatif -> koyu/alcak perde

yogunluk (Y, 0..1) sapma miktarini olcekler: dusukse notr'a yakin, yuksekse tam etki.

Tek karakter sesi (aican) kullanilir; duyguya gore SADECE tonlama degisir, konusmaci
degil. Boylece 31 jest tek tek elle yazilmadan valans+uyarilma'dan turetilir.
"""
from __future__ import annotations

import json
from functools import lru_cache

import paths

# paths.kaynak_oku anahtari (depo kokune gore POSIX); dondurulmus build'de bellekten.
_DEFAULT_GESTURES = "ai/gestures.json"

# Notr capa: V=0, A~0.45 (sakin konusma). Ham formuller bu noktada bu degerleri verir,
# boylece yogunluk harmani puruzsuz olur.
_NEUTRAL = {
    "length_scale": 1.05,
    "pitch_semitones": 0.0,
    "volume": 0.95,
    "noise_scale": 0.667,
    "noise_w_scale": 0.80,
    "sentence_silence": 0.30,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@lru_cache(maxsize=4)
def _load_va(gestures_path: str) -> dict:
    """jest_id -> (valans, uyarilma) sozlugu. lru_cache ile dosya bir kez okunur."""
    data = json.loads(paths.kaynak_oku(gestures_path).decode("utf-8-sig"))
    out = {}
    for j in data.get("jestler", []):
        out[j["id"]] = (
            float(j.get("duygu_valansi", 0.0)),
            float(j.get("uyarilma_seviyesi", 0.45)),
        )
    return out


def prosody_for_va(valence: float, arousal: float, yogunluk: float = 0.7) -> dict:
    """Valans + uyarilma + yogunluk -> Piper prosodi parametreleri."""
    V = _clamp(valence, -1.0, 1.0)
    A = _clamp(arousal, 0.0, 1.0)
    Y = _clamp(yogunluk, 0.0, 1.0)

    # Ham parametreler (uyarilma agirlikli, valans ile renklendirilir)
    length_raw = 1.30 - 0.55 * A + 0.15 * max(0.0, -V)         # yavas <-> hizli
    pitch_raw = _clamp(4.0 * (A - 0.45) + 1.8 * V, -4.0, 4.0)  # perde (yari ton)
    volume_raw = 0.95 + 0.50 * (A - 0.45)                      # ses gucu
    nscale_raw = 0.667 + 0.35 * (A - 0.45)                     # tonlama cesitliligi
    nw_raw = 0.80 + 0.55 * (A - 0.45)                          # hece suresi cesitliligi
    silence_raw = 0.50 - 0.40 * A                              # cumle arasi durak (sn)

    # yogunluk: notr capaya dogru harmanla (0 -> ~notr, 1 -> tam etki)
    f = 0.45 + 0.55 * Y

    def blend(raw: float, key: str) -> float:
        return _NEUTRAL[key] + (raw - _NEUTRAL[key]) * f

    return {
        "length_scale": round(_clamp(blend(length_raw, "length_scale"), 0.70, 1.50), 3),
        "pitch_semitones": round(_clamp(blend(pitch_raw, "pitch_semitones"), -4.0, 4.0), 2),
        "volume": round(_clamp(blend(volume_raw, "volume"), 0.70, 1.15), 3),
        "noise_scale": round(_clamp(blend(nscale_raw, "noise_scale"), 0.40, 0.95), 3),
        "noise_w_scale": round(_clamp(blend(nw_raw, "noise_w_scale"), 0.40, 1.30), 3),
        "sentence_silence": round(_clamp(blend(silence_raw, "sentence_silence"), 0.10, 0.70), 3),
    }


def prosody_for(jest_id: str, yogunluk: float = 0.7, gestures_path: str | None = None) -> dict:
    """jest_id (ornegin 'uzgun_derin') + yogunluk -> prosodi parametreleri.

    Bilinmeyen jest_id notr capaya duser. Sonuca teshis icin jest_id/valans/uyarilma eklenir.
    """
    path = str(gestures_path) if gestures_path else str(_DEFAULT_GESTURES)
    V, A = _load_va(path).get(jest_id, (0.0, 0.45))
    p = prosody_for_va(V, A, yogunluk)
    p.update({"jest_id": jest_id, "valence": V, "arousal": A})
    return p


if __name__ == "__main__":
    # Hizli gozlem: tum jestlerin prosodi tablosu
    va = _load_va(str(_DEFAULT_GESTURES))
    hdr = f"{'jest_id':18} {'V':>5} {'A':>5} | {'len':>5} {'pitch':>6} {'vol':>5} {'nsc':>5} {'nw':>5} {'sil':>5}"
    print(hdr)
    print("-" * len(hdr))
    for jid in va:
        p = prosody_for(jid, 0.8)
        print(f"{jid:18} {p['valence']:>5} {p['arousal']:>5} | "
              f"{p['length_scale']:>5} {p['pitch_semitones']:>6} {p['volume']:>5} "
              f"{p['noise_scale']:>5} {p['noise_w_scale']:>5} {p['sentence_silence']:>5}")
