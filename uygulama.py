"""CanYouSpeak: yardımcı ekran. Hiç ses çıkarmaz, kimsenin yerine konuşmaz.
Karşı tarafın söylediğini Türkçe altyazı olarak gösterir; siz F8'e basılı tutup Türkçe
konuşunca söylemeniz gereken cümleyi karşı tarafın dilinde altyazıya yazar."""
import ctypes
import logging
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import keyboard

import ayarlar
import ses
from altyazi import Altyazi
from altyazi_ayar import AltyaziAyar
from ceviri import DILLER, Motor
from fare import DUGMELER, FareDinleyici

logging.basicConfig(filename=str(ayarlar.KLASOR / "hata.log"), level=logging.WARNING,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s", encoding="utf-8")

ARKA, PANEL, YAZI, SOLUK = "#14161a", "#1e2127", "#e8e8e8", "#8a8f98"
RENK = {"yesil": "#3ddc84", "sari": "#f5c542", "kirmizi": "#ff5c5c", "gri": "#8a8f98"}
YAZI_TIPI = "Segoe UI"
VARSAYILAN_AYGIT = "Varsayılan (Windows ayarı)"
GECMIS_SINIRI = 1500               # gecmis penceresinde en fazla bu kadar satir tutulur
AYNI_HATA_SN = 30


def _no(anahtar: str) -> int:
    return int(re.sub(r"\D", "", anahtar or "") or 0)


def tus_adi(tus: str) -> str:
    return DUGMELER.get(tus, tus.upper())


class Uygulama:
    def __init__(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)     # altyazi bulanik olmasin
        except Exception:  # noqa: BLE001
            pass
        self.ayar = ayarlar.yukle()
        self.olaylar: queue.Queue = queue.Queue()
        self.kok = tk.Tk()
        self.kok.title("CanYouSpeak")
        self.kok.geometry("640x800")
        self.kok.minsize(500, 560)
        self.kok.configure(bg=ARKA)
        self.kok.attributes("-topmost", bool(self.ayar["hep_ustte"]))
        self.kok.protocol("WM_DELETE_WINDOW", self.kapat)
        self.kok.report_callback_exception = lambda *a: logging.error("arayuz hatasi", exc_info=a)
        self._tus_basili = False
        self._atama_bekliyor = False               # "değiştir"e basildi, yeni tus/fare dugmesi bekleniyor
        self._giden_durum = ("Başlıyor…", "sari")
        self._ayar_penceresi = None
        self._son_karsi_no = 0                     # altyazida gosterilen en yeni konusma
        self._son_ben_anahtar = ""
        self._son_hatalar: dict[str, float] = {}
        self._arayuz()
        self.altyazi = Altyazi(self.kok, self.ayar["altyazi_stil"])
        self.altyazi.goster(bool(self.ayar["altyazi_acik"]))

        try:
            self.motor = Motor(self.ayar, self._olay)
        except Exception as e:  # noqa: BLE001
            logging.exception("baslatma")
            messagebox.showerror("CanYouSpeak", f"Başlatılamadı:\n{e}")
            os._exit(1)
        self.fare = FareDinleyici(self._fare_olayi)
        self._tus_bagla()
        self.kok.after(1500, self._aygit_listelerini_doldur)
        self.kok.after(50, self._olaylari_isle)

    # ── arayuz ───────────────────────────────────────────────────────────────
    def _arayuz(self):
        k = self.kok
        stil = ttk.Style(k)
        stil.theme_use("clam")
        stil.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=YAZI,
                       arrowcolor=YAZI, bordercolor=PANEL, selectbackground=PANEL, selectforeground=YAZI)
        stil.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", YAZI)])
        k.option_add("*TCombobox*Listbox.background", PANEL)
        k.option_add("*TCombobox*Listbox.foreground", YAZI)

        ust = tk.Frame(k, bg=ARKA)
        ust.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(ust, text="CANYOUSPEAK", bg=ARKA, fg=YAZI, font=(YAZI_TIPI, 13, "bold")).pack(side="left")
        tk.Label(ust, text="yerel · internetsiz · ücretsiz", bg=ARKA, fg=SOLUK, font=(YAZI_TIPI, 9)).pack(side="right")

        durum = tk.Frame(k, bg=PANEL)
        durum.pack(fill="x", padx=14, pady=4)
        self.gelen_durum, self.gelen_cubuk = self._durum_satiri(durum, 0, "Karşı taraf:")
        self.giden_durum, self.giden_cubuk = self._durum_satiri(durum, 1, "Siz:")
        durum.columnconfigure(1, weight=1)

        kayit = tk.Frame(k, bg=ARKA)
        kayit.pack(fill="both", expand=True, padx=14, pady=4)
        self.metin = tk.Text(kayit, bg=PANEL, fg=YAZI, relief="flat", wrap="word", padx=10, pady=8,
                             font=(YAZI_TIPI, 11), state="disabled", cursor="arrow", height=8)
        kaydirma = tk.Scrollbar(kayit, command=self.metin.yview)
        self.metin.configure(yscrollcommand=kaydirma.set)
        kaydirma.pack(side="right", fill="y")
        self.metin.pack(side="left", fill="both", expand=True)
        self.metin.tag_configure("orj", foreground=SOLUK, font=(YAZI_TIPI, 9))
        self.metin.tag_configure("gelen", foreground="#ffffff", font=(YAZI_TIPI, 12, "bold"))
        self.metin.tag_configure("giden", foreground="#ffd84a", font=(YAZI_TIPI, 12, "bold"))
        self.metin.tag_configure("bilgi", foreground=SOLUK, font=(YAZI_TIPI, 9, "italic"))
        self.metin.tag_configure("hata", foreground=RENK["kirmizi"], font=(YAZI_TIPI, 9))

        ayar = tk.Frame(k, bg=ARKA)
        ayar.pack(fill="x", padx=14, pady=(6, 2))
        ayar.columnconfigure(1, weight=1)
        satir = 0

        self._etiket(ayar, "Sizin konuşmanız şu dile:", satir)
        dil_cerceve = tk.Frame(ayar, bg=ARKA)
        dil_cerceve.grid(row=satir, column=1, columnspan=2, sticky="w", pady=2)
        self.dil = ttk.Combobox(dil_cerceve, values=list(DILLER), state="readonly", width=16)
        self.dil.set(self.ayar["hedef_dil"] if self.ayar["hedef_dil"] in DILLER else "Otomatik")
        self.dil.bind("<<ComboboxSelected>>", lambda e: self._ayarla("hedef_dil", self.dil.get()))
        self.dil.pack(side="left")
        self.oto_etiket = tk.Label(dil_cerceve, text="", bg=ARKA, fg=SOLUK, font=(YAZI_TIPI, 9))
        self.oto_etiket.pack(side="left", padx=8)
        satir += 1

        self._etiket(ayar, "Dinlenen kulaklık / hoparlör:", satir)
        self.cikis = ttk.Combobox(ayar, state="readonly", width=44)
        self.cikis.grid(row=satir, column=1, sticky="we", pady=2)
        self.cikis.bind("<<ComboboxSelected>>", lambda e: self._aygit_secildi("dinlenen_aygit", self.cikis.get()))
        self._dugme(ayar, "↻ Yenile", self._aygitlari_yenile).grid(row=satir, column=2, rowspan=2, sticky="ns", padx=(6, 0))
        satir += 1

        self._etiket(ayar, "Mikrofon:", satir)
        self.giris = ttk.Combobox(ayar, state="readonly", width=44)
        self.giris.grid(row=satir, column=1, sticky="we", pady=2)
        self.giris.bind("<<ComboboxSelected>>", lambda e: self._aygit_secildi("mikrofon", self.giris.get()))
        satir += 1

        self._etiket(ayar, "Ses eşiği (düşük = daha hassas):", satir)
        self.esik = tk.Scale(ayar, from_=50, to=1500, resolution=10, orient="horizontal", showvalue=True,
                             bg=ARKA, fg=YAZI, troughcolor=PANEL, highlightthickness=0, bd=0, font=(YAZI_TIPI, 8),
                             command=lambda v: self._esik_degisti(int(float(v))))
        self.esik.set(int(self.ayar["esik"]))
        self.esik.grid(row=satir, column=1, columnspan=2, sticky="we")
        satir += 1

        dugmeler = tk.Frame(ayar, bg=ARKA)
        dugmeler.grid(row=satir, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._dugme(dugmeler, "Altyazı ayarları…", self._altyazi_ayarlari).pack(side="left")
        self.tus_dugme = self._dugme(dugmeler, "", self._tus_degistir)
        self.tus_dugme.pack(side="left", padx=8)

        secim = tk.Frame(k, bg=ARKA)
        secim.pack(fill="x", padx=10, pady=(6, 2))
        self._kutu(secim, "Karşı tarafı çevir", "gelen_acik", sonra=lambda: self.motor.aygitlari_yenile(False))
        self._kutu(secim, "Altyazı göster", "altyazi_acik",
                   sonra=lambda: self.altyazi.goster(bool(self.ayar["altyazi_acik"])))
        self._kutu(secim, "Bu pencere hep üstte", "hep_ustte",
                   sonra=lambda: self.kok.attributes("-topmost", bool(self.ayar["hep_ustte"])))

        tk.Label(k, text="İpucu: Oyunu \"kenarlıksız pencere\" (borderless) modunda açın. Tam ekran modunda "
                         "Windows hiçbir pencerenin oyunun üstüne çıkmasına izin vermez. Discord'un sesi hangi "
                         "kulaklıktan geliyorsa \"Dinlenen kulaklık\" o olmalı.",
                 bg=ARKA, fg=SOLUK, font=(YAZI_TIPI, 8), wraplength=600, justify="left").pack(fill="x", padx=14, pady=(2, 10))

    def _etiket(self, ebeveyn, yazi, satir):
        tk.Label(ebeveyn, text=yazi, bg=ARKA, fg=SOLUK, font=(YAZI_TIPI, 9)).grid(
            row=satir, column=0, sticky="w", padx=(0, 8), pady=2)

    def _dugme(self, ebeveyn, yazi, komut):
        return tk.Button(ebeveyn, text=yazi, command=komut, bg=PANEL, fg=YAZI, relief="flat",
                         activebackground="#2a2e36", activeforeground=YAZI, font=(YAZI_TIPI, 9), padx=8)

    def _durum_satiri(self, ebeveyn, satir, baslik):
        dikey = (8, 2) if satir == 0 else (2, 8)
        tk.Label(ebeveyn, text=baslik, bg=PANEL, fg=SOLUK, font=(YAZI_TIPI, 10)).grid(
            row=satir, column=0, sticky="w", padx=10, pady=dikey)
        etiket = tk.Label(ebeveyn, text="Başlıyor…", bg=PANEL, fg=RENK["sari"], font=(YAZI_TIPI, 10, "bold"))
        etiket.grid(row=satir, column=1, sticky="w", pady=dikey)
        cubuk = tk.Canvas(ebeveyn, width=140, height=10, bg=ARKA, highlightthickness=0)
        cubuk.grid(row=satir, column=2, sticky="e", padx=10, pady=dikey)
        cubuk.create_rectangle(0, 0, 0, 10, fill=RENK["yesil"], width=0, tags="seviye")
        cubuk.create_line(-5, 0, -5, 10, fill=RENK["sari"], tags="esik")
        return etiket, cubuk

    def _kutu(self, ebeveyn, yazi, anahtar, sonra=None):
        deger = tk.BooleanVar(value=bool(self.ayar[anahtar]))

        def degisti():
            self._ayarla(anahtar, deger.get())
            if sonra:
                sonra()
        tk.Checkbutton(ebeveyn, text=yazi, variable=deger, command=degisti, bg=ARKA, fg=YAZI, selectcolor=PANEL,
                       activebackground=ARKA, activeforeground=YAZI, font=(YAZI_TIPI, 9)).pack(side="left", padx=4)

    def _ayarla(self, anahtar, deger):
        self.ayar[anahtar] = deger
        try:
            ayarlar.kaydet(self.ayar)
        except OSError:
            logging.exception("ayar kaydi")

    def _esik_degisti(self, deger: int):
        self.ayar["esik"] = deger                     # motor her parcada okur; diske kaydetmeyi geciktir
        if getattr(self, "_esik_kayit", None):
            self.kok.after_cancel(self._esik_kayit)
        self._esik_kayit = self.kok.after(600, lambda: self._ayarla("esik", self.ayar["esik"]))

    # ── ses aygitlari ────────────────────────────────────────────────────────
    def _aygit_listelerini_doldur(self):
        def listele():
            try:
                cikislar, girisler = ses.cikis_aygitlari(), ses.giris_aygitlari()
            except Exception:  # noqa: BLE001
                logging.exception("aygit listesi")
                cikislar, girisler = [], []
            self.olaylar.put(("aygit_listesi", cikislar, girisler))
        threading.Thread(target=listele, daemon=True).start()

    def _liste_kur(self, kutu: ttk.Combobox, adlar: list[str], secili: str):
        degerler = [VARSAYILAN_AYGIT] + adlar
        if secili and not any(secili.lower() in a.lower() for a in adlar):
            degerler.append(f"{secili} (bağlı değil)")
        kutu.configure(values=degerler)
        if not secili:
            kutu.set(VARSAYILAN_AYGIT)
        else:
            kutu.set(next((a for a in adlar if secili.lower() in a.lower()), f"{secili} (bağlı değil)"))

    def _aygit_secildi(self, anahtar: str, deger: str):
        ad = "" if deger == VARSAYILAN_AYGIT else deger.replace(" (bağlı değil)", "")
        if ad == self.ayar[anahtar]:
            return
        self._ayarla(anahtar, ad)
        self.motor.aygitlari_yenile(True)

    def _aygitlari_yenile(self):
        self.motor.aygitlari_yenile(True)              # yeni takilan aygitlari gormek icin ses sistemi yeniden baslar
        self.kok.after(2500, self._aygit_listelerini_doldur)

    def _altyazi_ayarlari(self):
        if self._ayar_penceresi and self._ayar_penceresi.p.winfo_exists():
            self._ayar_penceresi.p.lift()
            return
        self._ayar_penceresi = AltyaziAyar(self.kok, self.altyazi, self.ayar["altyazi_stil"],
                                           lambda stil: self._ayarla("altyazi_stil", dict(stil)))

    # ── bas-konus tusu ───────────────────────────────────────────────────────
    def _tus_bagla(self):
        """Bas-konus: klavye tusu ya da fare orta/yan tusu ("fare:yan1" gibi)."""
        self._atama_bekliyor = False
        keyboard.unhook_all()
        tus = self.ayar["ptt_tusu"]
        if tus in DUGMELER:
            self.fare.dinle(True)                          # klavye hic dinlenmez
        else:
            self.fare.dinle(False)                         # fare hic dinlenmez
            # Tus ADIYLA eslestirilir, tarama koduyla degil: makro/klavye yazilimlari (G Hub, Synapse,
            # AutoHotkey) tusu tarama kodu olmadan gonderebiliyor; on_press_key o zaman hic tetiklenmiyordu
            # (2026-10-14 SendInput ile goruldu).
            aranan = tus.lower()

            def klavye(olay):
                if (olay.name or "").lower() == aranan:
                    self._tus(olay.event_type == keyboard.KEY_DOWN)
            keyboard.hook(klavye)
        self.tus_dugme.config(text=f"Bas-konuş: {tus_adi(tus)}  (değiştir)")
        self._giden_durumu_yaz()

    def _tus(self, basili: bool):
        if basili == self._tus_basili:                     # tus tekrari
            return
        self._tus_basili = basili
        self.olaylar.put(("tus_durum", basili))
        self.motor.tus(basili)

    def _fare_olayi(self, dugme: str, basili: bool):
        """Fare is parcaciginda calisir: kisa tut."""
        if self._atama_bekliyor:
            if basili:
                self._atama_bekliyor = False
                self.olaylar.put(("tus", dugme))
        elif dugme == self.ayar["ptt_tusu"]:
            self._tus(basili)

    def _tus_degistir(self):
        if self._tus_basili:                               # konusurken atama yapma
            return
        self.tus_dugme.config(text="Klavyede bir tuşa ya da farenin orta/yan tuşuna basın… (vazgeç: Esc)")
        keyboard.unhook_all()
        self._atama_bekliyor = True
        self.fare.dinle(True)

        def klavye(olay):
            if self._atama_bekliyor and olay.event_type == keyboard.KEY_DOWN and olay.name:
                self._atama_bekliyor = False
                self.olaylar.put(("tus", None if olay.name == "esc" else olay.name))
        keyboard.hook(klavye)

    # ── motordan gelen olaylar ───────────────────────────────────────────────
    def _olay(self, *veri):
        self.olaylar.put(veri)

    def _olaylari_isle(self):
        try:
            for _ in range(500):                           # cok olay birikse bile arayuz donmasin
                tur, *veri = self.olaylar.get_nowait()
                try:
                    self._olay_isle(tur, veri)
                except Exception:  # noqa: BLE001
                    logging.exception("olay %s", tur)
        except queue.Empty:
            pass
        self.kok.after(50, self._olaylari_isle)

    def _olay_isle(self, tur: str, veri: list):
        if tur == "durum_gelen":
            self.gelen_durum.config(text=veri[0], fg=RENK[veri[1]])
        elif tur == "durum_giden":
            self._giden_durum = (veri[0], veri[1])
            self._giden_durumu_yaz()
        elif tur == "tus_durum":
            self._giden_durumu_yaz()
        elif tur == "tus_birakildi":                       # motor uzun basisi kendisi bitirdi
            self._tus_basili = False
            self._giden_durumu_yaz()
        elif tur == "seviye_gelen":
            self._seviye_ciz(self.gelen_cubuk, *veri)
        elif tur == "seviye_giden":
            self._seviye_ciz(self.giden_cubuk, *veri)
        elif tur == "gelen":
            anahtar, orj, cev, dil = veri
            self._satir(anahtar, orj, cev, "gelen", dil)
            if _no(anahtar) >= self._son_karsi_no:         # eski konusmanin gec gelen sonucu yenisini ezmesin
                self._son_karsi_no = _no(anahtar)
                self.altyazi.karsi_yaz(cev, dil, anahtar)
        elif tur == "giden_basla":
            self._son_ben_anahtar = veri[0]
            self.altyazi.ben_yaz("● Dinliyorum…", anahtar=veri[0])
        elif tur == "giden":
            anahtar, orj, cev, dil = veri
            if orj or cev:                                 # bos: kisa F8 dokunusu, sadece altyazi temizlenir
                self._satir(anahtar, orj, cev, "giden", dil)
            if anahtar == self._son_ben_anahtar:           # onceki F8'in gec gelen sonucu yenisini ezmesin
                self.altyazi.ben_yaz(cev, orj, dil, anahtar)
        elif tur == "oto_dil":
            self.oto_etiket.config(text=f"(otomatik şu an: {veri[0]})")
        elif tur == "bilgi":
            self._yaz("bilgi", veri[0])
        elif tur == "hata":
            simdi = time.time()
            if simdi - self._son_hatalar.get(veri[0], 0) > AYNI_HATA_SN:   # ayni hata yagmasin
                self._son_hatalar[veri[0]] = simdi
                self._yaz("hata", veri[0])
        elif tur == "tus":
            if veri[0]:
                self._ayarla("ptt_tusu", veri[0])
            self._tus_bagla()
        elif tur == "aygit_listesi":
            cikislar, girisler = veri
            self._liste_kur(self.cikis, cikislar, self.ayar["dinlenen_aygit"])
            self._liste_kur(self.giris, girisler, self.ayar["mikrofon"])

    def _giden_durumu_yaz(self):
        yazi, renk = self._giden_durum
        if yazi == "Dinliyor":
            yazi, renk = (("KONUŞUN… (tuşu bırakınca biter)", "kirmizi") if self._tus_basili
                          else (f"Hazır: {tus_adi(self.ayar['ptt_tusu'])} basılı tutup Türkçe konuşun", "yesil"))
        self.giden_durum.config(text=yazi, fg=RENK[renk])

    def _seviye_ciz(self, cubuk, deger: float, esik):
        olcek = lambda v: min(140, int(140 * (v / 3000) ** 0.5))   # noqa: E731
        cubuk.coords("seviye", 0, 0, olcek(deger), 10)
        if esik is not None:
            x = olcek(esik)
            cubuk.coords("esik", x, 0, x, 10)

    def _yaz(self, etiket: str, yazi: str):
        m = self.metin
        m.configure(state="normal")
        m.insert("end", yazi + "\n", etiket)
        self._gecmisi_kirp()
        m.configure(state="disabled")
        m.see("end")

    def _satir(self, anahtar: str, orj: str, cev: str, etiket: str, dil: str = ""):
        """Ayni konusma satirini canli gunceller (ceviri parca parca gelir)."""
        m = self.metin
        m.configure(state="normal")
        sondaydi = m.yview()[1] > 0.98
        # Her konusma kendi etiketini tasir; guncellemede o etiketin araligi silinip yeniden yazilir
        satir = f"satir_{anahtar}"
        araliklar = m.tag_ranges(satir)
        if araliklar:
            yer = str(araliklar[0])
            m.delete(yer, araliklar[-1])
        else:
            yer = "end-1c"
        isaret = "🌍" if etiket == "gelen" else "🎤"
        dil_notu = (f"[{dil}] " if etiket == "gelen" else f"[→ {dil}] ") if dil else ""
        m.insert(yer, f"{isaret} {dil_notu}{orj}\n", ("orj", satir), f"→ {cev}\n\n", (etiket, satir))
        if not araliklar:
            self._gecmisi_kirp()
        m.configure(state="disabled")
        if sondaydi:
            m.see("end")

    def _gecmisi_kirp(self):
        """Saatlerce acik kalinca gecmis sonsuza buyumesin: en eski satirlari ve etiketlerini sil."""
        m = self.metin
        satir_sayisi = int(m.index("end-1c").split(".")[0])
        if satir_sayisi <= GECMIS_SINIRI:
            return
        m.delete("1.0", f"{satir_sayisi - GECMIS_SINIRI * 2 // 3}.0")
        for etiket in m.tag_names():
            if etiket.startswith("satir_") and not m.tag_ranges(etiket):
                m.tag_delete(etiket)

    def kapat(self):
        try:
            keyboard.unhook_all()
            self.fare.kapat()
            self.motor.kapat()
        except Exception:  # noqa: BLE001
            logging.exception("kapatma")
        finally:
            os._exit(0)

    def calis(self):
        self.kok.mainloop()


def _tek_kopya() -> bool:
    """Uygulama ikinci kez acilirsa iki altyazi + iki kat ekran karti kullanimi olmasin."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "CanYouSpeak_TekKopya")
    return ctypes.windll.kernel32.GetLastError() != 183          # ERROR_ALREADY_EXISTS


def main():
    # pythonw ile acilinca stdout/stderr yok; bir kutuphane yazmaya kalkarsa cokmesin
    if sys.stdout is None or sys.stderr is None:
        bos = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or bos
        sys.stderr = sys.stderr or bos
    threading.excepthook = lambda a: logging.error("is parcacigi hatasi", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    sys.excepthook = lambda *a: logging.error("beklenmeyen hata", exc_info=a)
    if not _tek_kopya():
        kok = tk.Tk()
        kok.withdraw()
        messagebox.showinfo("CanYouSpeak", "Uygulama zaten açık (görev çubuğuna bakın).")
        return
    Uygulama().calis()


if __name__ == "__main__":
    main()
