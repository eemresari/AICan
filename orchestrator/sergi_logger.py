"""Sergi ziyaretci logu — sergiyi gelistirmek icin ziyaretci bazli olcum.

session_logger'dan (teknik/AI oturum logu) AYRI tutulur: burada birim
"ziyaretci"dir. Her ziyaretci icin bir kayit tutulur ve ziyaret bitince
iki dosyaya yazilir:

  logs/sergi/ziyaretciler.jsonl  -> makine okunur (analiz/istatistik icin)
  logs/sergi/sergi_rapor.txt     -> insan okunur ozet blok (gorevli/gelistirici)

Tutulanlar (ziyaretci basina):
  - ne kadar oynadi (toplam sure + son gercek etkinlige kadar aktif sure)
  - hangi oyunlari secti/oynadi, "basla" diyip gercekten basladi mi
  - skor (dogru/toplam, oyun basina + ziyaret toplami)
  - yarida birakti mi (terk_edildi / yarim_birakildi / ziyaret bitiminde acik kalan)
  - kac defa anlamsiz cevap verdi (menude anlasilmadi, hazir ekraninda
    'basla' anlasilmadi, STT bos "duyamadim", TTS yankisi atildi)
  - soru bazinda dogru/yanlis/zaman-asimi sayilari
  - STT kullanim olcumleri (deneme, kurtarma turu, ortalama sure, konusulan saniye)
  - test modunda sohbet deneme sayisi

TASARIM KURALI: loglama sergiyi ASLA durdurmaz — tum public metotlar
hatalari yutar; ziyaretci acik degilken gelen olaylar sessizce yok sayilir.
Ziyaretci yasam dongusunu web_server yonetir (session/new greet = baslat,
attract/idle_reset/end_to_eyes = bitir); oyun olaylarini game_engine gonderir.
"""
from __future__ import annotations

import functools
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("sergi_logger")

# Ziyaret bitiminde hala acik olan oyunun sonucu (oyun kendi bitisini
# gormedi = ziyaretci oyunun ortasinda gitti / attract devraldi).
_SONUC_YARIM_KALDI = "yarim_kaldi"
# "Yarida birakti" sayilan sonuclar (bitti disinda her sey).
_YARIM_SONUCLAR = ("terk_edildi", "yarim_birakildi", _SONUC_YARIM_KALDI)


