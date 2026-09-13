"""Basit dosya tabanli WAV onbellegi.

Anahtar = (ses, jest_id, yogunluk, metin) -> sha1. Sik tekrar eden cumleler
(selamlama vb.) bir kez uretilir, sonra aninda servis edilir; boylece hem gecikme
hem CPU yuku duser. Dosya sayisi limiti asilinca en eski (mtime) dosyalar silinir.

IKI DIZIN: `dir` yazilabilir (kullanici verisi), `seed_dir` SALT OKUNUR tohum
(kuruluma gomulmus, onceden uretilmis ElevenLabs parcalari). Okuma once
yazilabilir dizine, isabet yoksa tohuma bakar; yazma ve eviction tohuma HIC
dokunmaz. Boylece 6490 parcalik onbellek EXE'nin yaninda YERINDE okunur
(%LOCALAPPDATA%'ya 900 MB kopyalanmaz) ve eviction onu yiyemez.
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path


class WavCache:
    def __init__(self, cache_dir, max_files: int = 500, enabled: bool = True,
                 seed_dir=None) -> None:
        self.dir = Path(cache_dir)
        self.seed_dir = Path(seed_dir) if seed_dir else None
        # Tohum yazilabilir dizinin kendisiyse (kaynaktan calisma) yok say —
        # ayni dizini iki kez aramanin anlami yok.
        if self.seed_dir is not None:
            try:
                if self.seed_dir.resolve() == self.dir.resolve():
                    self.seed_dir = None
            except OSError:
                pass
        self.max_files = int(max_files)
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def make_key(self, text: str, jest_id, yogunluk, voice: str) -> str:
        raw = "\x1f".join([
            str(voice),
            str(jest_id or ""),
            f"{float(yogunluk):.2f}",
            (text or "").strip(),
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def get(self, key: str):
        if not self.enabled:
            return None
        adaylar = [self.dir / f"{key}.wav"]
        if self.seed_dir is not None:
            adaylar.append(self.seed_dir / f"{key}.wav")
        for f in adaylar:
            try:
                if f.exists():
                    return f.read_bytes()
            except OSError:
                continue
        return None

    def put(self, key: str, data: bytes) -> None:
        """YALNIZ yazilabilir dizine yazar. Tohumda zaten varsa hic yazmaz —
        ayni parcanin ikinci kopyasi diski sisirir ve eviction'i tetikler."""
        if not self.enabled or not data:
            return
        if self.seed_dir is not None and (self.seed_dir / f"{key}.wav").exists():
            return
        f = self.dir / f"{key}.wav"
        try:
            f.write_bytes(data)
        except OSError:
            return
        self._maybe_evict()

    def _maybe_evict(self) -> None:
        """Yalniz yazilabilir dizini budar; tohum dizini sayilmaz ve silinmez."""
        with self._lock:
            files = sorted(self.dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
            while len(files) > self.max_files:
                old = files.pop(0)
                try:
                    old.unlink()
                except OSError:
                    pass
