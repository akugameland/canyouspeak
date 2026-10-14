"""Ayarlar: ayarlar.json okunur/yazilir."""
import json
from pathlib import Path

KLASOR = Path(__file__).resolve().parent
DOSYA = KLASOR / "ayarlar.json"

VARSAYILAN = {
    "hedef_dil": "Otomatik",        # sizin konusmanizin cevrilecegi dil
    "ptt_tusu": "f8",               # basili tutup Turkce konusun; ceviri altyazida bir sonraki basisa kadar kalir
    "gelen_acik": True,             # karsi tarafi Turkceye cevir
    "altyazi_acik": True,           # ekranin altinda, her zaman en onde altyazi
    "altyazi_stil": {},             # renk, boyut, saydamlik vb. (bos: altyazi.VARSAYILAN_STIL)
    "hep_ustte": False,             # ana pencere (gecmis) en onde mi
    "esik": 300,                    # bu seviyenin altindaki ses (sessizlik/ugultu) konusma sayilmaz
    "dinlenen_aygit": "",           # bos: varsayilan hoparlor/kulaklik
    "mikrofon": "",                 # bos: varsayilan mikrofon
    "cihaz": "otomatik",            # "cpu": konusma tanima ekran kartini hic kullanmasin (agir oyunlarda)
}


def yukle() -> dict:
    ayar = dict(VARSAYILAN)
    try:
        ayar.update(json.loads(DOSYA.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    except Exception:  # bozuk dosya: varsayilanlarla devam
        pass
    ayar.pop("gemini_api_key", None)                 # eski surumden kalan anahtar dosyada tutulmasin
    return ayar


def kaydet(ayar: dict) -> None:
    DOSYA.write_text(json.dumps(ayar, ensure_ascii=False, indent=2), encoding="utf-8")
