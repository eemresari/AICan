#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AICAN sağlık kontrolü — sergi PC'si oyunu çalıştırmaya hazır mı?

Kurulumun son adımı olarak koşar; sergi gününden önce tek başına da
çalıştırılabilir:  python kurulum/saglik_kontrol.py

Çıkış kodu: 0 = hazır (uyarılar olabilir), 1 = eksik/hatalı kurulum.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import donanim  # noqa: E402 — kur.py ile ortak donanım/profil mantığı

BURASI = Path(__file__).resolve().parent
ROOT = BURASI.parent
ORCH = ROOT / "orchestrator"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_SONUC = {"PASS": 0, "UYARI": 0, "HATA": 0}


def yaz(durum: str, mesaj: str) -> None:
    _SONUC[durum] += 1
    isaret = {"PASS": "✔", "UYARI": "!", "HATA": "✘"}[durum]
    print(f"  [{isaret} {durum:5}] {mesaj}")


def kontrol_python() -> None:
    v = sys.version_info
    if (v.major, v.minor) >= (3, 10):
        yaz("PASS", f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        yaz("HATA", f"Python {v.major}.{v.minor} çok eski — 3.10+ gerekli")


def kontrol_paketler() -> None:
    paketler = ["flask", "requests", "faster_whisper", "edge_tts",
                "piper", "imageio_ffmpeg", "psutil"]
    for ad in paketler:
        try:
            __import__(ad)
            yaz("PASS", f"paket: {ad}")
        except Exception as e:  # noqa: BLE001
            yaz("HATA", f"paket eksik/bozuk: {ad} ({e}) — pip install -r orchestrator/requirements.txt")


def kontrol_vcredist() -> None:
    """ctranslate2 (Whisper) ve onnxruntime (Piper) MSVCP140 ister; temiz
    Windows'ta yoktur — pip başarılı olur ama import 'DLL load failed' verir."""
    import ctypes
    try:
        ctypes.WinDLL("msvcp140")
        ctypes.WinDLL("vcruntime140_1")
        yaz("PASS", "VC++ Redistributable (msvcp140) yüklü")
    except OSError:
        yaz("HATA", "VC++ Redistributable eksik — Whisper ve Piper açılmaz. "
                    "Kur: https://aka.ms/vs/17/release/vc_redist.x64.exe")


def kontrol_gpu(cfg: dict | None = None):
    """Ekran kartı, sürücü ve config'in GPU varsayımları.

    Yeni sergi PC'sinin (RTX 5090 / Blackwell) en olası sessiz arızası:
    yanlış profil kopyalanınca Whisper INT8 ister, sm_120 desteklemez, sistem
    CPU'ya düşer ve 'çalışıyor ama yavaş' hâlde sergiye çıkar. Burada yakala."""
    gpu = donanim.birincil_gpu()
    if gpu is None:
        yaz("UYARI", "NVIDIA kartı görünmüyor (nvidia-smi yok/sürücü kurulu değil) — "
                     "LLM ve ses tanıma CPU'da çok yavaş çalışır")
        return None
    yaz("PASS", f"GPU: {gpu}")
    uyari = donanim.surucu_uyarisi(gpu)
    if uyari:
        yaz("HATA", uyari)
    if gpu.blackwell:
        # Blackwell'de INT8 kapalı (CTranslate2 4.6.2) ve CUDA 12.8 (4.6.3) şart.
        try:
            import importlib.metadata as md
            s = md.version("ctranslate2")
            parcalar = tuple(int(x) for x in s.split(".")[:3] if x.isdigit())
            if parcalar >= (4, 6, 3):
                yaz("PASS", f"ctranslate2 {s} (Blackwell/CUDA 12.8 destekli)")
            else:
                yaz("HATA", f"ctranslate2 {s} — RTX 50 serisi için 4.6.3+ gerekli "
                            f"(CUDA 12.8). Güncelle: pip install -U 'ctranslate2>=4.6.3,<5'")
        except Exception as e:  # noqa: BLE001
            yaz("UYARI", f"ctranslate2 sürümü okunamadı ({e})")
    if cfg:
        for u in donanim.config_uyumu(gpu, cfg):
            yaz("HATA", u)
        agirlik = donanim.model_vram_ihtiyaci(str(cfg.get("ollama_model", "")))
        if agirlik and agirlik + 5 > gpu.vram_gb:
            yaz("UYARI", f"model ~{agirlik:.0f} GB + Whisper, {gpu.vram_gb:.0f} GB VRAM'e "
                         f"zor sığar — katmanlar CPU'ya taşabilir (yavaş cevap)")
    return gpu


def kontrol_ffmpeg() -> None:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        yaz("PASS", f"ffmpeg: {exe}")
    except Exception as e:  # noqa: BLE001
        yaz("HATA", f"ffmpeg bulunamadı ({e}) — Piper perde kaydırma çalışmaz")


def kontrol_dosyalar() -> None:
    gerekli = [
        "run_web.py", "BASLAT.bat",
        "orchestrator/web_server.py", "orchestrator/game_engine.py",
        "orchestrator/llm_bridge.py", "orchestrator/word_llm.py",
        "web/AI_Body_v2.html", "web/Kontrol_Paneli.html",
        "web/app.js", "web/control.js", "web/led-panel.js",
        "ai/system_prompt.txt", "ai/gestures.json",
    ]
    eksik = [d for d in gerekli if not (ROOT / d).is_file()]
    if eksik:
        for d in eksik:
            yaz("HATA", f"dosya eksik: {d} — proje klasörü eksik kopyalanmış")
    else:
        yaz("PASS", f"proje dosyaları tam ({len(gerekli)} kritik dosya)")
    # Emoji kareleri: gestures.json'daki gorsel_tipi=='emoji' jestlerin TAMAMI
    # icin kare klasoru olmali (eksik USB kopyasini isim isim yakala).
    try:
        jestler = json.loads((ROOT / "ai" / "gestures.json")
                             .read_text(encoding="utf-8-sig")).get("jestler", [])
        gerekli_jest = {j["id"] for j in jestler if j.get("gorsel_tipi") == "emoji"}
    except Exception:  # noqa: BLE001
        gerekli_jest = set()
    emoji_dir = ROOT / "assets" / "emojis"
    varolan = ({d.name for d in emoji_dir.iterdir()
                if d.is_dir() and any(d.glob("frame_*.png"))}
               if emoji_dir.is_dir() else set())
    if not gerekli_jest:
        yaz("UYARI", "gestures.json'dan emoji jest listesi çıkarılamadı — kare kontrolü atlandı")
    else:
        eksik_jest = sorted(gerekli_jest - varolan)
        if eksik_jest:
            yaz("HATA", f"emoji kareleri eksik ({len(eksik_jest)}/{len(gerekli_jest)}): "
                        f"{', '.join(eksik_jest[:6])}{'…' if len(eksik_jest) > 6 else ''} "
                        f"— sergi ekranı bu yüzleri gösteremez")
        else:
            yaz("PASS", f"emoji kareleri tam ({len(gerekli_jest)} jest)")


def kontrol_veri() -> None:
    beklenen = {
        "ai/es_zit_anlam.json": (dict, 50),
        "ai/atasozu.json": (list, 50),
        "ai/dogru_yanlis.json": (list, 10),
        "ai/word_categories.json": (dict, 1),
    }
    for yol, (tip, esik) in beklenen.items():
        p = ROOT / yol
        try:
            veri = json.loads(p.read_text(encoding="utf-8-sig"))
            if not isinstance(veri, tip):
                yaz("HATA", f"{yol}: beklenen yapı {tip.__name__} değil")
            elif len(veri) < esik:
                yaz("UYARI", f"{yol}: {len(veri)} kayıt (beklenen ≥{esik}) — havuz küçük")
            else:
                yaz("PASS", f"{yol}: {len(veri)} kayıt")
        except FileNotFoundError:
            yaz("HATA", f"{yol} yok")
        except (ValueError, OSError) as e:
            yaz("HATA", f"{yol} okunamadı: {e}")


def config_yukle() -> dict:
    p = ORCH / "config.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8-sig"))
        yaz("PASS", f"config.json geçerli (model: {cfg.get('ollama_model')}, "
                    f"tts: {cfg.get('tts_engine')})")
        return cfg
    except Exception as e:  # noqa: BLE001
        yaz("HATA", f"config.json okunamadı: {e}")
        return {}


