"""Ses kaynaklari: Discord'u dinleme (WASAPI loopback) ve mikrofon. Uygulama hic ses calmaz."""
import ctypes
import logging
import threading

import numpy as np
import pyaudiowpatch as pyaudio

GIRIS_HIZI = 16000                          # modele giden ses
PARCA_MS = 100
PARCA_BAYT = GIRIS_HIZI * PARCA_MS // 1000 * 2
SESSIZ_PARCA = b"\0" * PARCA_BAYT

log = logging.getLogger("ses")
_pa = None
_pa_kilit = threading.RLock()


def pa() -> pyaudio.PyAudio:
    global _pa
    with _pa_kilit:
        if _pa is None:
            _pa = pyaudio.PyAudio()
        return _pa


def yeniden_baslat():
    """PortAudio aygit listesini acilista bir kez okur; kulaklik takilinca ya da varsayilan aygit
    degisince gormez. Tum akislar kapatildiktan sonra cagrilmali."""
    global _pa
    with _pa_kilit:
        if _pa is not None:
            try:
                _pa.terminate()
            except Exception:  # noqa: BLE001
                log.exception("portaudio kapatma")
        _pa = None


# ── Windows'un varsayilan aygiti (winmm; PortAudio'nun eski listesinden bagimsiz) ──
_winmm = ctypes.windll.winmm
DRVM_MAPPER_PREFERRED_GET = 0x2015
WAVE_MAPPER = 0xFFFFFFFF


class _CIKIS_OZ(ctypes.Structure):
    _fields_ = [("wMid", ctypes.c_ushort), ("wPid", ctypes.c_ushort), ("vDriverVersion", ctypes.c_uint),
                ("szPname", ctypes.c_wchar * 32), ("dwFormats", ctypes.c_uint), ("wChannels", ctypes.c_ushort),
                ("wReserved1", ctypes.c_ushort), ("dwSupport", ctypes.c_uint)]


class _GIRIS_OZ(ctypes.Structure):
    _fields_ = [("wMid", ctypes.c_ushort), ("wPid", ctypes.c_ushort), ("vDriverVersion", ctypes.c_uint),
                ("szPname", ctypes.c_wchar * 32), ("dwFormats", ctypes.c_uint), ("wChannels", ctypes.c_ushort),
                ("wReserved1", ctypes.c_ushort)]


def _varsayilan(cikis: bool) -> str:
    try:
        no, bayrak = ctypes.c_uint(), ctypes.c_uint()
        mesaj = _winmm.waveOutMessage if cikis else _winmm.waveInMessage
        if mesaj(WAVE_MAPPER, DRVM_MAPPER_PREFERRED_GET, ctypes.byref(no), ctypes.byref(bayrak)) != 0:
            return ""
        oz = _CIKIS_OZ() if cikis else _GIRIS_OZ()
        al = _winmm.waveOutGetDevCapsW if cikis else _winmm.waveInGetDevCapsW
        if al(no.value, ctypes.byref(oz), ctypes.sizeof(oz)) != 0:
            return ""
        return oz.szPname
    except Exception:  # noqa: BLE001
        return ""


def varsayilan_cikis_adi() -> str:
    return _varsayilan(True)


def varsayilan_giris_adi() -> str:
    return _varsayilan(False)


# ── aygit listeleri ──────────────────────────────────────────────────────────
def _loopback_adi(ad: str) -> str:
    return ad.replace(" [Loopback]", "")


def cikis_aygitlari() -> list[str]:
    """Dinlenebilecek kulaklik/hoparlorler (WASAPI loopback)."""
    with _pa_kilit:
        return sorted({_loopback_adi(d["name"]) for d in pa().get_loopback_device_info_generator()})


def giris_aygitlari() -> list[str]:
    """Mikrofonlar (WASAPI adlari kirpilmamis oldugu icin onlar)."""
    with _pa_kilit:
        p = pa()
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        adlar = set()
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if d["hostApi"] == wasapi and d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice"):
                adlar.add(d["name"])
        return sorted(adlar)


