"""ElevenLabs ON-URETIM (batch) betigi — sergi oncesi sabit korpusu bir kez uretir.

Oyun modunun seslendirilen metinlerini (sabit replikler + kelime havuzu + quiz
havuzu) enumere eder, cumle parcalarina boler (runtime ile ayni _split_sentences_tr),
KABA duygu imzasiyla (engine_elevenlabs.emotion_signature) tekillestirir ve WavCache'e
YAZAR. Boylece sergide bu parcalar %100 cache isabeti = 0 kredi.

Anahtar esitligi: runtime /api/speak, ElevenLabs motorunda cache anahtarini
(voice, DUYGU-IMZASI, yogunluk, metin) uzerinden kurar (bkz web_server._cache_jest);
bu betik de AYNI imzayi/anahtari uretir -> sergide dogrudan isabet. Rastgele jest
secimi imza sayesinde tek sese kanoniklesir (emoji/oyun degismez).

Kullanim (orchestrator/ dizininden):
  python -m tts.gen_batch_elevenlabs                 # DRY-RUN: kredi onizlemesi (API'siz)
  python -m tts.gen_batch_elevenlabs --run --yes     # GERCEK uretim (ELEVENLABS_API_KEY gerekli)
  python -m tts.gen_batch_elevenlabs --run --yes --include-selfheal   # harf sablonlarini da uret

self_heal=True birimler (harf'li retry/pes replikleri) VARSAYILAN olarak ON-URETILMEZ;
sergide ilk kullanimda canli uretilip cache'lenir (bkz secilen plan). Dry-run bunlari
ayri "self-heal kuyrugu" olarak raporlar.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # orchestrator/ path'e

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Turkce konsol
except Exception:  # noqa: BLE001
    pass

from game_engine import GameEngine, _JEST, _TXT, _cap, _load_json_list   # noqa: E402
from word_llm import son_harf                                 # noqa: E402
from web_server import (                                      # noqa: E402
    _split_sentences_tr, KELIME_KURAL_TEXT, HAZIR_BEKLE_TEXT,
    SESSION_GREETING_TEXT, SESSION_GREETING_JEST, DEFAULT_TTS_VOICE, load_config,
    TEST_OYUNLAR, TEST_SOHBET_KAPALI_TEXT, _test_greeting_yanit,
)
from tts.engine_elevenlabs import emotion_signature           # noqa: E402
from tts.text_norm import seslendirme_metni                   # noqa: E402

_SEN_BASLA = "Sen başla — bir kelime söyle!"


def _guard_templates():
    try:
        from llm_bridge import _SAFE_RESPONSE_TEMPLATES
        return dict(_SAFE_RESPONSE_TEMPLATES)
    except Exception:  # noqa: BLE001
        return {}


def _enumerate_quiz(ge):
    """Tum quiz sorularinin (prompt, reveal) metinlerini uret (saglayici koduyla ayni sablon)."""
    prompts, reveals = [], []
    ez = ge._providers.get("eszit")
    if ez:
        for w in ez.words:
            for tip in ("es", "zit"):
                if ez.data.get(w, {}).get(tip):
                    tip_ad = "eş" if tip == "es" else "zıt"
                    prompts.append(f"'{_cap(w)}' kelimesinin {tip_ad} anlamlısı ne?")
                    reveals.append(_cap(ez.data[w][tip][0]))
    at = ge._providers.get("atasozu")
    if at:
        for it in at.items:
            prompts.append(f"'{it['bas']} …' nasıl devam eder?")
            reveals.append(f"{it['bas']} {it['tamam'][0]}")
    dy = ge._providers.get("dogruyanlis")
    if dy:
        for it in dy.items:
            prompts.append(f"'{it['ifade']}' — doğru mu, yanlış mı?")
            dyw = "Doğru" if it["dogru"] else "Yanlış"
            reveals.append(f"{dyw} — {it.get('aciklama', '')}".strip(" —"))
    return prompts, reveals


def build_units(ge):
    """Seslendirilen her baglam icin {name, texts, jests, yog, self_heal} birimi."""
    U = []
    def add(name, texts, jests, yog, self_heal=False):
        texts = [t for t in (texts or []) if (t or "").strip()]
        if texts:
            U.append({"name": name, "texts": texts, "jests": list(jests),
                      "yog": yog, "self_heal": self_heal})

    # 1) Sabit cekirdek replikler
    add("menu", [ge._menu_payload()["yanit"], ge._menu_payload(reprompt=True)["yanit"]],
        [_JEST["menu"]], 0.8)
    # Test modu ('g' tusu: sinirli menu + sohbet kapali) replikleri de cache'te olsun.
    eski_izin = ge.izinli_oyunlar
    ge.izinli_oyunlar = TEST_OYUNLAR
    tm_menu = ge._menu_payload()
    add("menu_test",
        [_test_greeting_yanit(), tm_menu["yanit"],
         ge._menu_payload(reprompt=True)["yanit"], TEST_SOHBET_KAPALI_TEXT],
        [_JEST["menu"], SESSION_GREETING_JEST], 0.8)
    ge.izinli_oyunlar = eski_izin
    # KIOSK (panelsiz sergi) voice_only=True kullanir -> menu birincil metni
    # "Söyle: ..." olur ("Dokun ya da söyle" YERINE; bkz game_engine._menu_payload).
    # Batch varsayilani voice_only=False oldugundan bu varyant SADECE web_server
    # startup pre-warm'u ile cache'lenirdi (kirilgan; ozellikle NON-test 4-oyunlu
    # menu hic uretilmiyordu). Burada dogrudan uret: hem tum oyunlar (non-test)
    # hem TEST_OYUNLAR (test modu). Zaten cache'te olan atlanir (kredi harcanmaz).
    eski_vo = ge.voice_only
    ge.voice_only = True
    vo_menu = [ge._menu_payload()["yanit"]]              # tum oyunlar (non-test kiosk)
    ge.izinli_oyunlar = TEST_OYUNLAR
    vo_menu.append(ge._menu_payload()["yanit"])          # test modu kiosk
    ge.izinli_oyunlar = eski_izin
    ge.voice_only = eski_vo
    add("menu_voice", vo_menu, [_JEST["menu"], SESSION_GREETING_JEST], 0.8)
    add("exit", list(_TXT["exit"]), [_JEST["exit"]], 0.6)
    add("kelime_kural", [KELIME_KURAL_TEXT], _JEST["kel_intro"], 0.8)
    add("hazir_bekle", [HAZIR_BEKLE_TEXT], ["bekle"], 0.6)
    add("sen_basla", [_SEN_BASLA], _JEST["kel_intro"], 0.8)
    add("tezahurat", list(_TXT["kel_user_ok"]), _JEST["kel_user_ok"], 0.85)
    add("user_lose", list(_TXT["kel_user_lose_timeout"]) + list(_TXT["kel_user_lose_invalid"]),
        _JEST["kel_user_lose"], 0.8)
    add("greeting", [SESSION_GREETING_TEXT], [SESSION_GREETING_JEST], 0.8)
    for k, v in _guard_templates().items():
        add(f"guard:{k}", [v], [None if k == "sicaklik_default" else k], 0.7)
    for prov in ge._providers.values():
        add(f"quiz_intro:{prov.key}",
            [prov.intro(ge.QUIZ_QUESTION_COUNT) +
             " Hazırsan başlayalım — 'başla' de ya da butona dokun!"],
            _JEST["kel_intro"], 0.8)
    # Quiz hazirlik repliklerinin VOICE_ONLY (kiosk/test modu) varyantlari: "ya da
    # butona dokun" yok -> FARKLI metin, FARKLI cache anahtari. Batch varsayilani
    # voice_only=False oldugu icin bunlar yalnizca web_server on-isitmasiyla
    # cache'lenirdi; anahtar yokken on-isitma edge'e duser ve (cache zehirlenme
    # korumasi geregi) YAZILMAZ -> sergide surekli ucretsiz ses. Dogrudan uret.
    eski_vo, eski_prov, eski_phase = ge.voice_only, ge.quiz_provider, ge.phase
    ge.voice_only = True
    vo_intro, vo_bekle = [], []
    for key in ge._providers:
        ge.quiz_provider = key
        vo_intro.append(ge._start_quiz()["yanit"])
        vo_bekle.append(ge._handle_quiz_ready("hmm")["yanit"])
    ge.voice_only, ge.quiz_provider, ge.phase = eski_vo, eski_prov, eski_phase
    ge.quiz_turn = None
    add("quiz_intro_voice", vo_intro, _JEST["kel_intro"], 0.8)
    add("quiz_bekle_voice", list(dict.fromkeys(vo_bekle)), ["bekle"], 0.6)

    # 2) Kazanma (AI pes) + tekrar-uyari replikleri — ARTIK harfsiz -> harf-basi
    # genisletme yok, dogrudan on-uretilir (Mert sesiyle cache'te olsun).
    words = sorted({w for ws in ge._ai_pool.values() for w in ws})
    add("retry", [_TXT["kel_retry_invalid"][0], _TXT["kel_retry_letter"][0],
                  _TXT["kel_retry_used"][0]], _JEST["kel_retry"], 0.65)
    add("ai_lose", list(_TXT["kel_ai_lose"]), _JEST["kel_ai_lose"], 0.85)

    # 3) Kelime havuzu — AI kelimesi 3 baglamda cikabilir (imza cogunu birlestirir)
    caps = [_cap(w) for w in words]
    add("word_opener", caps, _JEST["kel_intro"], 0.8)
    add("word_normal", caps, _JEST["kel_ai_word"], 0.85)
    add("word_streak", caps, _JEST["kel_ai_streak"], 0.9)

    # 4) Quiz sorulari + SADELESTIRILMIS geri bildirim (cevap TEK, paylasilan cumle)
    prompts, reveals = _enumerate_quiz(ge)
    add("quiz_prompts", prompts,
        _JEST["kel_intro"] + _JEST["kel_user_ok"] + _JEST["kel_retry"], 0.85)
    # rstrip(' .'): runtime'daki beklenen = reveal.rstrip(" .") ile BIREBIR ayni
    # metin (aksi halde "doner.." cift nokta -> farkli cache anahtari -> miss).
    fb = [f"Cevap: {rv.rstrip(' .')}." for rv in reveals]  # dogru/yanlis'ta ORTAK cevap cumleleri
    fb += list(GameEngine._QUIZ_DOGRU_CHEER)              # 3 tezahurat cumlesi
    fb += list(GameEngine._QUIZ_YAKIN)                    # yakin-cevap onekleri
    fb += list(GameEngine._QUIZ_YANLIS)                   # notr yanlis onekleri
    fb += ["Süre doldu!"]                                  # zaman asimi
    add("quiz_feedback", fb, _JEST["kel_user_ok"] + _JEST["kel_retry"], 0.85)

    # 5) Quiz bitisi (yog=0.85, _quiz_end ile AYNI): "Bitti!" min_len altinda kaldigi
    # icin skor cumlesiyle BIRLESIR -> tum ulasilabilir skor varyantlari
    # (d <= t <= soru sayisi) birlesik haliyle on-uretilir; kapanis replikleri ayri.
    # AYRICA son sorunun geri bildirim oneki (tezahurat/onek + "Cevap: X.") _quiz_end
    # payload'ina EKLENIR ve OYUN-SONU jest havuzuyla + yog=0.85'te seslendirilir;
    # bu yuzden fb (feedback cumleleri) burada da uretilmeli — aksi halde son sorunun
    # onek/cevap parcasi (orta oyun jest havuzunda uretildigi icin) edge'e duser.
    n_q = GameEngine.QUIZ_QUESTION_COUNT
    bitis = [f"Bitti! {d}/{t} doğru." for t in range(1, n_q + 1) for d in range(0, t + 1)]
    bitis += ["Harikasın!", "Güzel oynadın!", "Önemli değil, yine beklerim!"]
    bitis += fb   # tezahurat + "Cevap: X." + yakin/yanlis onekleri + "Süre doldu!"
    add("quiz_end", bitis, _JEST["kel_user_ok"] + _JEST["kel_intro"] + ["huzur"], 0.85)

    return U


AI_DIR = Path(__file__).resolve().parent.parent.parent / "ai"


def veri_kombinasyonlari():
    """(etiket, GameEngine) — AKTIF veri + ai/ altindaki TUM soru seti varyantlari.

    Sergi PC'sinin deposu farkli bir surumde olabilir: kod 2026-08-01'de kucuk
    'cocuklar icin' setlerine gecti, ondan onceki checkout hala buyuk havuzu
    (es_zit_anlam.json + atasozu.json) okur. Yalnizca aktif seti uretirsek o
    makinede sorular — ozellikle OYUN SONU baglamindaki son cevap — sesi olmayan
    metne duser. Varyantlari da kapsamak, hangi surum acilirsa acilsin Mert
    sesini garantiler."""
    yield "aktif", GameEngine(bridge=None)
    for ea in sorted(AI_DIR.glob("es_zit*.json")):
        for ata in sorted(AI_DIR.glob("atasozu*.json")):
            yield (f"{ea.name} + {ata.name}",
                   GameEngine(bridge=None, ea_path=ea, atasozu_data=_load_json_list(ata)))


def build_units_tum_veri():
    """Tum veri varyantlarinin birimleri arka arkaya. Ayni anahtar birden fazla
    varyantta cikarsa cagiran taraf (unit_key_map + gorulen kumesi) tekillestirir."""
    U = []
    for _, ge in veri_kombinasyonlari():
        U.extend(build_units(ge))
    return U


def unit_key_map(unit):
    """{(chunk, imza, yog): (chunk, temsili_jest, yog)} — TUM pool jest'leri enumere
    edilir, imza benzer olanlari tek anahtara indirir (= gercek runtime maliyeti);
    her anahtar icin ilk (temsili) jest saklanir, --run onunla DUYGULU ses uretir."""
    m = {}
    for text in unit["texts"]:
        for chunk in _split_sentences_tr(text):
            # runtime (_tts_synth_cached) ile AYNI temizlik — aksi halde emoji/":)"
            # iceren parcalarin anahtari tutmaz ve sergide ucretsiz sese duser.
            chunk = seslendirme_metni(chunk)
            if not chunk:
                continue
            for j in unit["jests"]:
                key = (chunk, emotion_signature(j, unit["yog"]), unit["yog"])
                if key not in m:
                    m[key] = (chunk, j, unit["yog"])
    return m


def summarize(units):
    """(pre_gen_cat, self_heal_cat) -> her biri {name: [parca_sayisi, karakter]}."""
    pre, heal = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    seen = set()
    for u in units:
        bucket = heal if u["self_heal"] else pre
        for key in unit_key_map(u):
            if key in seen:            # ayni anahtar iki baglamda -> tek say
                continue
            seen.add(key)
            bucket[u["name"]][0] += 1
            bucket[u["name"]][1] += len(key[0])
    return pre, heal


def _print_cat(title, cat, cpc):
    n_chunks = sum(v[0] for v in cat.values())
    n_chars = sum(v[1] for v in cat.values())
    print(f"--- {title} ---")
    for name in sorted(cat, key=lambda k: -cat[k][1]):
        c, ch = cat[name]
        print(f"  {name:16} {c:6} parca  {ch:8} karakter")
    print(f"  {'TOPLAM':16} {n_chunks:6} parca  {n_chars:8} karakter  "
          f"=> {n_chars * cpc:,.0f} kredi\n")
    return n_chunks, n_chars


def _open_cache(cfg):
    """(cache, voice) — API'siz; denetim ve uretim AYNI anahtar uzayini kullansin."""
    from tts.cache import WavCache
    voice = cfg.get("tts_voice", DEFAULT_TTS_VOICE)
    cache = WavCache(Path(__file__).resolve().parent / "cache",
                     max_files=int(cfg.get("tts_cache_max", 5000)), enabled=True)
    return cache, voice