def kontrol_piper(cfg: dict) -> None:
    ses = cfg.get("tts_fallback_voice", "tr_TR-dfki-medium")
    onnx = ORCH / "tts" / "voices" / f"{ses}.onnx"
    if onnx.is_file() and onnx.with_suffix(".onnx.json").is_file():
        yaz("PASS", f"Piper çevrimdışı sesi: {ses}")
    else:
        yaz("HATA", f"Piper ses dosyası eksik: {onnx} — internetsiz ortamda ses tamamen susar")


def kontrol_tts_cache(cfg: dict) -> None:
    cache = ORCH / "tts" / "cache"
    n = len(list(cache.glob("*.wav"))) if cache.is_dir() else 0
    if cfg.get("tts_engine") == "elevenlabs":
        if n >= 1000:
            yaz("PASS", f"TTS ön-üretim cache: {n} ses parçası")
        elif n > 0:
            yaz("UYARI", f"TTS cache küçük ({n} parça) — gen_batch_elevenlabs koşulmamış olabilir")
        else:
            yaz("UYARI", "TTS cache boş — her replik canlı sentezlenir (kredi + gecikme)")
    else:
        yaz("PASS", f"TTS cache: {n} parça (motor: {cfg.get('tts_engine')})")
    anahtar = os.environ.get("ELEVENLABS_API_KEY") or cfg.get("tts_elevenlabs_api_key")
    if cfg.get("tts_engine") == "elevenlabs" and not anahtar:
        yaz("UYARI", "ELEVENLABS_API_KEY yok — cache'te olmayan replikler edge/piper sesiyle çalar")


