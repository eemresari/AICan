#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Donanim tespiti — kur.py ve saglik_kontrol.py ortak kullanir.

Tek isi: makinede hangi NVIDIA karti var, ne kadar VRAM'i var, surucusu
yeterli mi — ve buna gore HANGI CONFIG PROFILI kullanilmali.

Neden ayri dosya: profil secimi artik elle degil otomatik. Kurulum sirasinda
kur.py karti gorup dogru profili seciyor; sergi gunu saglik_kontrol.py AYNI
mantikla "config'in varsaydigi kart bu makinede gercekten var mi" diye
dogruluyor. Iki yerde kopya mantik olsaydi biri guncellenip digeri unutulurdu.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ——— Profiller —————————————————————————————————————————————
# (dosya adi, insan okunur ad, min VRAM MB)
PROFILLER = {
    "sergi5090": ("config.sergi5090.json", "Yeni sergi PC'si — RTX 5090 32 GB", 24000),
    "sergi":     ("config.sergi.json",     "Eski sergi PC'si — GTX 1660 Ti 6 GB", 5000),
    "laptop":    ("config.json",           "Gelistirme laptopu — RTX 3050 Ti 4 GB", 0),
}

# CUDA 12.8 (Blackwell/sm_120 icin sart) Windows'ta en az 570.xx surucu ister.
MIN_SURUCU_BLACKWELL = 570.0
# CUDA 12 calisma kutuphaneleri icin genel taban.
MIN_SURUCU_CUDA12 = 525.0


class Gpu:
    """nvidia-smi'den okunan tek kart."""

    def __init__(self, ad: str, vram_mb: int, surucu: str, compute_cap: str) -> None:
        self.ad = ad
        self.vram_mb = vram_mb
        self.surucu = surucu
        self.compute_cap = compute_cap

    @property
    def vram_gb(self) -> float:
        return self.vram_mb / 1024

    @property
    def surucu_sayi(self) -> float:
        """'572.83' -> 572.83; okunamazsa 0.0 (kontrolleri patlatma)."""
        m = re.match(r"(\d+(?:\.\d+)?)", self.surucu or "")
        return float(m.group(1)) if m else 0.0

    @property
    def blackwell(self) -> bool:
        """RTX 50 serisi / sm_120 mi?

        Once compute capability'ye bakariz (kesin olcut). Eski nvidia-smi
        surumleri compute_cap sutununu desteklemez — o zaman model adindan
        cikarim yapariz ("RTX 5090", "RTX 5080", ... ama "RTX 590" degil)."""
        try:
            if self.compute_cap and float(self.compute_cap) >= 12.0:
                return True
        except ValueError:
            pass
        return bool(re.search(r"RTX\s*50[6-9]0", self.ad, re.IGNORECASE))

    def __str__(self) -> str:
        parca = [self.ad, f"{self.vram_gb:.0f} GB VRAM", f"surucu {self.surucu}"]
        if self.compute_cap:
            parca.append(f"compute {self.compute_cap}")
        return "  ·  ".join(parca)


