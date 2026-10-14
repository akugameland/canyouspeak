"""Fare tusuyla bas-konus: orta tus ve iki yan tus (geri/ileri).

Neden Raw Input (dusuk seviye fare kancasi degil): kanca (WH_MOUSE_LL) Windows'un fare akisini her
harekette Python kodu donene kadar bekletir; 1000 Hz oyun faresinde oyunda fare gecikmesine yol acabilir.
Raw Input olaylari ise sadece bildirim olarak kuyruga gelir, fareyi hic bekletmez. Sadece bir fare
tusu atanmissa (ya da tus atanirken) dinlenir; klavye tusu seciliyse hic dinlenmez.
Sol/sag tik bilerek desteklenmez: oyunu ve ayar dugmelerini bozardi.
"""
import ctypes
import logging
import threading
from ctypes import wintypes

DUGMELER = {"fare:orta": "Fare orta tuşu", "fare:yan1": "Fare yan tuşu 1 (geri)", "fare:yan2": "Fare yan tuşu 2 (ileri)"}

WM_INPUT, WM_CLOSE, WM_DESTROY, WM_APP = 0x00FF, 0x0010, 0x0002, 0x8000
RIDEV_INPUTSINK, RIDEV_REMOVE = 0x00000100, 0x00000001
RID_INPUT, RIM_TYPEMOUSE = 0x10000003, 0
HWND_MESSAGE = wintypes.HWND(-3)
# RAWMOUSE.usButtonFlags
_GECIS = {0x0010: ("fare:orta", True), 0x0020: ("fare:orta", False),
          0x0040: ("fare:yan1", True), 0x0080: ("fare:yan1", False),
          0x0100: ("fare:yan2", True), 0x0200: ("fare:yan2", False)}

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wintypes.USHORT), ("_dolgu", wintypes.USHORT),
                ("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT),
                ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG),
                ("ulExtraInformation", wintypes.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u32.DefWindowProcW.restype = LRESULT
_u32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
_u32.RegisterClassExW.restype = wintypes.ATOM
_u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                 wintypes.HINSTANCE, wintypes.LPVOID]
_u32.CreateWindowExW.restype = wintypes.HWND
_u32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
_u32.RegisterRawInputDevices.restype = wintypes.BOOL
_u32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(wintypes.UINT), wintypes.UINT]
_u32.GetRawInputData.restype = wintypes.UINT
_u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_u32.GetMessageW.restype = wintypes.BOOL
_u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u32.DestroyWindow.argtypes = [wintypes.HWND]
_u32.PostQuitMessage.argtypes = [ctypes.c_int]
_u32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_u32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_u32.DispatchMessageW.restype = LRESULT
_k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_k32.GetModuleHandleW.restype = wintypes.HMODULE

_DINLE = WM_APP + 1          # wParam: 1 = dinlemeye basla, 0 = birak


class FareDinleyici:
    """geri_cagri(dugme, basili): orta/yan tus basilinca ve birakilinca, kendi is parcaciginda cagrilir."""

    def __init__(self, geri_cagri):
        self._geri_cagri = geri_cagri
        self._hwnd = None
        self._hazir = threading.Event()
        self._basili: set[str] = set()
        threading.Thread(target=self._calis, daemon=True, name="fare").start()
        self._hazir.wait(3)

    # ── disaridan ────────────────────────────────────────────────────────────
    def dinle(self, acik: bool):
        """Sadece fare tusu atanmisken ya da tus atanirken acik tutulur."""
        if self._hwnd:
            _u32.PostMessageW(self._hwnd, _DINLE, 1 if acik else 0, 0)

    def kapat(self):
        if self._hwnd:
            _u32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    # ── is parcacigi ─────────────────────────────────────────────────────────
    def _calis(self):
        try:
            self._wndproc = WNDPROC(self._pencere_islevi)      # referans tutulmazsa cop toplanir ve cokulur
            hinst = _k32.GetModuleHandleW(None)
            sinif = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self._wndproc,
                                hInstance=hinst, lpszClassName="CanYouSpeakFare")
            _u32.RegisterClassExW(ctypes.byref(sinif))
            self._hwnd = _u32.CreateWindowExW(0, "CanYouSpeakFare", None, 0, 0, 0, 0, 0,
                                              HWND_MESSAGE, None, hinst, None)
        except Exception:  # noqa: BLE001
            logging.exception("fare penceresi")
        finally:
            self._hazir.set()
        if not self._hwnd:
            logging.error("fare dinleyici acilamadi: %s", ctypes.get_last_error())
            return
        mesaj = wintypes.MSG()
        while _u32.GetMessageW(ctypes.byref(mesaj), None, 0, 0) > 0:
            _u32.TranslateMessage(ctypes.byref(mesaj))
            _u32.DispatchMessageW(ctypes.byref(mesaj))

    def _kaydet(self, acik: bool):
        aygit = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK if acik else RIDEV_REMOVE, self._hwnd if acik else None)
        if not _u32.RegisterRawInputDevices(ctypes.byref(aygit), 1, ctypes.sizeof(RAWINPUTDEVICE)):
            logging.error("raw input kaydi (%s) basarisiz: %s", acik, ctypes.get_last_error())
        if not acik:
            for dugme in list(self._basili):                    # basili kalan tusu birakilmis say
                self._bildir(dugme, False)

    def _bildir(self, dugme: str, basili: bool):
        if basili == (dugme in self._basili):
            return
        (self._basili.add if basili else self._basili.discard)(dugme)
        try:
            self._geri_cagri(dugme, basili)
        except Exception:  # noqa: BLE001
            logging.exception("fare geri cagri")

    def _pencere_islevi(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_INPUT:
                veri = RAWINPUT()
                boyut = wintypes.UINT(ctypes.sizeof(veri))
                if _u32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(veri), ctypes.byref(boyut),
                                        ctypes.sizeof(RAWINPUTHEADER)) != 0xFFFFFFFF \
                        and veri.header.dwType == RIM_TYPEMOUSE:
                    bayrak = veri.mouse.usButtonFlags
                    if bayrak:                                   # hareket olaylarinda 0: hemen gec
                        for bit, (dugme, basili) in _GECIS.items():
                            if bayrak & bit:
                                self._bildir(dugme, basili)
            elif msg == _DINLE:
                self._kaydet(bool(wparam))
                return 0
            elif msg == WM_CLOSE:
                self._kaydet(False)
                _u32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                _u32.PostQuitMessage(0)
                return 0
        except Exception:  # noqa: BLE001
            logging.exception("fare mesaji")
        return _u32.DefWindowProcW(hwnd, msg, wparam, lparam)