def kontrol_ollama_gpu(url: str, model: str) -> None:
    """Yüklü model GPU'da mı, CPU'da mı?

    Ollama yeni bir kartı tanıyamazsa HATA VERMEDEN CPU'ya düşer: model
    çalışır, cevaplar 10 kat yavaşlar. /api/ps'teki size_vram bunu tek
    bakışta söyler. Model o an yüklü değilse (keep_alive dolmuş) sessiz geç —
    BASLAT.bat açılışta warmup yapıyor, sergi anında yüklü olur."""
    import requests
    try:
        yuklu = requests.get(f"{url}/api/ps", timeout=5).json().get("models", [])
    except Exception:  # noqa: BLE001
        return
    for m in yuklu:
        if not str(m.get("name", "")).startswith(model.split(":")[0]):
            continue
        vram, toplam = int(m.get("size_vram", 0)), int(m.get("size", 0)) or 1
        if vram == 0:
            yaz("HATA", "model CPU'da çalışıyor (size_vram=0) — cevaplar çok yavaş. "
                        "NVIDIA sürücüsünü ve Ollama'yı güncelleyin "
                        "(winget upgrade -e --id Ollama.Ollama)")
        elif vram < toplam * 0.9:
            yaz("UYARI", f"modelin yalnızca %{100 * vram // toplam}'i GPU'da — "
                         f"katmanlar CPU'ya taşmış, cevaplar yavaşlar")
        else:
            yaz("PASS", f"model GPU'da: {vram / 2**30:.1f} GB")
        return


def kontrol_ollama(cfg: dict) -> None:
    model = cfg.get("ollama_model", "")
    url = cfg.get("ollama_url", "http://localhost:11434")
    try:
        import requests
        r = requests.get(f"{url}/api/tags", timeout=3)
        adlar = [m.get("name", "") for m in r.json().get("models", [])]
        yaz("PASS", f"Ollama sunucusu çalışıyor ({len(adlar)} model)")
        if model in adlar or any(a.startswith(model) for a in adlar):
            yaz("PASS", f"model hazır: {model}")
        else:
            yaz("HATA", f"model çekilmemiş: {model} — 'ollama pull {model}' çalıştırın")
        kontrol_ollama_gpu(url, model)
        return
    except Exception:
        pass
    # Sunucu kapalı — diskteki manifest'e bak (kurulu ama başlatılmamış olabilir).
    if ":" in model:
        ad, etiket = model.split(":", 1)
        manifest = list((Path.home() / ".ollama" / "models" / "manifests")
                        .glob(f"*/*/{ad}/{etiket}"))
        if manifest:
            yaz("UYARI", f"Ollama sunucusu şu an kapalı ama model diskte var ({model}) — "
                         f"BASLAT.bat açılışta başlatır")
            return
    yaz("HATA", "Ollama sunucusuna erişilemiyor ve model diskte bulunamadı — "
                "kurulum/KUR.bat'ı tekrar çalıştırın")


