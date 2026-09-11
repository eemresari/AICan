"""Aican'in lisans kapisi: urune ozel sabitler + dogrulama.

Bicimin kendisi lisans_bicim.py'dedir — o dosya Lisans Merkezi'nden BIREBIR
kopyalanir ve URUNE OZEL HICBIR SABIT TASIMAZ. Urune ozel olan her sey burada
durur; boylece kopya ayrismaz. (Ayrisirsa dagitilmis keyler dogrulanamaz hale
gelir ve bunu ilk musteri fark eder.)

EXE'DE YALNIZ ACIK ANAHTAR VARDIR: imzayi dogrulayabilir, URETEMEZ. Ozel
anahtar Lisans Merkezi'nin calistigi makinededir, bu depoda degil. Oyunun
icinde HIC key yoktur — EXE'yi parcalayan biri tek bir key cikaramaz.
"""

from __future__ import annotations

import lisans_bicim

URUN = "aican"

# Icerik anahtarinin surumu. Rotasyon gerekirse artirilir; eski lisanslar
# "eski surum icin uretilmis" mesajiyla reddedilir.
PAKET_NO = 1

# Ed25519 acik anahtar (32 bayt, hex). SIR DEGILDIR, depoya girer.
# Lisans Merkezi'ndeki "aican" cifti uretilirken yazdirilir (MERKEZ.bat ->
# Aican -> "Anahtar cifti uret"). YER TUTUCU KALDIGI SURECE hicbir gercek
# anahtar dogrulanamaz; tests/test_lisans.py bunu kilitler. (2026-09-11 dolduruldu)
ACIK_ANAHTAR_HEX = "b19a8d423024ffc8321456eee97c3bdd4605e1396b73ef31bff5f7a532a5f7a0"

# Hatalari burada disa ac: cagiran taraf lisans_bicim'i import etmek zorunda
# kalmasin, tek kapi olsun.
LisansHatasi = lisans_bicim.LisansHatasi
ImzaHatasi = lisans_bicim.ImzaHatasi
UrunHatasi = lisans_bicim.UrunHatasi
SurumHatasi = lisans_bicim.SurumHatasi
SuresiGecmis = lisans_bicim.SuresiGecmis


def dogrula(metin: str, simdi: float = None) -> dict:
    """Lisans metnini Aican icin dogrula ve yuku don."""
    return lisans_bicim.dogrula(metin, ACIK_ANAHTAR_HEX, urun=URUN,
                                paket_no=PAKET_NO, simdi=simdi)
