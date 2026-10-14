"""Yerel (internetsiz, ucretsiz) modeller: Whisper (konusma -> yazi) ve NLLB-200 (ceviri).

Modeller program klasorundeki modeller/ altinda durur (modelleri_indir.py indirir, surumleri sabit):
- whisper-turbo: mobiuslabsgmbh/faster-whisper-large-v3-turbo (faster-whisper'in varsayilan kaynagi, MIT)
- nllb-1.3b:     OpenNMT/nllb-200-distilled-1.3B-ct2-int8 (CTranslate2'yi yapan ekip, CC-BY-NC-4.0)
Whisper ekran kartinda calisir (yoksa islemcide 'small' modele duser); NLLB islemcide calisir,
ekran karti oyuna kalsin diye.
"""
import glob
import logging
import os
import re
import sys
from pathlib import Path

import numpy as np

KLASOR = Path(__file__).resolve().parent / "modeller"
os.environ.setdefault("HF_HOME", str(KLASOR / ".hf"))          # yedek indirmeler de D:'ye
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

log = logging.getLogger("yerel")


def _cuda_dll_ekle():
    """pip ile gelen NVIDIA kutuphaneleri (cuBLAS, cuDNN) Windows'ta kendiliginden bulunmuyor."""
    for d in glob.glob(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")):
        try:
            os.add_dll_directory(d)
        except OSError:
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


_cuda_dll_ekle()

import ctranslate2  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402
from faster_whisper.tokenizer import Tokenizer  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

import kisa_sozluk  # noqa: E402

# Whisper dil kodu -> NLLB dil kodu
NLLB = {
    "tr": "tur_Latn", "en": "eng_Latn", "de": "deu_Latn", "fr": "fra_Latn", "es": "spa_Latn",
    "ru": "rus_Cyrl", "it": "ita_Latn", "pt": "por_Latn", "pl": "pol_Latn", "uk": "ukr_Cyrl",
    "nl": "nld_Latn", "ar": "arb_Arab", "fa": "pes_Arab", "az": "azj_Latn", "ja": "jpn_Jpan",
    "ko": "kor_Hang", "zh": "zho_Hans", "sv": "swe_Latn", "no": "nob_Latn", "da": "dan_Latn",
    "fi": "fin_Latn", "cs": "ces_Latn", "sk": "slk_Latn", "ro": "ron_Latn", "hu": "hun_Latn",
    "el": "ell_Grek", "bg": "bul_Cyrl", "sr": "srp_Cyrl", "hr": "hrv_Latn", "bs": "bos_Latn",
    "sl": "slv_Latn", "he": "heb_Hebr", "hi": "hin_Deva", "ur": "urd_Arab", "id": "ind_Latn",
    "ms": "zsm_Latn", "vi": "vie_Latn", "th": "tha_Thai", "ka": "kat_Geor", "kk": "kaz_Cyrl",
    "uz": "uzn_Latn", "hy": "hye_Armn", "lt": "lit_Latn", "lv": "lvs_Latn", "et": "est_Latn",
    "be": "bel_Cyrl", "mk": "mkd_Cyrl", "sq": "als_Latn", "tl": "tgl_Latn", "bn": "ben_Beng",
    "ca": "cat_Latn", "ky": "kir_Cyrl", "tk": "tuk_Latn", "tt": "tat_Cyrl", "mn": "khk_Cyrl",
}

# Whisper'in sessizlik/muzik/unlem uzerine sik uydurdugu sozler
# ("Aa" -> "Anadolu Ajansı" 2026-10-14'te olculdu; Turkce haber altyazilarindan kalma)
_UYDURMA = re.compile(
    r"^(thank(s| you)( so much)?( for watching)?|thanks for watching|please subscribe|"
    r"altyaz[ıi].*|abone ol.*|izledi[gğ]iniz i[cç]in te[sş]ekk[uü]r.*|anadolu ajans[ıi].*|"
    r"untertitel.*|sous-titr.*|субтитр.*|продолжение следует|редактор субтитров.*|you)[.!?…]*$",
    re.IGNORECASE)
_KELIME_ANAHTAR = re.compile(r"[^\w']+")


def tekrarlari_sil(metin: str) -> str:
    """Ust uste tekrarlanan kelime/kelime obeklerini teke indirir:
    "Merhaba Merhaba Merhaba" -> "Merhaba", "Merhaba arkadaslar. Merhaba arkadaslar." -> "Merhaba arkadaslar."
    Whisper kisa seste ve NLLB kisa girdide boyle donguye giriyor (2026-10-14 olculdu)."""
    kelimeler = metin.split()
    anahtarlar = [_KELIME_ANAHTAR.sub("", k.lower()) for k in kelimeler]
    degisti = True
    while degisti:
        degisti = False
        for n in range(min(8, len(kelimeler) // 2), 0, -1):
            i = 0
            while i + 2 * n <= len(kelimeler):
                a, b = anahtarlar[i:i + n], anahtarlar[i + n:i + 2 * n]
                if a == b and any(a):
                    # ilkinin yazimini, tekrarin sonundaki noktalamayi koru ("Tamam, tamam." -> "Tamam.")
                    govde = re.sub(r"[^\w']+$", "", kelimeler[i + n - 1])
                    kelimeler[i + n - 1] = govde + re.search(r"[^\w']*$", kelimeler[i + 2 * n - 1]).group()
                    del kelimeler[i + n:i + 2 * n]
                    del anahtarlar[i + n:i + 2 * n]
                    degisti = True
                else:
                    i += 1
    return " ".join(kelimeler)


def _duzelt(metin: str) -> str:
    """NLLB ciktisi: film altyazisindan kalma basta tire ("- Merhaba."), noktalama oncesi bosluk."""
    metin = re.sub(r"(^|(?<=[.!?…]))\s*[-–—]\s+", r"\1 ", metin)
    metin = re.sub(r"\s+([,.!?…:;])", r"\1", metin)
    return " ".join(tekrarlari_sil(metin).split())


class Tanima:
    """Whisper: 16 kHz mono int16 ses -> (metin, dil, dil_olasiligi).

    Hiz icin faster-whisper'in transcribe'i yerine CTranslate2 dogrudan kullanilir (olculdu, GTX 1650):
    - transcribe dil tespiti icin sesi iki kez kodluyordu: 3.6 sn. Tek kodlama + ayni ciktidan dil: 1.9 sn.
    - Whisper sesi hep 30 sn'ye tamamlar; kodlama ~1.75 sn. Kisa konusmayi kendi uzunlugu + 3 sn pay
      (en az 10 sn) pencerede kodlamak: 5 sn'lik cumlede 0.4 sn, 11.6 sn'de 0.8 sn, ciktilar ayni.
      Pay 2 sn ve pencere kisa olunca model son cumleyi tekrar tekrar yaziyordu; 3 sn + en az 10 sn'de duzeldi.
    """
    PENCERE_EN_AZ = 1000          # mel karesi (10 ms): en az 10 sn
    PAY = 300                     # konusmanin ardina 3 sn sessizlik
    PARCA_SN = 25                 # cok uzun F8 konusmasi bu uzunlukta parcalara bolunur

    def __init__(self, cihaz: str = "otomatik"):
        self.cihaz = None
        if cihaz != "cpu" and ctranslate2.get_cuda_device_count() > 0:
            try:
                self.model = WhisperModel(str(KLASOR / "whisper-turbo"), device="cuda", compute_type="int8_float16")
                self.cihaz = "ekran kartı (whisper large-v3-turbo)"
            except Exception:  # noqa: BLE001
                log.exception("whisper cuda acilamadi, islemciye dusuluyor")
        if self.cihaz is None:
            # Islemcide turbo cok yavas; 'small' ilk kullanimda indirilir (~480 MB). Surum sabit:
            # depo sonradan degistirilse bile test edilen dosyalar iner.
            self.model = WhisperModel("Systran/faster-whisper-small", device="cpu", compute_type="int8",
                                      download_root=str(KLASOR / "whisper-small"),
                                      revision="536b0662742c02347bc0e980a01041f333bce120")
            self.cihaz = "işlemci (whisper small)"

    def yaziya(self, pcm: bytes, dil: str | None = None, ipucu: str | None = None) -> tuple[str, str | None, float]:
        """ipucu: sohbetin suregelen dili; model dilden emin degilse (kisa soz) ona yaslanir."""
        self._ipucu = ipucu
        ses = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
        # Konusma algilayici (Silero, islemcide, birkac ms): muzik/oyun sesi ekran kartina hic gitmesin
        konusma = get_speech_timestamps(ses, VadOptions(min_silence_duration_ms=500, speech_pad_ms=200))
        if not konusma:
            return "", None, 0.0
        ses = ses[konusma[0]["start"]:konusma[-1]["end"]]
        metinler, olasilik = [], 1.0
        adim = self.PARCA_SN * 16000
        for bas in range(0, len(ses), adim):
            metin, dil, o = self._parca(ses[bas:bas + adim], dil)  # sonraki parcalar ilk parcanin dilinde
            olasilik = min(olasilik, o)
            if metin:
                metinler.append(metin)
        return " ".join(metinler).strip(), dil, olasilik

    def _parca(self, ses: np.ndarray, dil: str | None) -> tuple[str, str | None, float]:
        """Tekrar onlemi (2026-10-14 olculdu: "Merhaba" -> "Merhaba Merhaba Merhaba..." 8 kez):
        zaman damgali cozulur ve sesin bittigi andan SONRA baslayan parcalar atilir (model sessiz
        payi "duydugunu" sanip ayni sozu yeniden yaziyordu); ayrica 3'lu kelime tekrari yasak.
        Bu ikisiyle tum ornekler duzeldi, uzun cumleler degismedi."""
        m = self.model
        ozellik = m.feature_extractor(ses)                           # (mel, kare)
        n = min(3000, max(self.PENCERE_EN_AZ, int(np.ceil((ozellik.shape[1] + self.PAY) / 100) * 100)))
        girdi = np.zeros((ozellik.shape[0], n), np.float32)
        girdi[:, :min(n, ozellik.shape[1])] = ozellik[:, :n]
        kod = m.model.encode(ctranslate2.StorageView.from_array(girdi[None]), to_cpu=False)
        olasilik = 1.0
        if dil is None:
            adaylar = m.model.detect_language(kod)[0]                # [("<|en|>", 0.7), ...] buyukten kucuge
            jeton, olasilik = adaylar[0]
            dil = jeton[2:-2]                                        # "<|en|>" -> "en"
            ipucu = getattr(self, "_ipucu", None)
            # Kisa sozde dil tespiti saskin (olculdu: Almanca "Hallo Hallo" -> Ingilizce "Oh no"):
            # emin degilse ve sohbetin dili de guclu adaysa onu sec
            if ipucu and dil != ipucu and olasilik < 0.6:
                for j, p in adaylar[:6]:
                    if j[2:-2] == ipucu and p >= 0.08:
                        dil, olasilik = ipucu, p
                        break
        tk = Tokenizer(m.hf_tokenizer, True, task="transcribe", language=dil)
        sure = len(ses) / 16000
        r = m.model.generate(kod, [list(tk.sot_sequence)], beam_size=3, return_no_speech_prob=True,
                             suppress_blank=True, no_repeat_ngram_size=3,
                             max_length=min(224, int(sure * 12) + 24))[0]
        if r.no_speech_prob > 0.7:
            return "", dil, olasilik
        metin = tekrarlari_sil(self._sure_icinde(r.sequences_ids[0], tk, sure))
        return ("" if _UYDURMA.match(metin) else metin), dil, float(olasilik)

    @staticmethod
    def _sure_icinde(jetonlar: list[int], tk: Tokenizer, sure: float) -> str:
        """Zaman damgali ciktidan, baslangici gercek sesin icinde olan parcalari birlestir."""
        parcalar, simdiki, bas = [], [], None
        for t in jetonlar:
            if t >= tk.timestamp_begin:
                zaman = (t - tk.timestamp_begin) * 0.02
                if bas is None:
                    bas = zaman
                else:                                                # parca bitti
                    if simdiki and bas < sure - 0.05:
                        parcalar.append(tk.decode(simdiki).strip())
                    simdiki, bas = [], None
            elif t < tk.eot:
                simdiki.append(t)
        if simdiki and (bas is None or bas < sure - 0.05):
            parcalar.append(tk.decode(simdiki).strip())
        return " ".join(p for p in parcalar if p)


class Ceviri:
    """NLLB-200 1.3B (int8, islemci)."""

    def __init__(self):
        yol = str(KLASOR / "nllb-1.3b")
        self.ceviren = ctranslate2.Translator(yol, device="cpu", compute_type="int8",
                                              inter_threads=1, intra_threads=max(2, (os.cpu_count() or 4) // 3))
        self.sozluk = AutoTokenizer.from_pretrained(yol)

    def cevir(self, metin: str, kaynak: str, hedef: str) -> str:
        """kaynak/hedef: Whisper dil kodu (or. 'en', 'tr')."""
        kaynak_n, hedef_n = NLLB.get(kaynak), NLLB.get(hedef)
        if not metin.strip() or not kaynak_n or not hedef_n or kaynak_n == hedef_n:
            return metin if kaynak_n == hedef_n else ""
        hazir = kisa_sozluk.cevir(metin, kaynak, hedef)              # "Merhaba", "Evet", "Tamam"...
        if hazir:
            return hazir
        # Cumle cumle cevir: NLLB uzun, cok cumleli girdide cumle atlayabiliyor
        cumleler = [c for c in re.split(r"(?<=[.!?…])\s+", metin.strip()) if c]
        cikti = []
        for c in cumleler:
            cikti.append(kisa_sozluk.cevir(c, kaynak, hedef) or self._nllb(c, kaynak_n, hedef_n))
        return _duzelt(" ".join(cikti))

    def _nllb(self, cumle: str, kaynak_n: str, hedef_n: str) -> str:
        self.sozluk.src_lang = kaynak_n
        jetonlar = self.sozluk.convert_ids_to_tokens(self.sozluk.encode(cumle))
        kisa = len(cumle.split()) <= 3
        # Kisa girdide NLLB uzatip tekrarliyor ("Hey!" -> "Merhaba! Merhaba!"): 4 aday al, puani en iyiye
        # yakin olanlarin en kisasini sec (olculdu: "Okay." -> "Tamamdır.", "Hey!" -> "Merhaba.")
        s = self.ceviren.translate_batch([jetonlar], target_prefix=[[hedef_n]], beam_size=4,
                                         num_hypotheses=4 if kisa else 1, return_scores=True,
                                         max_decoding_length=min(256, 3 * len(jetonlar) + 10),
                                         repetition_penalty=1.1, no_repeat_ngram_size=4)[0]
        adaylar = [(self.sozluk.decode(self.sozluk.convert_tokens_to_ids(h[1:]), skip_special_tokens=True), p)
                   for h, p in zip(s.hypotheses, s.scores)]
        if kisa and len(adaylar) > 1:
            en_iyi = adaylar[0][1]
            yakin = [a for a in adaylar if a[1] >= en_iyi - 0.15]
            return min(yakin, key=lambda a: len(_duzelt(a[0]).split()))[0]
        return adaylar[0][0]
