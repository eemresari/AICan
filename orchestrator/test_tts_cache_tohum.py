"""WavCache tohum (seed) dizini: kuruluma gomulmus 6490 parcalik ElevenLabs
onbellegi YERINDE okunur — kopyalanmaz, uzerine yazilmaz, eviction yiyemez.

2026-09-13: build.py `tts/cache`i EXE'ye hic paketlemiyordu; kurulu sergide
tek bir iyi parca yoktu ve her replik ucretsiz yedege dusuyordu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tts.cache import WavCache


def _cache(tmp_path, **kw):
    return WavCache(tmp_path / "yazilabilir", seed_dir=tmp_path / "tohum", **kw)


def _tohum_yaz(tmp_path, key, data=b"RIFFtohum"):
    d = tmp_path / "tohum"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.wav").write_bytes(data)


def test_tohumdan_okur(tmp_path):
    _tohum_yaz(tmp_path, "aaa")
    c = _cache(tmp_path)
    assert c.get("aaa") == b"RIFFtohum"


def test_yazilabilir_dizin_tohumu_ezer(tmp_path):
    """Ayni anahtar iki yerdeyse yazilabilir kopya once gelir (guncelleme yolu)."""
    _tohum_yaz(tmp_path, "aaa")
    c = _cache(tmp_path)
    (c.dir / "aaa.wav").write_bytes(b"RIFFyeni")
    assert c.get("aaa") == b"RIFFyeni"


def test_put_tohuma_YAZMAZ(tmp_path):
    c = _cache(tmp_path)
    c.put("bbb", b"RIFFyeni")
    assert (c.dir / "bbb.wav").is_file()
    assert not (tmp_path / "tohum" / "bbb.wav").exists()


def test_put_tohumda_VARSA_kopyalamaz(tmp_path):
    """Tohumda olan parcayi ikinci kez diske yazmak 900 MB'i ikiye katlardi."""
    _tohum_yaz(tmp_path, "ccc")
    c = _cache(tmp_path)
    c.put("ccc", b"RIFFyeni")
    assert not (c.dir / "ccc.wav").exists()
    assert c.get("ccc") == b"RIFFtohum"


def test_eviction_tohuma_DOKUNMAZ(tmp_path):
    """max_files asilinca yalniz yazilabilir dizin budanir; tohum sagkalir."""
    for i in range(5):
        _tohum_yaz(tmp_path, f"t{i}")
    c = _cache(tmp_path, max_files=2)
    for i in range(4):
        c.put(f"y{i}", b"RIFFyeni")
    assert len(list(c.dir.glob("*.wav"))) <= 2
    assert len(list((tmp_path / "tohum").glob("*.wav"))) == 5
    assert c.get("t0") == b"RIFFtohum"


def test_tohum_yoksa_eski_davranis(tmp_path):
    """seed_dir=None (kaynaktan calisma) — tek dizinli eski davranis aynen."""
    c = WavCache(tmp_path / "tek")
    assert c.seed_dir is None
    c.put("ddd", b"RIFF")
    assert c.get("ddd") == b"RIFF"
    assert c.get("yok") is None


def test_tohum_yazilabilir_dizinle_AYNIYSA_yok_sayilir(tmp_path):
    """Kaynaktan calismada ikisi ayni dizin olabilir; iki kez aranmasin."""
    d = tmp_path / "ayni"
    c = WavCache(d, seed_dir=d)
    assert c.seed_dir is None


def test_paths_tohum_kaynakta_None():
    """paths.tts_cache_seed_dir(): kaynaktan calisirken tohum YOK."""
    import paths
    assert paths.FROZEN is False
    assert paths.tts_cache_seed_dir() is None


def test_paths_tohum_frozende_resource_root(monkeypatch):
    import paths
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(paths, "resource_root", lambda: str(Path("C:/Program Files/Aican")))
    seed = paths.tts_cache_seed_dir()
    assert seed is not None
    assert Path(seed) == Path("C:/Program Files/Aican/tts/cache")
