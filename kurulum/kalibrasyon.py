"""Ortam gurultusu kalibrasyonu — sergi kurulduktan SONRA bir kez calistirilir.

Sistem her acilista ortami olcmez (sergi baslangicinda 4 sn sessizlik dayatmak
kirilgandi: ziyaretci/gorevli konusursa olcum bozulur). Bunun yerine ortam BIR
KEZ burada olculur, sonuc config.json'a yazilir ve her acilista uygulanir.

NASIL CALISIR
    Olcumu bu betik DEGIL, SERGI EKRANI (tarayici) yapar. Sebebi: Python'dan
    okunan ham PCM ile Chrome'un echoCancellation/noiseSuppression/AGC
    zincirinden gecmis RMS ayni OLCEKTE DEGIL — burada olculen esik oraya
    tasinmaz. Betik yalnizca tetikler ve sonucu bekler:

        1. POST /api/kalibrasyon/istek   -> sunucudaki sayac artar
        2. Sergi ekrani /api/config yoklamasinda (~10 sn) degisimi gorur,
           calib_ms boyunca ortami dinler
        3. Ekran POST /api/kalibrasyon/sonuc -> sunucu config.json'a yazar
        4. Betik sonucu yazdirir

ON KOSUL
    Sistem CALISIYOR olmali (BASLAT.bat) ve sergi ekrani acik olmali,
    mikrofon dinlemesi ACIK olmali (ekranda 'd' ile kontrol edilir).

KULLANIM
    python kurulum\\kalibrasyon.py            # olc ve kaydet
    python kurulum\\kalibrasyon.py --goster   # yalnizca kayitli olcumu goster
    python kurulum\\kalibrasyon.py --port 5000
    python kurulum\\kalibrasyon.py --onaysiz  # Enter beklemeden hemen olc

Cikis kodu: 0 basarili, 1 basarisiz/iptal.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# Ekran istegi ~10 sn'lik yoklamada gorur + calib_ms olcer + sonucu gonderir.
# Bol pay: yoklama tam kacirilmis olabilir, TTS calisiyorsa olcum ertelenir.
BEKLEME_SN = 75
YOKLAMA_SN = 1.0


def _url(port: int, yol: str) -> str:
    return f"http://127.0.0.1:{port}{yol}"


def _get(port: int, yol: str, timeout: float = 5.0):
    with urllib.request.urlopen(_url(port, yol), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(port: int, yol: str, govde: dict | None = None, timeout: float = 5.0):
    data = json.dumps(govde or {}).encode("utf-8")
    req = urllib.request.Request(
        _url(port, yol), data=data, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _zaman(ts) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "-"


def kayitli_yazdir(durum: dict) -> None:
    k = durum.get("kayitli") or {}
    if k.get("abs_min"):
        print(f"  Kayitli olcum : {_zaman(k.get('at'))}")
        print(f"    gurultu tabani : {k.get('floor'):.4f}")
        print(f"    alt esik       : {k.get('abs_min'):.4f}"
              f"   (medyan {k.get('p50') or 0:.4f} / p90 {k.get('p90') or 0:.4f})")
    else:
        print("  Kayitli olcum : YOK — sistem config'teki elle ayarli esikleri kullaniyor")
    # Gurultu profili: Whisper oncesi denoise'un y_noise referansi.
    pr = durum.get("profil") or {}
    if not pr.get("denoise_acik", True):
        print("  Gurultu profili: denoise KAPALI (whisper_denoise_enabled=false)")
    elif pr.get("var"):
        print(f"  Gurultu profili: VAR ({pr.get('sn')} sn)"
              f" — denoise bastirma {pr.get('prop')}")
    else:
        print("  Gurultu profili: YOK — denoise gurultuyu sesin icinden tahmin ediyor")
    if not durum.get("enabled", True):
        print("  UYARI: config.json'da voice_input_calibration_enabled=false —")
        print("         kalibrasyon KAPALI, olcum yapilamaz.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ortam gurultusu kalibrasyonu")
    ap.add_argument("--port", type=int, default=5000, help="sunucu portu (varsayilan 5000)")
    ap.add_argument("--goster", action="store_true", help="olcme, yalnizca kayitli degeri goster")
    ap.add_argument("--onaysiz", action="store_true", help="Enter bekleme, hemen olc")
    a = ap.parse_args()

    print()
    print("=" * 62)
    print("  ORTAM GURULTUSU KALIBRASYONU")
    print("=" * 62)

    # 1) Sunucu ayakta mi
    try:
        _get(a.port, "/api/health", timeout=3.0)
    except (urllib.error.URLError, OSError, ValueError):
        print()
        print(f"  HATA: Sunucuya ulasilamadi (127.0.0.1:{a.port}).")
        print("  Once sistemi baslatin: BASLAT.bat  — sonra bu araci tekrar calistirin.")
        print()
        return 1

    try:
        durum = _get(a.port, "/api/kalibrasyon")
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"\n  HATA: Kalibrasyon durumu okunamadi: {e}\n")
        return 1

    print()
    kayitli_yazdir(durum)
    print()

    if a.goster:
        return 0
    if not durum.get("enabled", True):
        return 1

    # 2) Sessizlik uyarisi + onay
    print("  Olcum SERGI EKRANINDA yapilir (mikrofon orada).")
    print("  Ekranin acik ve mikrofon dinlemesinin ACIK oldugundan emin olun ('d' tusu).")
    print()
    print("  >>> OLCUM BOYUNCA (~4 sn) KIMSE KONUSMASIN <<<")
    print("      Salon sergi gunundeki halinde olsun: klima, projeksiyon, kalabalik acik.")
    print("      Konusulursa olcum reddedilir ve tekrar denemeniz istenir.")
    print()
    if not a.onaysiz:
        try:
            input("  Hazir oldugunuzda Enter'a basin (vazgecmek icin Ctrl+C)... ")
        except (KeyboardInterrupt, EOFError):
            print("\n  Iptal edildi.\n")
            return 1

    # 3) Istegi birak
    try:
        seq = int(_post(a.port, "/api/kalibrasyon/istek")["seq"])
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(f"\n  HATA: Olcum istegi gonderilemedi: {e}\n")
        return 1

    print()
    print("  Istek birakildi. Sergi ekrani en gec ~10 sn icinde olcume baslayacak.")
    print("  Ekranda 'Ortam sesi olculuyor' yazisi cikacak — SESSIZ OLUN.")
    print()

    # 4) Sonucu bekle
    bitis = time.monotonic() + BEKLEME_SN
    nokta = 0
    while time.monotonic() < bitis:
        time.sleep(YOKLAMA_SN)
        try:
            d = _get(a.port, "/api/kalibrasyon")
        except (urllib.error.URLError, OSError, ValueError):
            continue          # sunucu bir an mesgul — beklemeye devam
        s = d.get("sonuc")
        # seq esitligi: onceki kosunun sonucunu bu kosunun sonucu sanmayalim.
        if s and int(s.get("seq") or 0) == seq:
            print()
            if s.get("ok"):
                print("  " + "-" * 58)
                print("  OLCUM BASARILI — config.json'a yazildi")
                print("  " + "-" * 58)
                print(f"    ortam medyani  : {s['p50']:.4f}")
                print(f"    ortam p90      : {s['p90']:.4f}")
                print(f"    gurultu tabani : {s['floor']:.4f}")
                print(f"    ALT ESIK       : {s['abs_min']:.4f}")
                try:
                    pr = _get(a.port, "/api/kalibrasyon").get("profil") or {}
                    if pr.get("var"):
                        print(f"    gurultu profili: {pr.get('sn')} sn kaydedildi"
                              f" (denoise bastirma {pr.get('prop')})")
                    elif pr.get("denoise_acik", True):
                        print("    gurultu profili: KAYDEDILEMEDI — denoise profilsiz calisir")
                except (urllib.error.URLError, OSError, ValueError):
                    pass
                print()
                print("  Bu esik artik her acilista uygulanir; tekrar olcmeye gerek yok.")
                print("  Salon dolunca/bosalinca ya da mikrofonun yeri degisince yeniden calistirin.")
                print()
                return 0
            print("  " + "-" * 58)
            print("  OLCUM REDDEDILDI")
            print("  " + "-" * 58)
            print(f"    sebep: {s.get('sebep') or 'bilinmiyor'}")
            print()
            print("  Sistem eski (config'teki) esiklerle calismaya devam ediyor.")
            print("  Sessizligi saglayip bu araci TEKRAR calistirin.")
            print()
            return 1
        nokta = (nokta + 1) % 4
        sys.stdout.write("\r  Sonuc bekleniyor" + "." * nokta + "   ")
        sys.stdout.flush()

    print()
    print()
    print(f"  ZAMAN ASIMI ({BEKLEME_SN} sn) — sergi ekranindan sonuc gelmedi.")
    print("  Kontrol edin:")
    print("    - Sergi ekrani (tarayici sekmesi) acik mi?")
    print("    - Mikrofon dinlemesi acik mi? Ekranda 'd' tusu ac/kapa yapar,")
    print("      'm' tusu canli seviye gostergesini acar.")
    print("    - Ekranda 'MIKROFON YOK' uyarisi var mi?")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