def audit(units, cache, voice, cpc, ornek=10):
    """API'siz DENETIM: hangi birimlerin hangi parcalari cache'te YOK?

    Cache'te olmayan her parca sergide canli sentezlenir; ElevenLabs anahtari
    yoksa/kota dolmussa ucretsiz edge sesiyle duyulur. Bu rapor tam olarak o
    listedir (= --run --yes ile uretilecek kume)."""
    print(f"\n=== ONBELLEK DENETIMI (ses={voice}) ===\n")
    print(f"  {'birim':22} {'anahtar':>8} {'cache':>8} {'EKSIK':>8}   eksik-metin")
    eksikler, sayac, gorulen = defaultdict(list), defaultdict(lambda: [0, 0, 0]), set()
    for u in units:
        for key in unit_key_map(u):
            if key in gorulen:
                continue
            gorulen.add(key)
            chunk, sig, yog = key
            sayac[u["name"]][0] += 1
            if cache.get(cache.make_key(chunk, sig, yog, voice)) is not None:
                sayac[u["name"]][1] += 1
            else:
                sayac[u["name"]][2] += 1
                eksikler[u["name"]].append(chunk)
    for name in sorted(sayac, key=lambda n: -sayac[n][2]):
        t, h, m = sayac[name]
        print(f"  {name:22} {t:8} {h:8} {m:8}   {len(set(eksikler.get(name, [])))}")
    for name in sorted(eksikler, key=lambda n: -len(set(eksikler[n]))):
        benzersiz = sorted(set(eksikler[name]))
        kar = sum(len(p) for p in eksikler[name])
        print(f"\n  [{name}] eksik benzersiz metin: {len(benzersiz)}  "
              f"({kar} karakter ≈ {kar * cpc:,.0f} kredi)")
        for p in benzersiz[:ornek]:
            print(f"      - {p[:88]}")
        if len(benzersiz) > ornek:
            print(f"      ... (+{len(benzersiz) - ornek} benzersiz metin daha)")
    n_eksik = sum(v[2] for v in sayac.values())
    kar_top = sum(len(p) for v in eksikler.values() for p in v)
    print(f"\n  TOPLAM: {len(gorulen)} anahtar | cache'te {len(gorulen) - n_eksik} | "
          f"EKSIK {n_eksik} ({kar_top} karakter ≈ {kar_top * cpc:,.0f} kredi)")
    print("\n  Eksikleri uret: python -m tts.gen_batch_elevenlabs --run --yes\n")
    return eksikler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="Gercekten sentezle (API + kredi)")
    ap.add_argument("--yes", action="store_true", help="--run icin onay")
    ap.add_argument("--eksik", action="store_true",
                    help="API'siz DENETIM: cache'te olmayan (= ucretsiz sese dusen) parcalari listele")
    ap.add_argument("--include-selfheal", action="store_true",
                    help="self_heal birimleri (harf sablonlari) de uret")
    ap.add_argument("--tum-veri", action="store_true",
                    help="ai/ altindaki TUM soru seti varyantlarini kapsa "
                         "(sergi PC farkli surumdeyse de ses hazir olsun)")
    args = ap.parse_args()

    ge = GameEngine(bridge=None)
    units = build_units_tum_veri() if args.tum_veri else build_units(ge)
    model = "eleven_flash_v2_5"
    cpc = 0.5 if ("flash" in model or "turbo" in model) else 1.0

    if args.eksik:
        cache, voice = _open_cache(load_config())
        audit([u for u in units if not u["self_heal"] or args.include_selfheal],
              cache, voice, cpc)
        return

    print(f"\n=== ElevenLabs on-uretim ONIZLEME (imza-kanonik, model={model}, "
          f"{cpc} kredi/karakter) ===\n")
    pre, heal = summarize(units)
    _, pre_chars = _print_cat("ON-URETILECEK (pre-gen)", pre, cpc)
    _, heal_chars = _print_cat("SELF-HEAL kuyrugu (sergide ilk kullanimda canli)", heal, cpc)
    print(f"ONDEN uretim: {pre_chars * cpc:,.0f} kredi   |   "
          f"self-heal ust siniri: {heal_chars * cpc:,.0f} kredi (yalnizca gercekten "
          f"karsilasilan parcalar, 32k tavanla sinirli)\n")

    if not args.run:
        print("Dry-run bitti (hicbir sey uretilmedi). Gercek uretim: --run --yes\n")
        return
    if not args.yes:
        print("GUVENLIK: gercek uretim icin --yes ekle. Iptal.\n")
        return

    # ——— GERCEK URETIM ———
    import os
    from tts.engine_elevenlabs import ElevenLabsEngine
    cfg = load_config()
    api_key = cfg.get("tts_elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        print("HATA: ELEVENLABS_API_KEY yok (env ya da config). Iptal.\n")
        return
    cache, voice = _open_cache(cfg)
    # Batch BILINCLI tek-seferlik harcama (dry-run + --yes ile onaylandi) -> runtime
    # tavanina (cap) TAKILMASIN: cap=0 (guard kapali) ama harcama ayni usage dosyasina
    # yazilir; boylece runtime motoru (cap'li) ayni ayda bu harcamayi gorur.
    engine = ElevenLabsEngine(
        voice=voice, api_key=api_key,
        model=cfg.get("tts_elevenlabs_model", model),
        language=cfg.get("tts_elevenlabs_language", "tr"),
        monthly_cap=0,
        usage_path=Path(__file__).resolve().parent / "elevenlabs_usage.json")

    key_reps = {}
    for u in units:
        if u["self_heal"] and not args.include_selfheal:
            continue
        for key, rep in unit_key_map(u).items():
            key_reps.setdefault(key, rep)
    print(f"Uretiliyor: {len(key_reps)} benzersiz parca (voice={voice})...\n")
    done = hit = fail = 0
    for i, (key, rep) in enumerate(sorted(key_reps.items()), 1):
        chunk, sig, yog = key
        _, jest, _ = rep
        k = cache.make_key(chunk, sig, yog, voice)
        if cache.get(k) is not None:
            hit += 1
            continue
        # Temsili jest ile DUYGULU ses uret; anahtar imzayla kurulur (runtime ile ayni).
        audio = engine.synthesize(chunk, jest, yog)
        if audio:
            cache.put(k, audio)
            done += 1
        else:
            fail += 1
        if i % 50 == 0:
            print(f"  {i}/{len(key_reps)}  yeni={done} cache={hit} bos/atlanan={fail} "
                  f"harcanan~{engine.guard.spent:,.0f} kredi")
    print(f"\nBITTI. yeni={done} cache_isabet={hit} bos/atlanan={fail}  "
          f"toplam_harcanan~{engine.guard.spent:,.0f} kredi\n")


if __name__ == "__main__":
    main()