def kontrol_whisper(cfg: dict | None = None) -> None:
    # Config'te SECILI modeli dogrula (kur.py da bunu indiriyor). Sergi profili
    # large-v3-turbo; 'small' sabit kontrol edilirse dogru model varken bile
    # yanlis "eksik" uyarisi cikardi. local_files_only=True: internet DENEME.
    size = str((cfg or {}).get("whisper_model_size", "small"))
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # noqa: BLE001 — import (örn. DLL) hatası ayrı raporlansın
        yaz("HATA", f"faster-whisper yüklenemedi: {e}")
        return
    try:
        WhisperModel(size, device="cpu", compute_type="int8", local_files_only=True)
        yaz("PASS", f"Whisper '{size}' yerel önbellekte (sesli giriş çevrimdışı hazır)")
    except Exception:  # noqa: BLE001 — yerel kopya yok/eksik
        yaz("HATA", f"Whisper '{size}' yerel önbellekte YOK — internetli ortamda "
                    "kurulum/KUR.bat'ı tekrar çalıştırın")


def kontrol_ses_aygitlari() -> None:
    """Mikrofon (birincil girdi!) ve hoparlör var mı? — en olası sahne hatası."""
    import subprocess
    ps = "Get-PnpDevice -Class AudioEndpoint -Status OK | Select-Object -ExpandProperty InstanceId"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=30)
        cikti = r.stdout or ""
        mikrofon = cikti.count("{0.0.1.00000000}")   # MMDevice: capture endpoint
        hoparlor = cikti.count("{0.0.0.00000000}")   # MMDevice: render endpoint
        if mikrofon:
            yaz("PASS", f"mikrofon algılandı ({mikrofon} kayıt aygıtı)")
        else:
            yaz("UYARI", "mikrofon görünmüyor — sesli giriş çalışmaz; USB mikrofonu tak")
        if hoparlor:
            yaz("PASS", f"ses çıkışı algılandı ({hoparlor} aygıt)")
        else:
            yaz("UYARI", "ses çıkış aygıtı görünmüyor — hoparlörü bağla")
    except Exception:  # noqa: BLE001
        yaz("UYARI", "ses aygıtları sorgulanamadı — sahada elle kontrol et")


def kontrol_port(cfg: dict) -> None:
    port = int(cfg.get("web_port", 5057))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        yaz("PASS", f"port {port} boş")
    except OSError:
        yaz("UYARI", f"port {port} dolu — sunucu zaten çalışıyor olabilir (sorun değil)")


def kontrol_internet() -> None:
    try:
        socket.create_connection(("api.elevenlabs.io", 443), timeout=3).close()
        yaz("PASS", "internet var (ElevenLabs/edge-tts erişilebilir)")
    except OSError:
        yaz("UYARI", "internet yok — cache'teki sesler normal çalar, cache dışı replikler "
                     "Piper (çevrimdışı) sesiyle okunur")


def main() -> int:
    print(f"AICAN sağlık kontrolü · {ROOT}")
    kontrol_python()
    kontrol_vcredist()
    kontrol_paketler()
    kontrol_ffmpeg()
    kontrol_dosyalar()
    kontrol_veri()
    cfg = config_yukle()
    kontrol_gpu(cfg)
    if cfg:
        kontrol_piper(cfg)
        kontrol_tts_cache(cfg)
        kontrol_ollama(cfg)
        kontrol_port(cfg)
    kontrol_whisper(cfg)
    kontrol_ses_aygitlari()
    kontrol_internet()

    print(f"\nSONUÇ: {_SONUC['PASS']} PASS · {_SONUC['UYARI']} UYARI · {_SONUC['HATA']} HATA")
    if _SONUC["HATA"]:
        print("Sergiye ÇIKMAYIN — yukarıdaki HATA satırlarını giderin.")
        return 1
    if _SONUC["UYARI"]:
        print("Hazır (uyarıları gözden geçirin).")
    else:
        print("Her şey hazır ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
