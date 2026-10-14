"""Ekranin altinda film altyazisi gibi duran, her zaman en onde, tiklamalari gecirten katman.

Alt blok (karsi taraf): kucuk dil etiketi ("İTALYANCA") + Turkce ceviri; birkac saniye sonra kaybolur.
Ust blok (siz):         kucuk "→ İNGİLİZCE" etiketi + gri "Duyulan" + soylemeniz gereken ceviri;
                        bir sonraki bas-konus basisina kadar kalir.

Iki pencere kullanilir: arkada istege bagli yari saydam kutu, onde renk anahtarli (saydam zeminli) yazi.
Tek pencerede yazi ve kutuya ayri saydamlik verilemiyor.

Uzun konusmada yazi kademeli kuculur (okuma odagi bozulmasin diye):
- Satirlar alttan yukari buyur; son okunan satirin yeri sabit kalir.
- Ayni konusma surerken yazi sadece kuculur, geri buyumez (zipla-kucul olmaz); yeni konusma temel boyutla baslar.
- Az sayida sabit adim var (100/85/72/62 %); en kucukte de sigmazsa basindan kirpilir ("…").
Not: Tam ekran (exclusive fullscreen) oyunlarda hicbir pencere oyunun ustune cikamaz;
oyunu "kenarliksiz pencere" (borderless) modunda calistirin.
"""
import ctypes
import tkinter as tk
import tkinter.font as tkfont

ANAHTAR_RENK = "#010203"         # yazi penceresinde saydam yapilan renk

VARSAYILAN_STIL = {
    "yazi_tipi": "Segoe UI",
    "boyut": 26,
    "kalin": True,
    "karsi_renk": "#ffffff",
    "ben_renk": "#ffd84a",
    "duyulan_renk": "#c8c8c8",
    "etiket_renk": "#8fd0ff",
    "cerceve_renk": "#000000",
    "cerceve_kalinlik": 2,
    "kutu": False,               # yazinin arkasinda film altyazisi gibi koyu kutu
    "kutu_renk": "#000000",
    "kutu_saydamlik": 55,        # kutunun gorunurlugu (%)
    "yazi_saydamlik": 100,       # yazinin gorunurlugu (%)
    "alt_bosluk": 7,             # ekranin altindan uzaklik (%)
    "genislik": 80,              # altyazi alaninin ekran genisligine orani (%)
    "sure": 7,                   # karsi tarafin yazisi kac saniye kalsin
    "dil_etiketi": True,
}
OLCEK_ADIMLARI = (1.0, 0.85, 0.72, 0.62)
SATIR_SINIRI = (2, 3, 3, 3)      # her adimda izin verilen satir sayisi
EN_KUCUK_BOYUT = 12

_u32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40


TIKLAMA_GECIR = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE


def _tiklama_gecir(hwnd: int):
    """Fare tiklamalari altyazinin icinden arkadaki pencereye gecsin, odak calinmasin.
    Dikkat (2026-10-14 kullanici bildirdi): Tk, -alpha / -transparentcolor / -topmost her
    ayarlandiginda pencere stilini kendi bildigiyle yeniden yaziyor ve WS_EX_TRANSPARENT siliniyor;
    yazinin ustune tiklayinca arkadaki secenege tiklanamiyordu. Bu yuzden her ayardan sonra ve
    duzenli olarak yeniden uygulanir."""
    stil = _u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if stil & TIKLAMA_GECIR != TIKLAMA_GECIR:
        _u32.SetWindowLongW(hwnd, GWL_EXSTYLE, stil | TIKLAMA_GECIR)


def _katman(kok: tk.Tk, zemin: str) -> tuple[tk.Toplevel, int]:
    p = tk.Toplevel(kok)
    p.overrideredirect(True)
    p.configure(bg=zemin)
    p.attributes("-topmost", True)
    p.update_idletasks()
    hwnd = _u32.GetParent(p.winfo_id())
    _tiklama_gecir(hwnd)
    return p, hwnd


def _temiz_stil(stil: dict | None) -> dict:
    """Ayar dosyasindan gelen bozuk/eksik degerler altyaziyi cokertmesin."""
    sonuc = dict(VARSAYILAN_STIL)
    for k, v in (stil or {}).items():
        if k not in VARSAYILAN_STIL:
            continue
        ornek = VARSAYILAN_STIL[k]
        try:
            if isinstance(ornek, bool):
                sonuc[k] = bool(v)
            elif isinstance(ornek, int):
                sonuc[k] = int(v)
            elif isinstance(ornek, str) and isinstance(v, str) and v:
                if k.endswith("_renk") and not (v.startswith("#") and len(v) in (4, 7)):
                    continue
                sonuc[k] = v
        except (TypeError, ValueError):
            pass
    sinirlar = {"boyut": (10, 80), "cerceve_kalinlik": (0, 8), "kutu_saydamlik": (0, 100),
                "yazi_saydamlik": (10, 100), "alt_bosluk": (0, 60), "genislik": (30, 100), "sure": (1, 60)}
    for k, (alt, ust) in sinirlar.items():
        sonuc[k] = min(ust, max(alt, sonuc[k]))
    return sonuc


