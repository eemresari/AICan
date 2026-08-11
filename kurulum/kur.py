#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AICAN sergi kurulumu — temiz bir Windows PC'yi oyunu çalıştıracak hâle getirir.

KUR.bat bu betiği çağırır (Python'u o kurar/bulur). Betik İDEMPOTENTTİR:
yarıda kesilirse ya da bir adım hata verirse tekrar çalıştırmak güvenlidir.

Adımlar:
  1. Python sürüm kontrolü
  2. Ekran kartı + sürücü tespiti (profil bunu takip eder)
  3. Microsoft VC++ Redistributable (Whisper/Piper DLL'leri için ŞART)
  4. pip bağımlılıkları (orchestrator/requirements.txt)
  5. Profil seçimi (karta göre otomatik önerilir → config.json)
  6. Ollama kurulumu + sunucu + model indirme + GPU'ya yerleştiğinin doğrulanması
  7. Whisper ses-tanıma modelini ön-indirme
  8. Ses varlıkları (Piper çevrimdışı sesi + ElevenLabs ön-üretim cache'i)
  9. ElevenLabs API anahtarı (opsiyonel — boşsa edge/piper yedeği çalışır)
 10. Masaüstü kısayolu + opsiyonel otomatik başlatma
 11. Sağlık kontrolü (saglik_kontrol.py)

Parametreler (hepsi opsiyonel; verilmezse soru sorulur):
  --profil sergi5090|sergi|laptop   --anahtar ELEVENLABS_KEY
  --otomatik e|h                    --sessiz
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import donanim  # noqa: E402 — aynı klasördeki ortak donanım modülü

BURASI = Path(__file__).resolve().parent
ROOT = BURASI.parent
ORCH = ROOT / "orchestrator"
TOPLAM_ADIM = 11

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def baslik(no: int, ad: str) -> None:
    print(f"\n=== [{no}/{TOPLAM_ADIM}] {ad} " + "=" * max(1, 46 - len(ad)))


def sor(mesaj: str, varsayilan: str, sessiz: bool) -> str:
    if sessiz:
        return varsayilan
    yanit = input(f"{mesaj} [{varsayilan}]: ").strip()
    return yanit or varsayilan


def calistir(cmd: list, hata_olumcul: bool = True) -> int:
    """Komutu konsola akıtarak çalıştır; dönüş kodu döner."""
    print("  $ " + " ".join(str(c) for c in cmd))
    kod = subprocess.run([str(c) for c in cmd]).returncode
    if kod != 0 and hata_olumcul:
        raise SystemExit(f"HATA: komut {kod} koduyla bitti: {cmd[0]}")
    return kod


# ——— Adım 1: Python ————————————————————————————————————————
def adim_python() -> None:
    baslik(1, "Python sürümü")
    v = sys.version_info
    print(f"  Python {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    if (v.major, v.minor) < (3, 10):
        raise SystemExit("HATA: Python 3.10+ gerekli. KUR.bat'ın kurduğu sürümü kullanın.")
    print("  TAMAM.")


# ——— Adım 2: Donanım ————————————————————————————————————————
def adim_donanim():
    """Kartı erkenden tespit et: profil seçimi (adım 5) buna dayanıyor ve
    sürücü eksikse pip/model indirmeden ÖNCE haberdar olmak gerekiyor."""
    baslik(2, "Ekran kartı ve sürücü")
    gpu = donanim.birincil_gpu()
    if gpu is None:
        print("  NVIDIA kartı bulunamadı (nvidia-smi yok ya da sürücü kurulu değil).")
        print("  Oyun yine kurulur ama LLM ve ses tanıma CPU'da çok yavaş çalışır.")
        print("  Sergi PC'sinde bu satırı görüyorsan ÖNCE NVIDIA sürücüsünü kur:")
        print("  https://www.nvidia.com/download/index.aspx")
        return None
    print(f"  {gpu}")
    if gpu.blackwell:
        print("  Blackwell (RTX 50 serisi / sm_120) tespit edildi.")
        print("  NOT: Bu mimaride Whisper INT8 çalışmaz; sergi5090 profili float16 kullanır.")
    uyari = donanim.surucu_uyarisi(gpu)
    if uyari:
        print(f"  !! UYARI: {uyari}")
    else:
        print("  Sürücü yeterli.")
    return gpu


# ——— Adım 3: VC++ Redistributable ——————————————————————————
def _msvcp_yuklu() -> bool:
    """faster-whisper (ctranslate2) ve piper (onnxruntime) MSVCP140 ister;
    temiz Windows'ta ve python.org kurulumunda BU DLL YOKTUR."""
    import ctypes
    try:
        ctypes.WinDLL("msvcp140")
        ctypes.WinDLL("vcruntime140_1")
        return True
    except OSError:
        return False


def adim_vcredist() -> None:
    baslik(3, "Microsoft VC++ Redistributable (Whisper/Piper için şart)")
    if _msvcp_yuklu():
        print("  Zaten kurulu.")
        return
    print("  Kuruluyor (winget)...")
    calistir(["winget", "install", "-e", "--id", "Microsoft.VCRedist.2015+.x64",
              "--accept-source-agreements", "--accept-package-agreements"],
             hata_olumcul=False)   # 'zaten kurulu' çıkış kodları hata sayılmasın
    if _msvcp_yuklu():
        print("  TAMAM.")
    else:
        print("  UYARI: msvcp140.dll hâlâ yüklenemiyor — sesli giriş ve Piper sesi")
        print("  'DLL load failed' verir. Elle kurun: https://aka.ms/vs/17/release/vc_redist.x64.exe")


# ——— Adım 4: pip bağımlılıkları ————————————————————————————
def adim_pip() -> None:
    baslik(4, "Python bağımlılıkları (pip)")
    gereksinim = ORCH / "requirements.txt"
    if not gereksinim.is_file():
        raise SystemExit(f"HATA: {gereksinim} yok — proje klasörü eksik kopyalanmış.")
    calistir([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], hata_olumcul=False)
    calistir([sys.executable, "-m", "pip", "install", "-r", gereksinim])
    # ctranslate2 sürümü Blackwell için kritik — requirements taban veriyor ama
    # makinede ESKI bir sürüm kilitliyse (baska proje, eski venv) pip onu
    # yukseltmeden birakabilir. Fiilen ne kuruldugunu goster.
    try:
        import importlib.metadata as md
        print(f"  ctranslate2 {md.version('ctranslate2')}  ·  "
              f"faster-whisper {md.version('faster-whisper')}")
    except Exception:  # noqa: BLE001
        pass
    print("  TAMAM.")


# ——— Adım 5: Profil ————————————————————————————————————————
def profil_sor(gpu, sessiz: bool) -> str:
    """Karta göre öner, kullanıcıya onaylat."""
    onerilen = donanim.profil_oner(gpu, ORCH)
    print("  Kullanılabilir profiller:")
    for anahtar, (dosya, ad, _) in donanim.PROFILLER.items():
        isaret = "→" if anahtar == onerilen else " "
        varmi = "" if (ORCH / dosya).is_file() else "   (dosya YOK)"
        print(f"   {isaret} {anahtar:<10} {ad}{varmi}")
    if gpu is not None:
        print(f"  Tespit edilen kart ({gpu.ad}, {gpu.vram_gb:.0f} GB) için öneri: {onerilen}")
    return sor("  Profil?", onerilen, sessiz)


def adim_profil(profil: str, gpu) -> dict:
    baslik(5, f"Yapılandırma profili: {profil}")
    if profil not in donanim.PROFILLER:
        raise SystemExit(f"HATA: bilinmeyen profil '{profil}' — "
                         f"seçenekler: {', '.join(donanim.PROFILLER)}")
    hedef = ORCH / "config.json"
    kaynak_ad = donanim.PROFILLER[profil][0]
    if kaynak_ad != "config.json":
        kaynak = ORCH / kaynak_ad
        if not kaynak.is_file():
            raise SystemExit(f"HATA: {kaynak} yok.")
        if hedef.is_file():
            yedek = ORCH / f"config.yedek-{datetime.now():%Y%m%d-%H%M%S}.json"
            shutil.copy2(hedef, yedek)
            print(f"  Mevcut config.json yedeklendi: {yedek.name}")
        shutil.copy2(kaynak, hedef)
        print(f"  {kaynak_ad} → config.json kopyalandı.")
    else:
        print("  Laptop profili: mevcut config.json olduğu gibi kullanılıyor.")
    cfg = json.loads(hedef.read_text(encoding="utf-8-sig"))
    print(f"  Model: {cfg.get('ollama_model')}  ·  Whisper: {cfg.get('whisper_model_size')}"
          f" ({cfg.get('whisper_compute_type')})  ·  TTS: {cfg.get('tts_engine')}")

    for u in donanim.config_uyumu(gpu, cfg):
        print(f"  !! UYARI: {u}")
    # Model karta sığıyor mu? (Whisper + Windows için ~5 GB pay bırak.)
    agirlik = donanim.model_vram_ihtiyaci(str(cfg.get("ollama_model", "")))
    if gpu is not None and agirlik:
        if agirlik + 5 > gpu.vram_gb:
            print(f"  !! UYARI: model ~{agirlik:.0f} GB, kartta {gpu.vram_gb:.0f} GB VRAM var. "
                  f"Ollama katmanları CPU'ya taşırabilir (yavaş). Daha küçük bir model seç.")
        else:
            print(f"  VRAM: model ~{agirlik:.0f} GB / {gpu.vram_gb:.0f} GB — sığıyor.")
    return cfg


# ——— Adım 6: Ollama ————————————————————————————————————————
def ollama_yolu() -> str | None:
    adaylar = ["ollama",
               str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
               r"C:\Program Files\Ollama\ollama.exe"]
    for aday in adaylar:
        try:
            r = subprocess.run([aday, "--version"], capture_output=True, timeout=15)
            if r.returncode == 0:
                return aday
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return None


def ollama_sunucu_hazir() -> bool:
    import requests
    try:
        return requests.get("http://localhost:11434", timeout=2).ok
    except Exception:
        return False


def _gpu_yerlesimi_dogrula(yol: str, cfg: dict) -> None:
    """Model GERÇEKTEN GPU'ya mı yüklendi?

    Ollama'nın en sinsi arızası: yeni bir kartı (ör. Blackwell) tanıyamayınca
    hata VERMEDEN CPU'ya düşer — model çalışır, cevaplar 10 kat yavaşlar ve
    bu ancak sergi günü fark edilir. Küçük bir istekle modeli yükleyip
    /api/ps'teki size_vram'e bakıyoruz: 0 ise CPU'dayız."""
    import requests
    url = cfg.get("ollama_url", "http://localhost:11434")
    model = cfg.get("ollama_model", "")
    print("  Model GPU'ya yükleniyor (ilk yükleme uzun sürebilir)...")
    try:
        requests.post(f"{url}/api/generate",
                      json={"model": model, "prompt": "merhaba", "stream": False,
                            "keep_alive": "5m", "options": {"num_predict": 1}},
                      timeout=600)
        yuklu = requests.get(f"{url}/api/ps", timeout=15).json().get("models", [])
    except Exception as e:  # noqa: BLE001 — kurulum sürsün, sağlık kontrolü tekrar bakar
        print(f"  UYARI: GPU yerleşimi doğrulanamadı ({e})")
        return
    for m in yuklu:
        if not str(m.get("name", "")).startswith(model.split(":")[0]):
            continue
        vram = int(m.get("size_vram", 0))
        toplam = int(m.get("size", 0)) or 1
        if vram == 0:
            print("  !! UYARI: model CPU'da çalışıyor (size_vram=0) — cevaplar çok yavaş olur.")
            print("     NVIDIA sürücüsünü güncelle ve Ollama'yı en son sürüme çıkar:")
            print("     winget upgrade -e --id Ollama.Ollama")
        elif vram < toplam * 0.9:
            print(f"  !! UYARI: modelin yalnızca %{100 * vram // toplam}'i GPU'da — "
                  f"katmanlar CPU'ya taşmış, cevaplar yavaşlar.")
        else:
            print(f"  GPU'da: {vram / 2**30:.1f} GB (modelin tamamı) ✔")
        return
    print("  UYARI: model /api/ps listesinde görünmedi — GPU yerleşimi doğrulanamadı.")


def adim_ollama(cfg: dict) -> None:
    baslik(6, "Ollama + dil modeli")
    yol = ollama_yolu()
    if yol is None:
        print("  Ollama bulunamadı — winget ile kuruluyor...")
        calistir(["winget", "install", "-e", "--id", "Ollama.Ollama",
                  "--accept-source-agreements", "--accept-package-agreements"])
        yol = ollama_yolu()
        if yol is None:
            raise SystemExit("HATA: Ollama kurulumu doğrulanamadı. Elle kurun: https://ollama.com/download")
    else:
        # Yeni kartlar (Blackwell) yalnızca güncel Ollama'da tanınır; kurulu bir
        # sürüm varsa da yükseltmeyi dene (zaten günceli 'no upgrade' der).
        calistir(["winget", "upgrade", "-e", "--id", "Ollama.Ollama",
                  "--accept-source-agreements", "--accept-package-agreements"],
                 hata_olumcul=False)
    try:
        s = subprocess.run([yol, "--version"], capture_output=True, text=True, timeout=15)
        print(f"  Ollama: {yol}  ({(s.stdout or s.stderr or '').strip()})")
    except Exception:  # noqa: BLE001
        print(f"  Ollama: {yol}")

    if not ollama_sunucu_hazir():
        print("  Ollama sunucusu başlatılıyor...")
        subprocess.Popen([yol, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(20):
            time.sleep(1)
            if ollama_sunucu_hazir():
                break
        else:
            raise SystemExit("HATA: Ollama sunucusu 20 sn içinde ayağa kalkmadı.")
    print("  Sunucu çalışıyor.")

    model = cfg.get("ollama_model", "")
    if not model:
        raise SystemExit("HATA: config.json içinde ollama_model boş.")
    print(f"  Model indiriliyor (varsa atlanır): {model}")
    calistir([yol, "pull", model])
    _gpu_yerlesimi_dogrula(yol, cfg)
    print("  TAMAM.")


# ——— Adım 7: Whisper ————————————————————————————————————————
def adim_whisper(cfg: dict) -> None:
    # KRITIK: config'te SECILI modeli indir (small degil). Sergi profilleri
    # large-v3 / large-v3-turbo kullaniyor; burada 'small' indirilirse ilk acilis
    # ya internet ister ya da sessizce yavas CPU/small'a duser. Indirme cihazdan
    # bagimsiz (CPU/int8 ile HF reposu cekilir), bu yuzden CUDA olmadan da dogru
    # model onbellege alinir.
    size = str(cfg.get("whisper_model_size", "small"))
    baslik(7, f"Whisper '{size}' ses-tanıma modeli (ilk seferde iner)")
    try:
        from faster_whisper import WhisperModel
        print("  İndiriliyor/yükleniyor — birkaç dakika sürebilir...")
        WhisperModel(size, device="cpu", compute_type="int8")
        print(f"  TAMAM — '{size}' modeli yerel önbellekte, sergide internet gerekmez.")
    except Exception as e:  # noqa: BLE001 — kurulum sürsün, sağlık kontrolü yakalar
        print(f"  UYARI: Whisper ön-indirme başarısız: {e}")
        print("  (Sergiden önce internetli ortamda KUR.bat'ı tekrar çalıştırın.)")


# ——— Adım 8: Ses varlıkları ————————————————————————————————
def adim_ses_varliklari(cfg: dict) -> None:
    """Piper çevrimdışı sesi + ElevenLabs ön-üretim cache'i.

    İkisi de .gitignore'da: git clone ile GELMEZLER. Piper sesi (60 MB)
    buradan indirilebilir; cache (~450 MB) ElevenLabs kredisiyle üretildiği
    için elden taşınır — eksikse ne yapılacağını söyle."""
    baslik(8, "Ses varlıkları (çevrimdışı ses + ön-üretim cache)")

    ses = cfg.get("tts_fallback_voice", "tr_TR-dfki-medium")
    voices = ORCH / "tts" / "voices"
    onnx = voices / f"{ses}.onnx"
    if onnx.is_file() and onnx.with_suffix(".onnx.json").is_file():
        print(f"  Piper çevrimdışı sesi zaten var: {ses}")
    else:
        print(f"  Piper sesi indiriliyor: {ses} (~60 MB)")
        voices.mkdir(parents=True, exist_ok=True)
        kod = calistir([sys.executable, "-m", "piper.download_voices", ses,
                        "--data-dir", str(voices)], hata_olumcul=False)
        if kod != 0 or not onnx.is_file():
            print("  UYARI: Piper sesi inmedi — internetsiz ortamda ses TAMAMEN susar.")
            print(f"  Elle: python -m piper.download_voices {ses} --data-dir {voices}")

    cache = ORCH / "tts" / "cache"
    n = len(list(cache.glob("*.wav"))) if cache.is_dir() else 0
    if n >= 1000:
        print(f"  ElevenLabs ön-üretim cache'i: {n} ses parçası ✔")
    else:
        print(f"  !! ElevenLabs ön-üretim cache'i EKSİK ({n} parça).")
        print("     Bu klasör git'te YOK (~450 MB) — eski PC'den elden taşınmalı:")
        print("       ESKİ PC'de:  cd orchestrator && python -m tts.paket_hazirla --kopyala")
        print("       paketi USB ile taşı, YENİ PC'de cache/ içeriğini şuraya kopyala:")
        print(f"       {cache}")
        print("     Taşımazsan: her replik canlı sentezlenir (ElevenLabs kredisi + gecikme),")
        print("     anahtar da yoksa ücretsiz edge/piper sesine düşer.")


# ——— Adım 9: ElevenLabs anahtarı ————————————————————————————
def adim_elevenlabs(anahtar: str | None, sessiz: bool) -> None:
    baslik(9, "ElevenLabs API anahtarı (opsiyonel)")
    mevcut = os.environ.get("ELEVENLABS_API_KEY", "")
    if anahtar is None and not sessiz:
        print("  Boş bırakılırsa: ses, ücretsiz edge-tts + Piper yedeğiyle çalışır.")
        if mevcut:
            print("  (Bu makinede zaten bir anahtar tanımlı — boş geçersen o kalır.)")
        anahtar = input("  ElevenLabs anahtarı (boş geçilebilir): ").strip()
    if anahtar:
        calistir(["setx", "ELEVENLABS_API_KEY", anahtar], hata_olumcul=False)
        os.environ["ELEVENLABS_API_KEY"] = anahtar
        print("  Anahtar kalıcı ortam değişkenine yazıldı (yeni pencerelerde geçerli).")
    elif mevcut:
        print("  Mevcut anahtar korundu.")
    else:
        print("  Anahtar yok — ElevenLabs devre dışı, edge/piper yedeği kullanılacak.")


# ——— Adım 10: Kısayollar ————————————————————————————————————
def _kisayol(ps_klasor_sabiti: str, ad: str, hedef: Path) -> bool:
    def tek_tirnak(s) -> str:
        # PowerShell tek tırnaklı dizgede kaçış: ' -> '' (yol apostrof içerebilir,
        # ör. "mehmet'in klasörü") — kaçışsız hâli PS ParserError verir.
        return str(s).replace("'", "''")

    ps = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$d = [Environment]::GetFolderPath('{ps_klasor_sabiti}'); "
        f"$s = $w.CreateShortcut((Join-Path $d '{tek_tirnak(ad)}.lnk')); "
        f"$s.TargetPath = '{tek_tirnak(hedef)}'; "
        f"$s.WorkingDirectory = '{tek_tirnak(hedef.parent)}'; "
        "$s.Save()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True)
    if r.returncode != 0:
        hata = (r.stderr or "").strip().splitlines()
        if hata:
            print(f"    PowerShell hatası: {hata[-1]}")
    return r.returncode == 0


def adim_kisayol(otomatik: str) -> None:
    baslik(10, "Kısayollar")
    baslat = ROOT / "BASLAT.bat"
    if _kisayol("Desktop", "AICAN Baslat", baslat):
        print("  Masaüstüne 'AICAN Baslat' kısayolu kondu.")
    else:
        print(f"  UYARI: masaüstü kısayolu oluşmadı — elle kullanın: {baslat}")
    if otomatik.lower().startswith("e"):
        if _kisayol("Startup", "AICAN Baslat", baslat):
            print("  Otomatik başlatma AÇIK: PC açılınca oyun kendiliğinden başlar.")
        else:
            print("  UYARI: otomatik başlatma kısayolu oluşmadı.")
    else:
        print("  Otomatik başlatma kapalı (istersen kur.py --otomatik e ile tekrar çalıştır).")


# ——— Adım 11: Sağlık kontrolü ———————————————————————————————
def adim_saglik() -> int:
    baslik(11, "Sağlık kontrolü")
    return subprocess.run([sys.executable, "-X", "utf8",
                           str(BURASI / "saglik_kontrol.py")]).returncode


def main() -> int:
    p = argparse.ArgumentParser(description="AICAN sergi kurulumu")
    p.add_argument("--profil", choices=tuple(donanim.PROFILLER))
    p.add_argument("--anahtar", help="ElevenLabs API anahtarı")
    p.add_argument("--otomatik", choices=("e", "h"), help="PC açılışında oyunu başlat")
    p.add_argument("--sessiz", action="store_true", help="soru sorma, varsayılanları kullan")
    a = p.parse_args()

    print("AICAN kurulumu başlıyor — proje klasörü:", ROOT)
    adim_python()
    gpu = adim_donanim()
    adim_vcredist()
    adim_pip()
    profil = a.profil or (donanim.profil_oner(gpu, ORCH) if a.sessiz
                          else profil_sor(gpu, a.sessiz))
    cfg = adim_profil(profil, gpu)
    adim_ollama(cfg)
    adim_whisper(cfg)
    adim_ses_varliklari(cfg)
    adim_elevenlabs(a.anahtar, a.sessiz)
    otomatik = a.otomatik or sor("PC açılınca oyun otomatik başlasın mı? (e/h)", "e", a.sessiz)
    adim_kisayol(otomatik)
    kod = adim_saglik()

    print("\n" + "=" * 52)
    if kod == 0:
        print("KURULUM TAMAM ✔  Oyunu başlatmak için: masaüstündeki")
        print("'AICAN Baslat' kısayolu ya da proje kökündeki BASLAT.bat")
    else:
        print("Kurulum bitti ama SAĞLIK KONTROLÜ hata verdi — yukarıya bakın.")
    return kod


if __name__ == "__main__":
    sys.exit(main())
