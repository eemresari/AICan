"""Tek yerden yol cozumleme: paket icerigi (salt okunur) vs kullanici verisi (yazilabilir).

Kaynaktan calisirken ikisi de depo kokudur ve BUGUNKU DAVRANIS AYNEN korunur
(config orchestrator/config.json'da, loglar <depo>/logs, TTS onbellegi
orchestrator/tts/cache, tarayici profili <depo>/.tarayici_profili).
DONDURULMUS (Nuitka) build'de ayrisirlar ve ayrismak ZORUNDADIR:

  * Paket icerigi EXE'nin yanindaki dizindedir ve salt okunur kabul edilir:
    `assets/`, `lisans_web/`, `web.pak`, tohum `config.json`.
  * Kullanici verisi `%LOCALAPPDATA%\\Aican` altindadir: `config.json`, `logs/`,
    `tts/cache/`, `.tarayici_profili/`, `elevenlabs_usage.json`, `aktivasyon.dat`.
    Bunlar calisma zamaninda YAZILIR; Program Files'a kurulu EXE'nin yanina
    yazilamazlar.

`kaynak_oku(rel)` simi: `ai/*.json`, `ai/system_prompt.txt` ve `web/` icerigi
dondurulmus build'de diske HIC yazilmaz — web.pak'tan cozulup `PAKET` sozlugune
konur ve buradan okunur. Kaynaktan calisirken `PAKET` None'dir, dosya diskten
okunur. Tum yukleyiciler (game_engine, llm_bridge, word_llm, tts, web_server)
bu simden gecer; baska hicbir yerde `ai/` yolu kurulmaz.

Eskiden her modul yolunu `__file__`'a gore kendi hesapliyordu. Dondurulmus
build'de `__file__` cikarma dizinini gosterir; oraya yazilan config bir sonraki
acilista Program Files'ta yazma hatasi verir. Tek giris noktasi bu dosyadir.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Optional

# Nuitka derlenmis her module `__compiled__` ekler; PyInstaller `sys.frozen`
# kullanir. Ikisini de taniyoruz ki derleyici degisirse yollar sessizce yanlis
# yere kaymasin.
FROZEN = ("__compiled__" in globals()) or bool(getattr(sys, "frozen", False))

_APP_NAME = "Aican"

# Depo koku: bu dosya orchestrator/ icinde, bir ustu kok.
_SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Icerik paketi (web.pak) cozulunce buraya konur: {"ai/gestures.json": b"...", ...}.
# None = kaynaktan calisiyoruz, diskten oku. Anahtarlar depo kokune gore POSIX
# ("ai/atasozu50.json", "web/app.js"). G3'te web_paket.py doldurur.
PAKET: Optional[dict] = None

# ensure_seeded'in paketten veri kokune kopyaladigi dosyalar. `aktivasyon.dat`
# BILEREK YOK: makineye HMAC ile baglidir, kopyalanmasi anlamsiz bir "baska
# bilgisayar" hatasi uretir.
SEED_FILES = ("config.json",)

# Yazilan dosyalarin veri kokune gore konumu. Kaynak yerlesimi = bugunku
# gercek konumlar (degistirilmez); duz yerlesim = %LOCALAPPDATA%\Aican altinda
# EXE icin. Anahtarlar asagidaki *_path()/_dir() fonksiyonlarina karsilik gelir.
_KAYNAK_YERLESIM = {
    "config.json": "orchestrator/config.json",
    "logs": "logs",
    "tts_cache": "orchestrator/tts/cache",
    "tarayici_profili": ".tarayici_profili",
    "elevenlabs_usage.json": "orchestrator/tts/elevenlabs_usage.json",
    "aktivasyon.dat": "aktivasyon.dat",
}
_DUZ_YERLESIM = {
    "config.json": "config.json",
    "logs": "logs",
    "tts_cache": "tts/cache",
    "tarayici_profili": ".tarayici_profili",
    "elevenlabs_usage.json": "elevenlabs_usage.json",
    "aktivasyon.dat": "aktivasyon.dat",
}


def resource_root() -> str:
    """Salt okunur paket icerigi koku (assets/, lisans_web/, web.pak, tohum config)."""
    if FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)      # PyInstaller onefile
        if meipass:
            return meipass
        return os.path.dirname(os.path.abspath(sys.executable))   # Nuitka standalone
    return _SOURCE_ROOT


def _veri_koku_depo_mu() -> bool:
    """Veri koku depo kokunun kendisi mi? Evetse kaynak yerlesimi kullanilir
    (orchestrator/config.json vb.); degilse duz yerlesim."""
    return not FROZEN and not os.environ.get("AICAN_DATA_ROOT")


def data_root() -> str:
    """Yazilabilir kullanici durumunun koku.

    `AICAN_DATA_ROOT` ortam degiskeni her seyi ezer — testler ve "tasinabilir
    kurulum" (her sey EXE'nin yaninda) senaryosu bunu kullanir.
    """
    override = os.environ.get("AICAN_DATA_ROOT")
    if override:
        return os.path.abspath(override)
    if FROZEN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, _APP_NAME)
    return _SOURCE_ROOT


def _veri_yolu(ad: str) -> str:
    yerlesim = _KAYNAK_YERLESIM if _veri_koku_depo_mu() else _DUZ_YERLESIM
    return os.path.normpath(os.path.join(data_root(), yerlesim[ad]))


def config_path() -> str:
    """Yerel, makineye ozel config.json (test modu / model secimi buraya yazar)."""
    return _veri_yolu("config.json")


def seed_source_path(name: str) -> str:
    """Tohum dosyanin paketteki kaynagi. Kaynaktan calisirken hedefle AYNI dosya
    (orchestrator/config.json); dondurulmus build'de EXE'nin yanindaki kopya."""
    if _veri_koku_depo_mu():
        return _veri_yolu(name)
    return os.path.join(resource_root(), name)


def log_dir() -> str:
    return _veri_yolu("logs")


def session_log_path(cfg_value: Optional[str] = None) -> str:
    """config.json `session_log_path` (orchestrator/'a goreli, ornek
    "../logs/session.log"). Mutlak yol aynen; kaynakta bugunku cozumleme
    (orchestrator/ tabanli); dondurulmus build'de yalniz dosya adi alinir ve
    veri kokundeki logs/ altina konur."""
    cfg_value = cfg_value or "../logs/session.log"
    if os.path.isabs(cfg_value):
        return os.path.normpath(cfg_value)
    if _veri_koku_depo_mu():
        return os.path.normpath(os.path.join(_SOURCE_ROOT, "orchestrator", cfg_value))
    return os.path.join(log_dir(), os.path.basename(cfg_value))


def stt_debug_dir() -> str:
    """whisper_debug_save_audio teshis kayitlari."""
    return os.path.join(log_dir(), "stt_debug")


def tts_cache_dir() -> str:
    return _veri_yolu("tts_cache")


def tts_cache_seed_dir() -> Optional[str]:
    """Kuruluma gomulmus, SALT OKUNUR ses onbellegi tohumu (EXE yanindaki
    `tts/cache`, ~900 MB / 6490 onceden uretilmis ElevenLabs parcasi).

    WavCache once yazilabilir dizine, isabet yoksa buraya bakar; buraya HIC
    yazmaz ve eviction burayi silmez. Kaynaktan calisirken None doner: orada
    yazilabilir dizin zaten onbellegin kendisidir (orchestrator/tts/cache).
    """
    if not FROZEN:
        return None
    return os.path.join(resource_root(), "tts", "cache")


def browser_profile_dir() -> str:
    """Kiosk tarayicisinin --user-data-dir'i."""
    return _veri_yolu("tarayici_profili")