def _safe(fn):
    """Public metot koruyucusu: loglama hatasi sergiyi asla durdurmasin."""
    @functools.wraps(fn)
    def sarici(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:  # noqa: BLE001 — gozlem kodu akisi bozamaz
            log.debug("Sergi logu hatasi (%s): %s", fn.__name__, e)
            return None
    return sarici


class SergiLogger:
    SEP = "=" * 72
    SEP_INCE = "-" * 72

    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.jsonl_path = self.log_dir / "ziyaretciler.jsonl"
        self.rapor_path = self.log_dir / "sergi_rapor.txt"
        self._lock = threading.Lock()
        self._ziyaretci: dict | None = None
        self._sayac = 0
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            if self.jsonl_path.exists():
                with self.jsonl_path.open("r", encoding="utf-8") as f:
                    self._sayac = sum(1 for line in f if line.strip())
        except OSError as e:
            log.warning("Sergi log dizini hazirlanamadi: %s", e)

    # ---------- Yasam dongusu (web_server cagirir) ----------
    @_safe
    def visitor_start(self, reason: str = "greet") -> None:
        """Yeni ziyaretci selami geldi. Acik ziyaretci varsa once kapatilir."""
        with self._lock:
            if self._ziyaretci is not None:
                self._bitir_kilitli("yeni_ziyaretci")
            self._sayac += 1
            self._ziyaretci = {
                "no": self._sayac,
                "baslangic": datetime.now().isoformat(timespec="seconds"),
                "baslangic_mono": time.monotonic(),
                "son_aktivite_mono": time.monotonic(),
                "baslangic_nedeni": reason,
                "oyunlar": [],
                "anlamsiz": {"menu": 0, "hazir": 0, "duyamadi": 0, "yanki": 0},
                "anlamsiz_ornek": [],   # gelistirme icin: anlasilamayan ilk sozler
                "stt": {"deneme": 0, "bos": 0, "yanki": 0, "kurtarma": 0,
                        "toplam_ms": 0, "konusma_sn": 0.0},
                "sohbet_denemesi": 0,
                # Yasakli girdi: yalniz SAYI ve kategori tutulur; sozun kendisi
                # HICBIR loga yazilmaz (ekrana da cikmadi).
                "yasakli": {"toplam": 0, "agir": 0, "kategoriler": {}},
            }
        log.info("Sergi: ziyaretci #%d basladi [neden=%s]", self._sayac, reason)

    @_safe
    def visitor_end(self, reason: str) -> None:
        """Ziyaretci gitti (attract/idle_reset/end_to_eyes vb.) — kaydi yaz."""
        with self._lock:
            self._bitir_kilitli(reason)

    @_safe
    def close(self) -> None:
        """Sunucu kapanisi: acik ziyaretci kaybolmasin."""
        with self._lock:
            self._bitir_kilitli("sunucu_kapandi")

    # ---------- Oyun olaylari (game_engine cagirir) ----------
    @_safe
    def game_select(self, oyun: str, tur: str | None = None) -> None:
        """Menuden oyun secildi (kurallar anlatiliyor; henuz baslamadi)."""
        with self._lock:
            z = self._ziyaretci
            if z is None:
                return
            self._acik_oyunu_kapat_kilitli(z)
            z["oyunlar"].append({
                "oyun": oyun,                 # "quiz" | "kelime"
                "tur": tur,                   # eszit | atasozu | dogruyanlis | None
                "secim": datetime.now().isoformat(timespec="seconds"),
                "basladi": False,             # "basla" dedi mi
                "sonuc": None,                # bitti | terk_edildi | yarim_* | None=acik
                "dogru": None, "toplam": None, "skor": None,
                "soru_dogru": 0, "soru_yanlis": 0, "soru_timeout": 0,
            })
            z["son_aktivite_mono"] = time.monotonic()

    @_safe
    def game_begin(self) -> None:
        """'Basla' dendi — sorular/turlar gercekten basladi."""
        with self._lock:
            o = self._acik_oyun_kilitli()
            if o is not None:
                o["basladi"] = True
                self._ziyaretci["son_aktivite_mono"] = time.monotonic()

    @_safe
    def game_end(self, sonuc: str, skor: str | None = None,
                 dogru: int | None = None, toplam: int | None = None) -> None:
        """Oyun kapandi. sonuc: bitti | terk_edildi | yarim_birakildi."""
        with self._lock:
            o = self._acik_oyun_kilitli()
            if o is None:
                return
            o["sonuc"] = sonuc
            o["skor"] = skor
            o["dogru"] = dogru
            o["toplam"] = toplam

    @_safe
    def question(self, outcome: str) -> None:
        """Soru sonucu: 'dogru' | 'yanlis' | 'timeout'."""
        with self._lock:
            o = self._acik_oyun_kilitli()
            if o is None:
                return
            alan = {"dogru": "soru_dogru", "yanlis": "soru_yanlis",
                    "timeout": "soru_timeout"}.get(outcome)
            if alan:
                o[alan] += 1
            if outcome != "timeout":
                self._ziyaretci["son_aktivite_mono"] = time.monotonic()

    @_safe
    def anlamsiz(self, yer: str, text: str = "") -> None:
        """Anlasilamayan girdi. yer: 'menu' | 'hazir' (STT bos/yanki stt()'den)."""
        with self._lock:
            z = self._ziyaretci
            if z is None:
                return
            if yer in z["anlamsiz"]:
                z["anlamsiz"][yer] += 1
            if text and len(z["anlamsiz_ornek"]) < 20:
                z["anlamsiz_ornek"].append(f"{yer}: {text[:60]}")

    # ---------- Ses/sohbet olaylari (web_server cagirir) ----------
    @_safe
    def stt(self, bos: bool, yanki: bool = False, kurtarma: bool = False,
            stt_ms: int = 0, ses_sn: float = 0.0) -> None:
        """Her /api/transcribe sonucu. bos=metin cikmadi ("duyamadim")."""
        with self._lock:
            z = self._ziyaretci
            if z is None:
                return
            s = z["stt"]
            s["deneme"] += 1
            s["toplam_ms"] += int(stt_ms)
            s["konusma_sn"] = round(s["konusma_sn"] + float(ses_sn or 0.0), 1)
            if kurtarma:
                s["kurtarma"] += 1
            if bos:
                s["bos"] += 1
                if yanki:
                    s["yanki"] += 1
                    z["anlamsiz"]["yanki"] += 1
                else:
                    z["anlamsiz"]["duyamadi"] += 1
            else:
                z["son_aktivite_mono"] = time.monotonic()

    @_safe
    def yasakli(self, kategori: str, severity: int = 5) -> None:
        """Yasakli kelime filtresi bir sozu engelledi (web_server cagirir).
        Sozun KENDISI kaydedilmez — gorevli icin sayi ve kategori yeter."""
        with self._lock:
            z = self._ziyaretci
            if z is None:
                return
            y = z.setdefault("yasakli", {"toplam": 0, "agir": 0, "kategoriler": {}})
            y["toplam"] += 1
            if int(severity) >= 4:
                y["agir"] += 1
            k = str(kategori or "bilinmiyor")
            y["kategoriler"][k] = y["kategoriler"].get(k, 0) + 1
            z["son_aktivite_mono"] = time.monotonic()

    @_safe
    def sohbet(self) -> None:
        """Test modunda oyun disi sohbet denemesi (oyuna yonlendirildi)."""
        with self._lock:
            z = self._ziyaretci
            if z is None:
                return
            z["sohbet_denemesi"] += 1
            z["son_aktivite_mono"] = time.monotonic()

    @_safe
    def aktivite(self) -> None:
        """Gercek ziyaretci etkinligi (panel butonu vb.) — aktif sureyi tazeler."""
        with self._lock:
            if self._ziyaretci is not None:
                self._ziyaretci["son_aktivite_mono"] = time.monotonic()

    # ---------- Ic isler (kilit CAGIRANDA) ----------
    def _acik_oyun_kilitli(self) -> dict | None:
        z = self._ziyaretci
        if z is None or not z["oyunlar"]:
            return None
        o = z["oyunlar"][-1]
        return o if o["sonuc"] is None else None

    def _acik_oyunu_kapat_kilitli(self, z: dict) -> None:
        """Sonucu gelmemis onceki oyun varsa 'yarim_kaldi' say."""
        if z["oyunlar"] and z["oyunlar"][-1]["sonuc"] is None:
            z["oyunlar"][-1]["sonuc"] = _SONUC_YARIM_KALDI

    def _bitir_kilitli(self, reason: str) -> None:
        z = self._ziyaretci
        if z is None:
            return
        self._ziyaretci = None
        self._acik_oyunu_kapat_kilitli(z)

        simdi = time.monotonic()
        bas_mono = z.pop("baslangic_mono")
        son_akt_mono = z.pop("son_aktivite_mono")
        sure_sn = int(simdi - bas_mono)
        # Aktif sure: son gercek etkinlige kadar (attract 60 sn bosluk beklendigi
        # icin toplam sure her zaman ~1 dk sismis olur; gercek oyun suresi budur).
        aktif_sn = max(0, min(int(son_akt_mono - bas_mono), sure_sn))

        oyunlar = z["oyunlar"]
        top_dogru = sum(o["dogru"] or 0 for o in oyunlar)
        top_soru = sum(o["toplam"] or 0 for o in oyunlar)
        yarim = [o for o in oyunlar if o["sonuc"] in _YARIM_SONUCLAR]
        an = z["anlamsiz"]

        kayit = dict(z)
        kayit.update({
            "bitis": datetime.now().isoformat(timespec="seconds"),
            "bitis_nedeni": reason,
            "sure_sn": sure_sn,
            "aktif_sure_sn": aktif_sn,
            "skor_toplam": {"dogru": top_dogru, "toplam": top_soru},
            "yarida_birakti": bool(yarim),
            "anlamsiz_toplam": sum(an.values()),
        })

        try:
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("Sergi jsonl yazilamadi: %s", e)
        try:
            self._rapor_yaz(kayit)
        except OSError as e:
            log.warning("Sergi raporu yazilamadi: %s", e)
        log.info("Sergi: ziyaretci #%d bitti [neden=%s, sure=%ds, oyun=%d, skor=%d/%d]",
                 kayit["no"], reason, sure_sn, len(oyunlar), top_dogru, top_soru)

    def _rapor_yaz(self, k: dict) -> None:
        def _sure(sn: int) -> str:
            dk, s = divmod(int(sn), 60)
            return f"{dk} dk {s} sn" if dk else f"{s} sn"

        satirlar = [self.SEP,
                    f"ZIYARETCI #{k['no']} — {k['baslangic']} → {k['bitis']}",
                    self.SEP_INCE,
                    f"Sure:               {_sure(k['sure_sn'])} (aktif {_sure(k['aktif_sure_sn'])})",
                    f"Bitis nedeni:       {k['bitis_nedeni']}"]

        if k["oyunlar"]:
            satirlar.append("Oynanan oyunlar:")
            for o in k["oyunlar"]:
                ad = o["tur"] or o["oyun"]
                skor = (f"{o['dogru']}/{o['toplam']}" if o["dogru"] is not None
                        else (o["skor"] or "-"))
                basla = "" if o["basladi"] else " (hic baslamadi)"
                satirlar.append(
                    f"  - {ad}: {o['sonuc']}{basla}, skor {skor} "
                    f"[dogru {o['soru_dogru']}, yanlis {o['soru_yanlis']}, "
                    f"sure-doldu {o['soru_timeout']}]")
        else:
            satirlar.append("Oynanan oyunlar:    YOK (oyuna hic girmedi)")

        st = k["skor_toplam"]
        an = k["anlamsiz"]
        stt = k["stt"]
        ort_stt = (stt["toplam_ms"] // stt["deneme"]) if stt["deneme"] else 0
        satirlar += [
            f"Yarida birakti:     {'EVET' if k['yarida_birakti'] else 'hayir'}",
            f"Skor toplam:        {st['dogru']} dogru / {st['toplam']} soru",
            f"Anlamsiz cevap:     {k['anlamsiz_toplam']} "
            f"(menu {an['menu']}, hazir {an['hazir']}, "
            f"duyamadi {an['duyamadi']}, yanki {an['yanki']})",
            f"Konusma denemesi:   {stt['deneme']} "
            f"(bos {stt['bos']}, kurtarma {stt['kurtarma']}, "
            f"toplam ses {stt['konusma_sn']} sn, ort. STT {ort_stt} ms)",
        ]
        if k["sohbet_denemesi"]:
            satirlar.append(f"Sohbet denemesi:    {k['sohbet_denemesi']} (oyuna yonlendirildi)")
        ya = k.get("yasakli") or {}
        if ya.get("toplam"):
            kats = ", ".join(f"{a} {s}" for a, s in
                             sorted(ya.get("kategoriler", {}).items(),
                                    key=lambda x: -x[1])[:4])
            satirlar.append(f"Yasakli girdi:      {ya['toplam']} engellendi "
                            f"(agir {ya.get('agir', 0)}) [{kats}]")
        if k["anlamsiz_ornek"]:
            satirlar.append("Anlasilamayan sozler:")
            satirlar += [f"  · {s}" for s in k["anlamsiz_ornek"]]
        satirlar.append("")

        with self.rapor_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(satirlar) + "\n")
