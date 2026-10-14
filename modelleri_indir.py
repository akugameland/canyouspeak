"""Modelleri modeller/ klasorune indirir (~3 GB, bir kez).

Guvenlik: her model belirli bir surume (commit) sabitlenmistir. Depo sahibi ileride dosyalari
degistirse bile burada test edilmis surum iner. Indirilen dosyalar sadece model agirliklari ve
sozluk (json) dosyalaridir; calistirilabilir kod icermez.
"""
import os
import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent / "modeller"
os.environ.setdefault("HF_HOME", str(KLASOR / ".hf"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from huggingface_hub import snapshot_download  # noqa: E402

MODELLER = [
    # (depo, sabit surum, hedef klasor, lisans)
    ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf", "whisper-turbo", "MIT"),
    ("OpenNMT/nllb-200-distilled-1.3B-ct2-int8", "70f572adafa4794890ce7826156a4209717855af", "nllb-1.3b",
     "CC-BY-NC-4.0 (yalnizca ticari olmayan kullanim)"),
]
IZINLI = ["*.json", "*.bin", "*.txt", "*.model", "README.md"]   # .py/.exe gibi calistirilabilir dosya inmesin


def main():
    for depo, surum, hedef, lisans in MODELLER:
        print(f"İndiriliyor: {depo} ({lisans})")
        snapshot_download(depo, revision=surum, local_dir=KLASOR / hedef, allow_patterns=IZINLI)
    print("Tamam. Modeller:", KLASOR)


if __name__ == "__main__":
    sys.exit(main())
