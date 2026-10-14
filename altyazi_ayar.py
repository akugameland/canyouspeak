"""Altyazi gorunum ayarlari penceresi: degisiklik aninda altyaziya uygulanir, pencere aciksa ornek metin gosterilir."""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, ttk

from altyazi import VARSAYILAN_STIL

ARKA, PANEL, YAZI, SOLUK = "#14161a", "#1e2127", "#e8e8e8", "#8a8f98"
YAZI_TIPI = "Segoe UI"
ADAY_YAZI_TIPLERI = ["Segoe UI", "Arial", "Calibri", "Tahoma", "Verdana", "Trebuchet MS", "Bahnschrift",
                     "Georgia", "Times New Roman", "Consolas", "Comic Sans MS", "Impact"]


class AltyaziAyar:
    def __init__(self, kok: tk.Tk, altyazi, stil: dict, kaydet):
        self.altyazi, self.kaydet = altyazi, kaydet
        self.stil = {**VARSAYILAN_STIL, **stil}
        self._yedek = (altyazi.karsi, altyazi.karsi_dil, altyazi.karsi_anahtar,
                       altyazi.ben, altyazi.ben_duyulan, altyazi.ben_dil, altyazi.ben_anahtar)
        self.p = p = tk.Toplevel(kok)
        p.title("Altyazı ayarları")
        p.configure(bg=ARKA)
        p.resizable(False, False)
        p.attributes("-topmost", True)
        p.protocol("WM_DELETE_WINDOW", self.kapat)
        self._degiskenler: dict[str, tk.Variable] = {}
        self._renk_dugmeleri: dict[str, tk.Button] = {}
        self._kur()
        self._ornek()

    # ── arayuz ───────────────────────────────────────────────────────────────
    def _kur(self):
        g = tk.Frame(self.p, bg=ARKA)
        g.pack(padx=16, pady=12)
        self._satir = 0
        mevcut = set(tkfont.families())
        tipler = [t for t in ADAY_YAZI_TIPLERI if t in mevcut] or ["Segoe UI"]

        self._baslik(g, "Yazı")
        self._secim(g, "Yazı tipi", "yazi_tipi", tipler)
        self._kaydirac(g, "Boyut", "boyut", 14, 64)
        self._kutu(g, "Kalın", "kalin")
        self._kaydirac(g, "Yazı görünürlüğü (%)", "yazi_saydamlik", 20, 100)

        self._baslik(g, "Renkler")
        self._renk(g, "Karşı tarafın çevirisi", "karsi_renk")
        self._renk(g, "Sizin söyleyeceğiniz", "ben_renk")
        self._renk(g, "\"Duyulan\" satırı", "duyulan_renk")
        self._renk(g, "Dil etiketi", "etiket_renk")
        self._renk(g, "Çerçeve", "cerceve_renk")
        self._kaydirac(g, "Çerçeve kalınlığı", "cerceve_kalinlik", 0, 6)

        self._baslik(g, "Arka plan kutusu (film altyazısı gibi)")
        self._kutu(g, "Kutuyu göster", "kutu")
        self._renk(g, "Kutu rengi", "kutu_renk")
        self._kaydirac(g, "Kutu görünürlüğü (%)", "kutu_saydamlik", 0, 100)

        self._baslik(g, "Yerleşim")
        self._kaydirac(g, "Alttan uzaklık (%)", "alt_bosluk", 0, 45)
        self._kaydirac(g, "Genişlik (%)", "genislik", 40, 100)
        self._kaydirac(g, "Karşı tarafın yazısı kaç sn kalsın", "sure", 2, 20)
        self._kutu(g, "Konuşulan dili küçük etiketle göster", "dil_etiketi")

        alt = tk.Frame(self.p, bg=ARKA)
        alt.pack(fill="x", padx=16, pady=(0, 12))
        self._dugme(alt, "Varsayılana dön", self._varsayilan).pack(side="left")
        self._dugme(alt, "Kapat", self.kapat).pack(side="right")

    def _baslik(self, g, yazi):
        tk.Label(g, text=yazi, bg=ARKA, fg=YAZI, font=(YAZI_TIPI, 10, "bold")).grid(
            row=self._satir, column=0, columnspan=2, sticky="w", pady=(10 if self._satir else 0, 2))
        self._satir += 1

    def _etiket(self, g, yazi):
        tk.Label(g, text=yazi, bg=ARKA, fg=SOLUK, font=(YAZI_TIPI, 9)).grid(row=self._satir, column=0, sticky="w", padx=(8, 12))

    def _dugme(self, ebeveyn, yazi, komut):
        return tk.Button(ebeveyn, text=yazi, command=komut, bg=PANEL, fg=YAZI, relief="flat",
                         activebackground="#2a2e36", activeforeground=YAZI, font=(YAZI_TIPI, 9), padx=10)

    def _kaydirac(self, g, yazi, anahtar, en_az, en_cok):
        self._etiket(g, yazi)
        d = tk.IntVar(value=int(self.stil[anahtar]))
        tk.Scale(g, from_=en_az, to=en_cok, orient="horizontal", variable=d, length=220, showvalue=True,
                 bg=ARKA, fg=YAZI, troughcolor=PANEL, highlightthickness=0, bd=0, font=(YAZI_TIPI, 8),
                 command=lambda _v: self._degisti(anahtar, d.get())).grid(row=self._satir, column=1, sticky="w")
        self._degiskenler[anahtar] = d
        self._satir += 1

    def _kutu(self, g, yazi, anahtar):
        d = tk.BooleanVar(value=bool(self.stil[anahtar]))
        tk.Checkbutton(g, text=yazi, variable=d, command=lambda: self._degisti(anahtar, d.get()),
                       bg=ARKA, fg=YAZI, selectcolor=PANEL, activebackground=ARKA, activeforeground=YAZI,
                       font=(YAZI_TIPI, 9)).grid(row=self._satir, column=0, columnspan=2, sticky="w", padx=4)
        self._degiskenler[anahtar] = d
        self._satir += 1

    def _secim(self, g, yazi, anahtar, degerler):
        self._etiket(g, yazi)
        d = tk.StringVar(value=self.stil[anahtar])
        k = ttk.Combobox(g, values=degerler, textvariable=d, state="readonly", width=22)
        k.bind("<<ComboboxSelected>>", lambda e: self._degisti(anahtar, d.get()))
        k.grid(row=self._satir, column=1, sticky="w", pady=2)
        self._degiskenler[anahtar] = d
        self._satir += 1

    def _renk(self, g, yazi, anahtar):
        self._etiket(g, yazi)
        b = tk.Button(g, text="      ", bg=self.stil[anahtar], relief="flat", activebackground=self.stil[anahtar],
                      command=lambda: self._renk_sec(anahtar, yazi), width=6)
        b.grid(row=self._satir, column=1, sticky="w", pady=2)
        self._renk_dugmeleri[anahtar] = b
        self._satir += 1

    def _renk_sec(self, anahtar, yazi):
        _, secilen = colorchooser.askcolor(color=self.stil[anahtar], title=yazi, parent=self.p)
        if secilen:
            self._renk_dugmeleri[anahtar].configure(bg=secilen, activebackground=secilen)
            self._degisti(anahtar, secilen)

    # ── davranis ─────────────────────────────────────────────────────────────
    def _degisti(self, anahtar, deger):
        if self.stil.get(anahtar) == deger:
            return
        self.stil[anahtar] = deger
        self.altyazi.stil_uygula(self.stil)
        self._kaydet_sonra()

    def _kaydet_sonra(self):
        # Kaydirac surukleyince saniyede onlarca degisiklik gelir; diske biraz bekleyip bir kez yaz
        if getattr(self, "_kayit", None):
            self.p.after_cancel(self._kayit)
        self._kayit = self.p.after(500, self._simdi_kaydet)

    def _simdi_kaydet(self):
        self._kayit = None
        self.kaydet(dict(self.stil))

    def _varsayilan(self):
        self.stil = dict(VARSAYILAN_STIL)
        for anahtar, d in self._degiskenler.items():
            d.set(self.stil[anahtar])
        for anahtar, b in self._renk_dugmeleri.items():
            b.configure(bg=self.stil[anahtar], activebackground=self.stil[anahtar])
        self.altyazi.stil_uygula(self.stil)
        self._kaydet_sonra()

    def _ornek(self):
        a = self.altyazi
        a.ben_yaz("I'm coming, wait two minutes. I'll go around from the left side.",
                  "Geliyorum, iki dakika bekleyin. Sol taraftan dolaşacağım.", "İngilizce", "ornek_ben")
        a.karsi_yaz("Hey, neredesin? Düşman kuzey tarafından ilerliyor, iki oyuncu daha lazım.",
                    "İngilizce", "ornek_karsi")
        if a._karsi_zamanlayici:                  # ornek, pencere acik kaldikca silinmesin
            a.p.after_cancel(a._karsi_zamanlayici)
            a._karsi_zamanlayici = None

    def kapat(self):
        if getattr(self, "_kayit", None):            # bekleyen kaydi kacirma
            self.p.after_cancel(self._kayit)
            self._simdi_kaydet()
        karsi, karsi_dil, karsi_anahtar, ben, duyulan, ben_dil, ben_anahtar = self._yedek
        self.altyazi.ben_yaz(ben, duyulan, ben_dil, ben_anahtar)
        if karsi:
            self.altyazi.karsi_yaz(karsi, karsi_dil, karsi_anahtar)
        else:
            self.altyazi._karsi_sil()
        self.p.destroy()