def elevenlabs_usage_path() -> str:
    """ElevenLabs aylik kredi sayaci (CreditGuard yazar)."""
    return _veri_yolu("elevenlabs_usage.json")


def activation_path() -> str:
    """Lisans aktivasyon kaydi (lisans_durum.py yazar/okur).

    TOHUMLANMAZ ve paket iceriginde YOKTUR: bu makineye HMAC ile baglidir,
    baska kurulumdan kopyalanmasi anlamsiz bir "baska bilgisayar" hatasi
    uretir. Veri kokunde durur ki Program Files'a kurulu EXE yazabilsin.
    """
    return _veri_yolu("aktivasyon.dat")


def ensure_seeded() -> None:
    """Veri kokunu ve logs/ dizinini ac; SEED_FILES'i paketten kopyala.

    Hedef zaten varsa DOKUNULMAZ (kullanicinin config'i ezilmez). Kaynaktan
    calisirken kaynak == hedef oldugundan kopyalama yapilmaz. Tohum paketten
    cikmamissa sessizce gecilir — load_config kendi hatasini verir.
    """
    try:
        os.makedirs(data_root(), exist_ok=True)
        os.makedirs(log_dir(), exist_ok=True)
    except OSError as exc:
        print(f"[paths] veri koku acilamadi ({exc!r}); devam ediliyor.")
        return
    for name in SEED_FILES:
        hedef = _veri_yolu(name)
        kaynak = seed_source_path(name)
        if os.path.isfile(hedef):
            continue
        if os.path.normcase(os.path.abspath(kaynak)) == os.path.normcase(os.path.abspath(hedef)):
            continue
        if not os.path.isfile(kaynak):
            print(f"[paths] tohum yok: '{kaynak}'")
            continue
        try:
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            shutil.copy2(kaynak, hedef)
            print(f"[paths] '{hedef}' tohumlandi.")
        except OSError as exc:
            print(f"[paths] '{name}' tohumlanamadi ({exc!r}).")


# --- icerik simi -----------------------------------------------------------

def kaynak_rel(cfg_rel: str) -> str:
    """config.json'daki orchestrator/'a goreli yolu ("../ai/system_prompt.txt")
    depo kokune goreli POSIX pakete anahtarina cevirir ("ai/system_prompt.txt").
    Mutlak yol aynen doner (diskten okunur)."""
    if os.path.isabs(cfg_rel):
        return cfg_rel
    duz = os.path.normpath(os.path.join("orchestrator", cfg_rel))
    return duz.replace("\\", "/")


def kaynak_oku(rel: str) -> bytes:
    """Paket icerigini oku: PAKET doluysa bellekten, degilse resource_root()/rel
    diskten. `rel` depo kokune gore POSIX ("ai/atasozu50.json"). Mutlak yol
    (test enjeksiyonu) her zaman diskten okunur — pakette olamaz."""
    rel = str(rel)
    if os.path.isabs(rel):
        with open(rel, "rb") as f:
            return f.read()
    anahtar = rel.replace("\\", "/")
    if PAKET is not None:
        try:
            return PAKET[anahtar]
        except KeyError:
            raise FileNotFoundError(f"pakette yok: {anahtar}") from None
    with open(os.path.join(resource_root(), *anahtar.split("/")), "rb") as f:
        return f.read()