def _en_one(hwnd: int, goster: bool = False, altina: int | None = None):
    """altina verilirse pencere o pencerenin hemen altina konur. Denendi: kutu gizlenip yeniden
    gosterilince yazinin ustune cikiyor ve iki pencereye HWND_TOPMOST vermek sirayi duzeltmiyor."""
    bayrak = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | (SWP_SHOWWINDOW if goster else 0)
    _u32.SetWindowPos(hwnd, altina if altina else HWND_TOPMOST, 0, 0, 0, 0, bayrak)


class Altyazi:
    def __init__(self, kok: tk.Tk, stil: dict):
        self.kok = kok
        self.stil = _temiz_stil(stil)
        self._satir_yuk: dict[tuple, int] = {}         # yazi tipi -> satir yuksekligi (onbellek)
        self.kutu, self.kutu_hwnd = _katman(kok, self.stil["kutu_renk"])
        self.p, self.hwnd = _katman(kok, ANAHTAR_RENK)
        self.p.attributes("-transparentcolor", ANAHTAR_RENK)
        self.c = tk.Canvas(self.p, bg=ANAHTAR_RENK, highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        self.acik = True
        self.karsi = self.karsi_dil = self.karsi_anahtar = ""
        self.ben = self.ben_duyulan = self.ben_dil = self.ben_anahtar = ""
        self._adim: dict[str, int] = {}              # konusma anahtari -> kullanilan olcek adimi (sadece buyur)
        self._karsi_zamanlayici = None
        self._yerlestir()
        self._ustte_tut()

    # ── genel ────────────────────────────────────────────────────────────────
    def _yerlestir(self):
        ekran_g, ekran_y = self.p.winfo_screenwidth(), self.p.winfo_screenheight()
        self.gen = int(ekran_g * self.stil["genislik"] / 100)
        self.yuk = int(ekran_y * 0.5)
        self.x = (ekran_g - self.gen) // 2
        self.y = ekran_y - self.yuk - int(ekran_y * self.stil["alt_bosluk"] / 100)
        self.p.geometry(f"{self.gen}x{self.yuk}+{self.x}+{self.y}")
        self.c.configure(width=self.gen, height=self.yuk)
        self.p.attributes("-alpha", self.stil["yazi_saydamlik"] / 100)
        self.kutu.configure(bg=self.stil["kutu_renk"])
        self.kutu.attributes("-alpha", self.stil["kutu_saydamlik"] / 100)
        self.p.update_idletasks()
        _tiklama_gecir(self.hwnd)                      # Tk az once stili ezdi: tiklama gecirmeyi geri koy
        _tiklama_gecir(self.kutu_hwnd)

    def _ustte_tut(self):
        # Bazi oyunlar kendini en one alir; katmanlari duzenli olarak tekrar en one koy (odak calmadan).
        # Yazi en one, kutu yazinin hemen altina. Tiklama gecirme de her seferinde denetlenir.
        if self.acik:
            _tiklama_gecir(self.hwnd)
            _tiklama_gecir(self.kutu_hwnd)
            _en_one(self.hwnd)
            _en_one(self.kutu_hwnd, altina=self.hwnd)
        self.p.after(1500, self._ustte_tut)

    def goster(self, acik: bool):
        self.acik = acik
        if acik:
            self.p.deiconify()
            self.p.update_idletasks()
            _tiklama_gecir(self.hwnd)
            _en_one(self.hwnd, goster=True)
            self._ciz()
        else:
            self.p.withdraw()
            self.kutu.withdraw()

    def stil_uygula(self, stil: dict):
        self.stil = _temiz_stil(stil)
        self._adim.clear()
        self._yerlestir()
        self._ciz()

    # ── icerik ───────────────────────────────────────────────────────────────
    def karsi_yaz(self, metin: str, dil: str = "", anahtar: str = ""):
        self.karsi, self.karsi_dil, self.karsi_anahtar = metin, dil, anahtar
        if self._karsi_zamanlayici:
            self.p.after_cancel(self._karsi_zamanlayici)
        self._karsi_zamanlayici = self.p.after(int(self.stil["sure"] * 1000), self._karsi_sil)
        self._ciz()

    def _karsi_sil(self):
        self._karsi_zamanlayici = None
        self.karsi = ""
        self._ciz()

    def ben_yaz(self, metin: str, duyulan: str = "", dil: str = "", anahtar: str = ""):
        """duyulan: uygulamanin sizden anladigi Turkce; yanlis anladiysa soylemeden once gorun."""
        self.ben, self.ben_duyulan, self.ben_dil, self.ben_anahtar = metin, duyulan, dil, anahtar
        self._ciz()

    # ── cizim ────────────────────────────────────────────────────────────────
    def _yazi_tipi(self, boyut: int, kalin: bool | None = None):
        kalin = self.stil["kalin"] if kalin is None else kalin
        return (self.stil["yazi_tipi"], boyut, "bold" if kalin else "normal")

    def _satir_sayisi(self, metin: str, boyut: int) -> int:
        kimlik = self.c.create_text(0, 0, text=metin, font=self._yazi_tipi(boyut), width=self.gen - 40, anchor="nw")
        x1, y1, x2, y2 = self.c.bbox(kimlik)
        self.c.delete(kimlik)
        yazi_tipi = self._yazi_tipi(boyut)
        if yazi_tipi not in self._satir_yuk:          # her cizimde yeni Font nesnesi olusturma
            self._satir_yuk[yazi_tipi] = max(1, tkfont.Font(font=yazi_tipi).metrics("linespace"))
        return max(1, round((y2 - y1) / self._satir_yuk[yazi_tipi]))

    def _sigdir(self, metin: str, anahtar: str) -> tuple[str, int]:
        """Metni sabit adimlarla kucultup sigdir. Ayni konusmada adim sadece buyur (yazi geri buyumez)."""
        temel = int(self.stil["boyut"])
        if len(self._adim) > 50:                       # eski konusmalarin kaydi birikmesin
            self._adim = {k: v for k, v in self._adim.items() if k in (self.karsi_anahtar, self.ben_anahtar)}
        bas = self._adim.get(anahtar, 0)
        for i in range(bas, len(OLCEK_ADIMLARI)):
            boyut = max(EN_KUCUK_BOYUT, int(temel * OLCEK_ADIMLARI[i]))
            if self._satir_sayisi(metin, boyut) <= SATIR_SINIRI[i]:
                self._adim[anahtar] = i
                return metin, boyut
        # En kucukte de sigmiyor: en yeni kisim gorunsun diye bastan kelime kelime kirp
        son = len(OLCEK_ADIMLARI) - 1
        self._adim[anahtar] = son
        boyut = max(EN_KUCUK_BOYUT, int(temel * OLCEK_ADIMLARI[son]))
        kelimeler = metin.split()
        while len(kelimeler) > 3 and self._satir_sayisi("… " + " ".join(kelimeler), boyut) > SATIR_SINIRI[son]:
            kelimeler = kelimeler[max(1, len(kelimeler) // 8):]
        return "… " + " ".join(kelimeler), boyut

    def _yazi(self, y: int, metin: str, renk: str, boyut: int, kalin: bool | None = None) -> int:
        """Cerceveli, ortali, alt kenari y'de olan yazi. Ust kenarin y'sini dondurur."""
        x = self.gen // 2
        yazi_tipi = self._yazi_tipi(boyut, kalin)
        genislik = self.gen - 40
        k = int(self.stil["cerceve_kalinlik"])
        if k > 0:
            for dx in (-k, 0, k):
                for dy in (-k, 0, k):
                    if dx or dy:
                        self.c.create_text(x + dx, y + dy, text=metin, fill=self.stil["cerceve_renk"],
                                           font=yazi_tipi, width=genislik, justify="center", anchor="s")
        kimlik = self.c.create_text(x, y, text=metin, fill=renk, font=yazi_tipi,
                                    width=genislik, justify="center", anchor="s")
        return self.c.bbox(kimlik)[1]

    def _etiket(self, y: int, metin: str, ana_boyut: int) -> int:
        if not (metin and self.stil["dil_etiketi"]):
            return y
        return self._yazi(y, metin.upper(), self.stil["etiket_renk"], max(9, int(ana_boyut * 0.42)), kalin=True) - 1

    def _ciz(self):
        self.c.delete("all")
        if not self.acik:
            return
        y = self.yuk - 6
        bosluk = max(6, int(self.stil["boyut"]) // 3)
        if self.karsi:
            metin, boyut = self._sigdir(self.karsi, self.karsi_anahtar or "karsi")
            y = self._yazi(y, metin, self.stil["karsi_renk"], boyut)
            y = self._etiket(y, self.karsi_dil, boyut) - bosluk
        if self.ben:
            metin, boyut = self._sigdir(self.ben, self.ben_anahtar or "ben")
            y = self._yazi(y, metin, self.stil["ben_renk"], boyut) - 2
            if self.ben_duyulan:
                y = self._yazi(y, f"Duyulan: {self.ben_duyulan}", self.stil["duyulan_renk"],
                               max(10, int(boyut * 0.55)), kalin=False) - 1
            self._etiket(y, f"→ {self.ben_dil}" if self.ben_dil else "", boyut)
        self._kutu_ayarla()

    def _kutu_ayarla(self):
        kutu = self.c.bbox("all") if self.stil["kutu"] and (self.karsi or self.ben) else None
        if not kutu:
            self.kutu.withdraw()
            return
        pay = max(8, int(self.stil["boyut"]) // 3)
        x1, y1, x2, y2 = kutu
        self.kutu.geometry(f"{x2 - x1 + 2 * pay}x{y2 - y1 + 2 * pay}+{self.x + x1 - pay}+{self.y + y1 - pay}")
        if self.kutu.state() != "normal":
            self.kutu.deiconify()
            self.kutu.update_idletasks()
            _tiklama_gecir(self.kutu_hwnd)
        _en_one(self.hwnd)
        _en_one(self.kutu_hwnd, goster=True, altina=self.hwnd)