def loopback_bul(ad_parcasi: str = "") -> dict:
    p = pa()
    if ad_parcasi:
        for d in p.get_loopback_device_info_generator():
            if ad_parcasi.lower() in d["name"].lower():
                return d
    return p.get_default_wasapi_loopback()


def giris_bul(ad_parcasi: str) -> int | None:
    """Adinda ad_parcasi gecen mikrofon (MME; Windows hizi kendisi donusturur). Yoksa None = varsayilan.
    MME adlari 31 karakterde kesildigi icin karsilastirma kirpilmis adla yapilir."""
    if not ad_parcasi:
        return None
    p = pa()
    mme = p.get_host_api_info_by_type(pyaudio.paMME)["index"]
    aranan = ad_parcasi.lower()[:31]
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["hostApi"] == mme and d["maxInputChannels"] > 0 and \
                (aranan in d["name"].lower() or d["name"].lower() in aranan):
            return i
    return None


def mono16k(veri: bytes, kanal: int, hiz: int) -> bytes:
    a = np.frombuffer(veri, np.int16).astype(np.float32)
    if kanal > 1:
        a = a[: len(a) // kanal * kanal].reshape(-1, kanal).mean(axis=1)
    if hiz != GIRIS_HIZI and len(a):
        if hiz % GIRIS_HIZI == 0:
            k = hiz // GIRIS_HIZI
            a = a[: len(a) // k * k].reshape(-1, k).mean(axis=1)
        else:
            n = int(len(a) * GIRIS_HIZI / hiz)
            a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)
    return np.clip(a, -32768, 32767).astype(np.int16).tobytes()


def rms(veri: bytes) -> float:
    a = np.frombuffer(veri, np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(a * a))) if len(a) else 0.0


class _Akis:
    def __init__(self, teslim, kanal: int, hiz: int, aygit_idx):
        self._teslim, self._kanal, self._hiz = teslim, kanal, hiz
        with _pa_kilit:
            self._akis = pa().open(format=pyaudio.paInt16, channels=kanal, rate=hiz, input=True,
                                   input_device_index=aygit_idx, frames_per_buffer=hiz * PARCA_MS // 1000,
                                   stream_callback=self._geri_cagri)

    def _geri_cagri(self, veri, kare, zaman, durum):
        try:
            self._teslim(mono16k(veri, self._kanal, self._hiz))
        except Exception:  # noqa: BLE001
            log.exception("ses akisi")
        return None, pyaudio.paContinue

    def calisiyor(self) -> bool:
        """Aygit cikarilinca akis kendiliginden durur."""
        try:
            return self._akis.is_active()
        except Exception:  # noqa: BLE001
            return False

    def kapat(self):
        try:
            self._akis.stop_stream()
            self._akis.close()
        except Exception:  # noqa: BLE001
            pass


class Dinleyici(_Akis):
    """Kulakliga/hoparlore giden sesi (Discord dahil) yakalar, 16 kHz mono parcalar uretir.
    Not: Windows, hicbir sey calmiyorken loopback'ten veri gondermez."""

    def __init__(self, ad_parcasi: str, teslim):
        with _pa_kilit:
            d = loopback_bul(ad_parcasi)
        self.ad = _loopback_adi(d["name"])
        super().__init__(teslim, d["maxInputChannels"], int(d["defaultSampleRate"]), d["index"])


class Mikrofon(_Akis):
    def __init__(self, ad_parcasi: str, teslim):
        with _pa_kilit:
            idx = giris_bul(ad_parcasi)
            self.ad = pa().get_device_info_by_index(idx)["name"] if idx is not None \
                else pa().get_default_input_device_info()["name"]
        super().__init__(teslim, 1, GIRIS_HIZI, idx)
