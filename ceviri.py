"""Ceviri motoru (tamamen yerel, internetsiz, ucretsiz). Uygulama ses calmaz, kimsenin yerine konusmaz.

KARSI TARAF: kulaklik/hoparlor sesi -> konusma parcalari (ses seviyesiyle) -> Whisper -> NLLB -> Turkce yazi
SIZ:         F8 basiliyken mikrofon -> Whisper (Turkce) -> NLLB -> karsi tarafin dilinde yazi

Konusma surerken ~1.5 sn'de bir ara ceviri gosterilir; konusma bitince son hali yazilir.
Isler tek bir is parcaciginda sirayla islenir; sizin cumleniz karsi tarafinkinden once gelir.
Aygit bekcisi: kulaklik takilip cikarilinca ya da Windows varsayilan aygiti degisince akislari yeniden acar.
"""
import collections
import itertools
import logging
import queue
import threading
import time

import kisa_sozluk
import ses

# Arayuzdeki ad -> Whisper/ISO dil kodu
DILLER = {
    "Otomatik": None, "İngilizce": "en", "Almanca": "de", "Fransızca": "fr", "İspanyolca": "es",
    "Rusça": "ru", "İtalyanca": "it", "Portekizce": "pt", "Lehçe": "pl", "Ukraynaca": "uk",
    "Hollandaca": "nl", "Arapça": "ar", "Farsça": "fa", "Azerbaycanca": "az", "Japonca": "ja",
    "Korece": "ko", "Çince": "zh",
}
KOD_AD = {kod: ad for ad, kod in DILLER.items() if kod} | {
    "tr": "Türkçe", "sv": "İsveççe", "no": "Norveççe", "da": "Danca", "fi": "Fince", "cs": "Çekçe",
    "sk": "Slovakça", "ro": "Rumence", "hu": "Macarca", "el": "Yunanca", "bg": "Bulgarca", "sr": "Sırpça",
    "hr": "Hırvatça", "bs": "Boşnakça", "sl": "Slovence", "he": "İbranice", "hi": "Hintçe", "ur": "Urduca",
    "id": "Endonezce", "ms": "Malayca", "vi": "Vietnamca", "th": "Tayca", "ka": "Gürcüce", "kk": "Kazakça",
    "uz": "Özbekçe", "hy": "Ermenice", "lt": "Litvanca", "lv": "Letonca", "et": "Estonca", "be": "Belarusça",
    "mk": "Makedonca", "sq": "Arnavutça", "tl": "Tagalogca", "bn": "Bengalce", "ca": "Katalanca",
    "ky": "Kırgızca", "tk": "Türkmence", "tt": "Tatarca", "mn": "Moğolca",
}

SESSIZ_SON = 7                # 0.7 sn sessizlik: karsi tarafin cumlesi bitti
EN_UZUN_SN = 12               # cok uzun konusma 12 sn'lik parcalara bolunur
ARA_SN = 1.5                  # konusma surerken ara ceviri sikligi (tanima ~0.4 sn surdugu icin sik olabilir)
EN_KISA_SN = 0.4              # bundan kisa F8 basisi: sadece altyaziyi temizler
EN_UZUN_BASIS_SN = 60         # F8 birakilisi kacirilirsa (oyun odakta vb.) kayit sonsuza gitmesin
AYNI_SOZ_SN = 6               # karsi taraftan ayni kisa soz bu kadar sure icinde tekrar gelirse gosterme
AYGIT_DENETIM_SN = 2.0


def dil_adi(kod: str) -> str:
    return KOD_AD.get(kod, (kod or "?").upper())


def _sure(tampon) -> float:
    return len(tampon) / (ses.GIRIS_HIZI * 2)


def _cuda_hatasi(e: Exception) -> bool:
    m = str(e).lower()
    return any(i in m for i in ("cuda", "cublas", "cudnn", "out of memory", "device-side"))


