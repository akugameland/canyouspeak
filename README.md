# CanYouSpeak

Discord'da (ve oyunlarda) yabancılarla konuşurken **canlı altyazı çevirmeni**. Tamamen bilgisayarınızda çalışır: internet, hesap, API anahtarı, kota ya da ücret yok.

- Karşı taraf hangi dilde konuşursa konuşsun, söylediğinin **Türkçesi** ekranın altında film altyazısı gibi çıkar. Konuşulan dil küçük bir etiketle yazar.
- Bas-konuş tuşunu (klavye tuşu ya da farenin orta/yan tuşu) basılı tutup Türkçe konuşursunuz. **Söylemeniz gereken cümle** karşı tarafın dilinde altyazıda belirir ve bir sonraki basışa kadar kalır.
- Uygulama **hiç ses çıkarmaz ve kimsenin yerine konuşmaz.** Sadece ekranda gösterir.
- Altyazı her zaman en öndedir, fare tıklamalarını geçirir, oyunun odağını almaz. Renk, boyut, yazı tipi, saydamlık ve arka plan kutusu ayarlanabilir.

## Gizlilik

- Ses ve metin **bilgisayarınızdan çıkmaz**. Uygulama çalışırken internete bağlanmaz.
- Tek internet kullanımı: kurulumda modellerin bir kez indirilmesi (Hugging Face, sabit sürüm). Bir de ekran kartı hata verirse yedek işlemci modelinin bir kez indirilmesi.
- Klavye yalnızca seçtiğiniz bas-konuş tuşu için dinlenir. Tuş basışları hiçbir yere kaydedilmez.
- Ayarlar (`ayarlar.json`) ve hata kaydı (`hata.log`) sadece yerelde durur, depoya eklenmez.

## Gereksinimler

- Windows 10/11, Python 3.12 (test edilen sürüm: [Python 3.12.10](https://www.python.org/downloads/release/python-31210/))
- Önerilen: NVIDIA ekran kartı (4 GB yeter). Yoksa işlemcide daha yavaş çalışır.
- Disk: ~3 GB model + ~2 GB Python paketleri

## Kurulum

1. Depoyu indirin.
2. `KURULUM.bat` dosyasını çalıştırın. Python ortamını kurar ve modelleri indirir. Bilgisayarda Python 3.12 yoksa onu da kendisi kurar (winget ile, yönetici izni gerekmez).
3. `BASLAT.bat` ile açın.

Python otomatik kurulamazsa elle kurun:

1. [Python 3.12.10](https://www.python.org/downloads/release/python-31210/) sayfasındaki "Files" tablosundan **Windows installer (64-bit)** dosyasını indirin. 3.12'nin daha yeni sürümlerinde (3.12.11 ve sonrası) Windows kurulum dosyası yoktur.
2. Kurulumun ilk ekranında **"Add python.exe to PATH"** kutusunu işaretleyin.
3. `KURULUM.bat` dosyasını yeniden çalıştırın.

Ayrıntılı kullanım ve sorun çözme: [OKU_BENI.txt](OKU_BENI.txt)

## Nasıl çalışır

| Parça | Ne yapar |
|---|---|
| WASAPI loopback | Kulaklığa giden sesi (Discord) dinler |
| [Whisper large-v3-turbo](https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo) (faster-whisper / CTranslate2) | Konuşmayı yazıya döker, dili algılar |
| [NLLB-200 1.3B](https://huggingface.co/OpenNMT/nllb-200-distilled-1.3B-ct2-int8) | 200 dil arasında çevirir |
| `kisa_sozluk.py` | Kısa sözler (merhaba, evet, tamam…) için 17 dilde hazır karşılıklar |
| Raw Input | Fare tuşunu oyunda gecikme yaratmadan dinler |

## Lisanslar

Bu depodaki kod: [MIT](LICENSE).

Modeller bu depoda **bulunmaz**; kurulumda kendi kaynaklarından indirilir ve kendi lisanslarına tabidir:

- Whisper large-v3-turbo: MIT
- NLLB-200: **CC-BY-NC-4.0 (yalnızca ticari olmayan kullanım)**
- Kullanılan Python paketleri kendi lisanslarına tabidir (`requirements.txt`).