def gpu_listesi() -> list:
    """Makinedeki NVIDIA kartlari. nvidia-smi yoksa/calismazsa bos liste."""
    alanlar = "name,memory.total,driver_version,compute_cap"
    try:
        r = subprocess.run(
            ["nvidia-smi", f"--query-gpu={alanlar}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        # compute_cap eski surumlerde yok — onsuz tekrar dene.
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return []
        if r.returncode != 0:
            return []
    kartlar = []
    for satir in (r.stdout or "").strip().splitlines():
        p = [s.strip() for s in satir.split(",")]
        if len(p) < 3:
            continue
        try:
            vram = int(float(p[1]))
        except ValueError:
            vram = 0
        kartlar.append(Gpu(p[0], vram, p[2], p[3] if len(p) > 3 else ""))
    return kartlar


def birincil_gpu():
    """En cok VRAM'li kart (tek kartli makinede tek kart). Yoksa None."""
    kartlar = gpu_listesi()
    return max(kartlar, key=lambda g: g.vram_mb) if kartlar else None


def profil_oner(gpu, orch_dir: Path) -> str:
    """Karta gore profil anahtari. GPU yoksa en muhafazakar profil.

    Olcut VRAM: 24 GB ustu = 5090 sinifi, 5 GB ustu = eski sergi PC'si.
    Model adina degil VRAM'e bakiyoruz ki 5090 disi buyuk kartlar (4090, 5080
    24 GB vb.) da dogru profile dussun."""
    def var(anahtar: str) -> bool:
        return (orch_dir / PROFILLER[anahtar][0]).is_file()

    if gpu is None:
        return "laptop"
    if gpu.vram_mb >= PROFILLER["sergi5090"][2] and var("sergi5090"):
        return "sergi5090"
    if gpu.vram_mb >= PROFILLER["sergi"][2] and var("sergi"):
        return "sergi"
    return "laptop"


def surucu_uyarisi(gpu) -> str:
    """Surucu bu kart icin yeterli mi? Sorun yoksa bos dize."""
    if gpu is None:
        return ""
    s = gpu.surucu_sayi
    if s <= 0:
        return ""      # okunamadi — yanlis alarm verme
    if gpu.blackwell and s < MIN_SURUCU_BLACKWELL:
        return (f"NVIDIA surucusu {gpu.surucu} — RTX 50 serisi icin CUDA 12.8 gerekiyor, "
                f"bu da >= {MIN_SURUCU_BLACKWELL:.0f} surucu ister. GPU'da ses tanima "
                f"calismaz. Guncelle: https://www.nvidia.com/download/index.aspx")
    if s < MIN_SURUCU_CUDA12:
        return (f"NVIDIA surucusu {gpu.surucu} cok eski — CUDA 12 icin en az "
                f"{MIN_SURUCU_CUDA12:.0f} gerekli. GPU'da ses tanima calismaz.")
    return ""


def config_uyumu(gpu, cfg: dict) -> list:
    """Config'teki GPU varsayimlari bu makineye uyuyor mu? Uyari metinleri.

    En kritigi Blackwell + int8: config.sergi.json'i (int8_float16) yanlislikla
    5090'a kopyalamak sergiyi CPU ses tanimaya dusurur — calisir gorunur ama
    her cumle 3-4 saniye gecikir. Bunu kurulumda yakalamak sahada yakalamaktan
    ucuz."""
    uyari = []
    if gpu is None:
        if cfg.get("whisper_device") == "cuda":
            uyari.append("config whisper_device=cuda diyor ama NVIDIA karti bulunamadi — "
                         "ses tanima CPU'ya dusecek (yavas).")
        return uyari
    ct = str(cfg.get("whisper_compute_type", ""))
    if gpu.blackwell and "int8" in ct:
        uyari.append(f"whisper_compute_type='{ct}' — {gpu.ad} (Blackwell/sm_120) INT8 "
                     f"desteklemiyor, CUBLAS_STATUS_NOT_SUPPORTED verir. 'float16' yap "
                     f"(config.sergi5090.json boyle).")
    return uyari


def model_vram_ihtiyaci(model: str) -> float:
    """Ollama model etiketinden kabaca GB agirlik tahmini (bilinmiyorsa 0).

    Kurulumda "bu model bu karta sigar mi" uyarisi icin — kesinlik degil,
    buyukluk mertebesi yeterli."""
    tablo = {
        "gemma4:26b": 18.0, "gemma4:31b": 20.0, "gemma4:12b": 7.6,
        "qwen3.5:35b-a3b": 24.0, "qwen3.5:27b": 17.0, "qwen3.5:9b": 6.6,
        "gemma3:27b": 17.0, "gemma3:12b": 8.1, "gemma3:4b": 3.3,
        "qwen3:4b-instruct-2507-q4_K_M": 2.6, "qwen3:30b-a3b": 19.0,
    }
    return tablo.get(model.strip(), 0.0)


if __name__ == "__main__":   # elle bakmak icin: python kurulum/donanim.py
    g = birincil_gpu()
    print(g if g else "NVIDIA karti bulunamadi (nvidia-smi yok ya da surucu kurulu degil)")
    if g:
        print(f"  Blackwell (sm_120): {'EVET' if g.blackwell else 'hayir'}")
        u = surucu_uyarisi(g)
        if u:
            print(f"  UYARI: {u}")
    print(f"  Onerilen profil: {profil_oner(g, Path(__file__).resolve().parent.parent / 'orchestrator')}")