class Motor:
    def __init__(self, ayar: dict, olay):
        self.ayar = ayar
        self.olay = olay                               # olay(tur, *veri) -> arayuze
        self.tanima = self.ceviri = None
        self._isler: queue.PriorityQueue = queue.PriorityQueue()
        self._sira = itertools.count()
        self._surum: dict[str, int] = {}               # anahtar -> en yeni is surumu (eski ara isler atlanir)
        self._surum_kilit = threading.Lock()
        self._sayac = itertools.count(1)
        self._yerlesik_dil = "en"                      # karsi tarafin dili (otomatik hedef)
        self._aday_dil = None
        self._son_karsi = ("", 0.0)                    # tekrar eden kisa sozu bastirmak icin
        self._gelen_q: queue.Queue = queue.Queue(maxsize=300)
        self._kilit = threading.Lock()
        self._basili = False
        self._basis_zamani = 0.0
        self._giden_tampon = bytearray()
        self._giden_anahtar = None
        self._son_ara = 0.0
        self._son_seviye = {"gelen": -1.0, "giden": -1.0}
        # aygitlar
        self._aygit_kilit = threading.Lock()
        self._dinleyici = None
        self._mikrofon = None
        self._aygitlari_yenile = threading.Event()
        self._yeniden_iste = False
        self._varsayilanlar = (ses.varsayilan_cikis_adi(), ses.varsayilan_giris_adi())
        for hedef in (self._yukle, self._aygit_dongu, self._gelen_dongu, self._giden_dongu):
            threading.Thread(target=hedef, daemon=True).start()

    # ── modeller ve is kuyrugu ───────────────────────────────────────────────
    def _yukle(self):
        for ad in ("gelen", "giden"):
            self.olay(f"durum_{ad}", "Modeller yükleniyor…", "sari")
        try:
            from yerel import Ceviri, Tanima            # agir ice aktarma: pencere once acilsin
            self._Tanima = Tanima
            self.tanima = Tanima(self.ayar.get("cihaz", "otomatik"))
            self.ceviri = Ceviri()
        except Exception as e:  # noqa: BLE001
            logging.exception("model yukleme")
            self.olay("hata", f"Modeller yüklenemedi: {str(e)[:200]}")
            for ad in ("gelen", "giden"):
                self.olay(f"durum_{ad}", "Model hatası", "kirmizi")
            return
        self.olay("bilgi", f"Konuşma tanıma: {self.tanima.cihaz} · Çeviri: işlemci (NLLB-200 1.3B)")
        self._durumlari_yaz()
        self._isci()

    def _durumlari_yaz(self):
        if not self.tanima:
            return
        acik = bool(self.ayar["gelen_acik"]) and self._dinleyici is not None
        self.olay("durum_gelen", "Dinliyor" if acik else "Kapalı", "yesil" if acik else "gri")
        if self._mikrofon is not None:
            self.olay("durum_giden", "Dinliyor", "yesil")
        else:
            self.olay("durum_giden", "Mikrofon yok", "kirmizi")

    def _is_ekle(self, tur: str, anahtar: str, pcm: bytes, son: bool):
        with self._surum_kilit:
            surum = self._surum[anahtar] = self._surum.get(anahtar, 0) + 1
            if len(self._surum) > 500:                 # eski kayitlar birikmesin
                for k in list(self._surum)[:250]:
                    self._surum.pop(k, None)
                self._surum[anahtar] = surum
        oncelik = (0 if tur == "giden" else 2) + (0 if son else 1)
        self._isler.put((oncelik, next(self._sira), tur, anahtar, surum, pcm, son))

    def _isci(self):
        cuda_hata = 0
        while True:
            _, _, tur, anahtar, surum, pcm, son = self._isler.get()
            with self._surum_kilit:
                eski = not son and surum < self._surum.get(anahtar, 0)
            if eski:
                continue                               # ayni konusmanin daha yeni hali kuyrukta
            try:
                if tur == "gelen":
                    self._gelen_isle(anahtar, pcm, son)
                else:
                    self._giden_isle(anahtar, pcm, son)
                cuda_hata = 0
            except Exception as e:  # noqa: BLE001
                logging.exception("is")
                if _cuda_hatasi(e):
                    cuda_hata += 1
                    if cuda_hata >= 2:                 # ekran karti dolu/bozuk (agir oyun): islemciye gec
                        self._islemciye_gec()
                        cuda_hata = 0
                    continue
                self.olay("hata", f"Çeviri hatası: {str(e)[:150]}")

    def _islemciye_gec(self):
        self.olay("hata", "Ekran kartı hatası (oyun belleği doldurmuş olabilir). Konuşma tanıma işlemciye "
                          "geçiyor; ilk seferde ~480 MB model iner, internet gerekir.")
        try:
            self.tanima = self._Tanima("cpu")
            self.olay("bilgi", f"Konuşma tanıma: {self.tanima.cihaz}")
        except Exception as e:  # noqa: BLE001
            logging.exception("islemciye gecis")
            self.olay("hata", f"İşlemci modeli de açılamadı: {str(e)[:150]}")

    def _gelen_isle(self, anahtar: str, pcm: bytes, son: bool):
        metin, dil, olasilik = self.tanima.yaziya(pcm, ipucu=self._yerlesik_dil)
        if not metin or dil == "tr":                   # konusma yok ya da zaten Turkce
            return
        cev = self.ceviri.cevir(metin, dil, "tr")
        if not cev:
            if olasilik < 0.7:                         # dil emin degil + cevrilemiyor: buyuk ihtimal gurultu
                return
            cev = f"(çevrilemeyen dil: {dil_adi(dil)})"
        if son:
            # Ayni kisa soz kisa surede tekrar geliyorsa (uydurma/yanki) bir daha gosterme
            anahtar_metin = kisa_sozluk.normallestir(metin, dil)
            if len(anahtar_metin.split()) <= 4 and self._son_karsi[0] == anahtar_metin \
                    and time.time() - self._son_karsi[1] < AYNI_SOZ_SN:
                return
            self._son_karsi = (anahtar_metin, time.time())
        self.olay("gelen", anahtar, metin, cev, dil_adi(dil))
        if son:
            self._karsi_dil(dil, olasilik, len(metin.split()))

    def _giden_isle(self, anahtar: str, pcm: bytes, son: bool):
        metin, _, _ = self.tanima.yaziya(pcm, dil="tr")
        hedef = self._giden_hedef()
        if not metin:
            if son:
                self.olay("giden", anahtar, "", "(anlaşılmadı, F8 ile tekrar söyleyin)", "")
            return
        self.olay("giden", anahtar, metin, self.ceviri.cevir(metin, "tr", hedef), dil_adi(hedef))

    # ── dil secimi ───────────────────────────────────────────────────────────
    def otomatik_dil(self) -> str:
        return self._yerlesik_dil

    def _giden_hedef(self) -> str:
        return DILLER.get(self.ayar["hedef_dil"]) or self.otomatik_dil()

    def _karsi_dil(self, dil: str, olasilik: float, kelime: int):
        """Net bir cumle (3+ kelime, Whisper %80+ emin) hedefi hemen degistirir; kisa ya da
        belirsiz bir soz ancak ust uste iki kez ayni dilde gelirse."""
        if dil == self._yerlesik_dil:
            self._aday_dil = None
        elif (kelime >= 3 and olasilik >= 0.8) or dil == self._aday_dil:
            self._yerlesik_dil, self._aday_dil = dil, None
        else:
            self._aday_dil = dil
        self.olay("oto_dil", dil_adi(self._yerlesik_dil))

    # ── aygitlar ─────────────────────────────────────────────────────────────
    def aygitlari_yenile(self, yeniden: bool = True):
        """Arayuzden aygit secimi degisince (yeniden=True) ya da dinleme acilip kapaninca (False) cagrilir."""
        self._yeniden_iste = self._yeniden_iste or yeniden
        self._aygitlari_yenile.set()

    def _aygit_dongu(self):
        while True:
            try:
                self._aygitlari_denetle()
            except Exception:  # noqa: BLE001
                logging.exception("aygit denetimi")
            self._aygitlari_yenile.wait(AYGIT_DENETIM_SN)

    def _aygitlari_denetle(self):
        istek = self._aygitlari_yenile.is_set()
        self._aygitlari_yenile.clear()
        yeniden_iste, self._yeniden_iste = self._yeniden_iste, False
        simdiki = (ses.varsayilan_cikis_adi(), ses.varsayilan_giris_adi())
        varsayilan_degisti = simdiki != self._varsayilanlar
        bozuk = (self._dinleyici is not None and not self._dinleyici.calisiyor()) or \
                (self._mikrofon is not None and not self._mikrofon.calisiyor())
        eksik = (self._dinleyici is None and self.ayar["gelen_acik"]) or self._mikrofon is None
        if self._basili and not istek:
            return                                     # F8 basiliyken mikrofonu kesme
        if (istek and yeniden_iste) or varsayilan_degisti or bozuk:
            if varsayilan_degisti:
                self.olay("bilgi", "Windows ses aygıtı değişti, yeniden bağlanılıyor…")
            self._varsayilanlar = simdiki
            self._hepsini_ac(yeniden=True)
        elif istek or eksik or (self._dinleyici is not None and not self.ayar["gelen_acik"]):
            self._hepsini_ac(yeniden=False)

    def _hepsini_ac(self, yeniden: bool):
        with self._aygit_kilit:
            if yeniden:
                # PortAudio aygit listesini sadece acilista okur: hepsini kapat, yeniden baslat
                for nesne in (self._dinleyici, self._mikrofon):
                    if nesne:
                        nesne.kapat()
                self._dinleyici = self._mikrofon = None
                ses.yeniden_baslat()
            if self.ayar["gelen_acik"] and self._dinleyici is None:
                try:
                    self._dinleyici = ses.Dinleyici(self.ayar["dinlenen_aygit"], self._gelen_koy)
                    self.olay("bilgi", f"Dinlenen aygıt: {self._dinleyici.ad}")
                except Exception as e:  # noqa: BLE001
                    logging.exception("dinleyici")
                    self.olay("hata", f"Kulaklık/hoparlör dinlenemiyor: {str(e)[:120]}")
            elif not self.ayar["gelen_acik"] and self._dinleyici is not None:
                self._dinleyici.kapat()
                self._dinleyici = None
            if self._mikrofon is None:
                try:
                    self._mikrofon = ses.Mikrofon(self.ayar["mikrofon"], self._mikrofon_koy)
                    self.olay("bilgi", f"Mikrofon: {self._mikrofon.ad}")
                except Exception as e:  # noqa: BLE001
                    logging.exception("mikrofon")
                    self.olay("hata", f"Mikrofon açılamadı: {str(e)[:120]}")
        self._durumlari_yaz()

    # ── KARSI TARAF: hoparlor sesini konusma parcalarina bol ─────────────────
    def _gelen_koy(self, veri: bytes):
        try:
            self._gelen_q.put_nowait(veri)
        except queue.Full:
            pass

    def _seviye(self, ad: str, deger: float, esik):
        if abs(deger - self._son_seviye[ad]) > 15:     # degismediyse arayuze yollama
            self._son_seviye[ad] = deger
            self.olay(f"seviye_{ad}", deger, esik)

    def _gelen_dongu(self):
        on_kayit = collections.deque(maxlen=3)        # konusma basi kesilmesin
        tampon, aktif, sessiz, son_ara, anahtar = bytearray(), False, 0, 0.0, None
        while True:
            try:
                parca = self._gelen_q.get(timeout=0.1)
            except queue.Empty:
                parca = None
            if not self.ayar["gelen_acik"]:
                tampon, aktif, sessiz = bytearray(), False, 0
                self._seviye("gelen", 0.0, self.ayar["esik"])
                continue
            if parca is None:
                if not aktif:
                    self._seviye("gelen", 0.0, self.ayar["esik"])
                    continue
                parca = ses.SESSIZ_PARCA               # hoparlor sustu: Windows veri gondermiyor
            seviye = ses.rms(parca)
            self._seviye("gelen", seviye, self.ayar["esik"])
            if seviye >= self.ayar["esik"]:
                if not aktif:
                    aktif, anahtar, son_ara = True, f"gelen{next(self._sayac)}", time.time()
                    tampon = bytearray(b"".join(on_kayit))
                    on_kayit.clear()
                sessiz = 0
                tampon += parca
            elif aktif:
                tampon += parca
                sessiz += 1
            else:
                on_kayit.append(parca)
                continue
            if not self.tanima:
                if _sure(tampon) > EN_UZUN_SN:         # modeller yuklenirken bellek dolmasin
                    tampon, aktif, sessiz = bytearray(), False, 0
                continue
            if sessiz >= SESSIZ_SON or _sure(tampon) >= EN_UZUN_SN:
                self._is_ekle("gelen", anahtar, bytes(tampon), son=True)
                tampon, aktif, sessiz = bytearray(), False, 0
            elif time.time() - son_ara >= ARA_SN and _sure(tampon) >= 1.5:
                self._is_ekle("gelen", anahtar, bytes(tampon), son=False)
                son_ara = time.time()

    # ── SIZ: F8 basiliyken mikrofon ──────────────────────────────────────────
    def _mikrofon_koy(self, veri: bytes):
        with self._kilit:
            if self._basili:
                self._giden_tampon += veri
        self._seviye("giden", ses.rms(veri) if self._basili else 0.0, None)

    def tus(self, basili: bool):
        with self._kilit:
            if basili == self._basili:
                return
            self._basili = basili
            if basili:
                self._giden_tampon = bytearray()
                self._giden_anahtar = f"giden{next(self._sayac)}"
                self._son_ara = self._basis_zamani = time.time()
                self.olay("giden_basla", self._giden_anahtar)
                return
            pcm, anahtar = bytes(self._giden_tampon), self._giden_anahtar
            self._giden_tampon = bytearray()
        if not self.tanima:
            self.olay("giden", anahtar, "", "(modeller henüz yükleniyor, birkaç saniye sonra tekrar deneyin)", "")
        elif self._mikrofon is None:
            self.olay("giden", anahtar, "", "(mikrofon açılamadı, ana pencereden mikrofonu seçin)", "")
        elif _sure(pcm) < EN_KISA_SN:
            self.olay("giden", anahtar, "", "", "")    # kisa dokunus: altyaziyi temizler
        else:
            self._is_ekle("giden", anahtar, pcm, son=True)

    def _giden_dongu(self):
        while True:                                    # basiliyken 1.5 sn'de bir ara ceviri
            time.sleep(0.1)
            if self._basili and time.time() - self._basis_zamani > EN_UZUN_BASIS_SN:
                self.tus(False)                        # birakilis kacirildi: kaydi kendiligimizden bitir
                self.olay("tus_birakildi")
                continue
            with self._kilit:
                if not (self._basili and self.tanima) or time.time() - self._son_ara < ARA_SN \
                        or _sure(self._giden_tampon) < 1.5:
                    continue
                self._son_ara = time.time()
                pcm, anahtar = bytes(self._giden_tampon), self._giden_anahtar
            self._is_ekle("giden", anahtar, pcm, son=False)

    def kapat(self):
        with self._aygit_kilit:
            for nesne in (self._dinleyici, self._mikrofon):
                if nesne:
                    nesne.kapat()
