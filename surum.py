"""Urun kimligi ve surum numarasi — TEK KAYNAK.

Surum bilgisi uc yerde birden gorunur:
    1. EXE'nin Windows ozellikleri (Nuitka --product-version / --file-version)
    2. Kurucu dosya adi ve "Program Ekle/Kaldir" kaydi (Inno Setup, /D ile gecer)
    3. Teslim ZIP'inin adi
Ucu de burayi okur. Elle uc yerde guncellemek, birinde unutmak demekti:
musteriye "0.9.0" yazan bir kurucudan "0.8.0" damgali EXE cikardi.

SURUM ARTIRMA: ilk gercek musteri teslimi 1.0.0'dir. 0.9.x, teslim oncesi
kendi test kurulumlarini isaretler. Icerik paketi surumu (lisans.PAKET_NO)
BUNDAN AYRIDIR: o yalniz web.pak anahtari dondugunde artar.
"""

from __future__ import annotations

SURUM = "0.9.0"
URUN_ADI = "Aican"
SIRKET = "Luden Studio"
ACIKLAMA = f"{URUN_ADI} — Konya Bilim Merkezi yapay zeka sergisi"

# Windows kaynak tablosu 4 haneli sayisal surum ister (a.b.c.d). SURUM'un
# uc hanesine build hanesi olarak 0 eklenir; ayri bir sabit tutulmaz ki
# ikisi ayrisamasin.
DOSYA_SURUMU = SURUM + ".0"

# Kurucu ciktisinin adi: Aican-Kurulum-0.9.0.exe (ve ayni adla .zip/.sha256)
KURUCU_ADI = f"{URUN_ADI}-Kurulum-{SURUM}"
