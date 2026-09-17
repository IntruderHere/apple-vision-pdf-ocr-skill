---
name: apple-vision-pdf-ocr
display-name: Apple Vision PDF OCR
description: OCR сканов PDF и картинок через Apple Vision на macOS.
  Использовать, когда нужно извлечь текст из PDF/изображений без текстового
  слоя.
---

# Apple Vision OCR для PDF и картинок (macOS)

Доступно только на macOS (`platform.system() == 'Darwin'`). В python нужен pyobjc
(`Vision`, `Quartz`, `Foundation`, `objc`) — на системном Python 3, например
`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`.
В изолированном sandbox-окружении (run_python) pyobjc обычно **нет** —
выполняйте скрипты через `shell_command` с системным `python3`.

## Стратегия

1. **Сначала текстуровый слой** через PyMuPDF (`fitz`): `page.get_text('text')`.
   Страница считается «сканом», если `len(text.strip()) < 40` — только такие
   страницы (или всё изображение целиком) отправлять в Vision.
2. **Рендер страницы** в CGImage при ~150 dpi:
   - основной путь: Quartz — `CGPDFDocumentCreateWithURL` →
     `CGPDFDocumentGetPage` (1-based!) → `CGBitmapContextCreate` +
     `CGContextDrawPDFPage` → `CGBitmapContextCreateImage`;
   - **fallback** (редко, ~1-2% PDF): Quartz не читает страницу
     (`CGPDFDocumentGetPage` вернул None / «cannot read page») — рендерим её
     PyMuPDF `page.get_pixmap(dpi=150, alpha=False)` → сохраняем PNG →
     `CGImageSourceCreateWithURL` → `CGImageSourceCreateImageAtIndex(src, 0, None)`.
3. **OCR**: `Vision.VNRecognizeTextRequest`,
   `setRecognitionLanguages_(["ru-RU", "en-US"])`,
   уровень `VNRequestTextRecognitionLevelAccurate`,
   `setUsesLanguageCorrection_(True)`,
   `VNImageRequestHandler(initWithCGImage_options_:(img, None))`,
   `performRequests_error_([req], None)`. Текст из `obs.topCandidates_(1)[0].string()`.
4. Картинки (jpg/png/tif): PIL → RGB → PNG → `CGImageSourceCreateWithURL` → тот же Vision.

Готовый скрипт в этой папке: **`vision_ocr.py`** — принимает PDF/PNG/JPG/TIFF,
сначала пробует текстуровый слой (PDF), сканы и картинки распознаёт Vision.
Порядок строк: Vision возвращает блоки без порядка — для читаемого текста
отсортируйте по bbox (y сверху вниз, потом x) либо просто берите `results()`
как есть, если порядок не важен.

## Подводные камни pyobjc (важно!)

- `NSAutoreleasePool` в pyobjc — **НЕ context manager**: создавать
  `NSAutoreleasePool.alloc().init()` и вызывать `.drain()` вручную
  (можно оборачивать в `contextmanager`, но drain всегда в `finally`).
  При потоках — пул на поток (`threading.local`), ротировать пул каждые ~50
  запросов Vision, чтобы память не росла.
- **Никогда** не вызывайте ручные release (`CFRelease`, `CGContextRelease`,
  `CGPDFDocumentClose`…) — в этой версии pyobjc `CGPDFDocumentClose` даже нет,
  а ручной release результата `CGBitmapContextCreateImage` приводит к
  двойному освобождению и **SIGSEGV**. Владелец объектов — python-обёртки +
  autorelease-пулы.
- `CGPDFDocumentGetPage(doc, n)` — **1-based** индекс страницы.
- `CGContextScaleCTM(ctx, scale, scale)` перед `CGContextDrawPDFPage`; фон —
  белый `CGContextSetRGBFillColor(ctx,1,1,1,1)` + `CGContextFillRect`.
- URL для Quartz: `CFURLCreateWithFileSystemPath(None, abs_path, kCFURLPOSIXPathStyle, False)`
  (или `Foundation.NSURL.fileURLWithPath_`).

## Производительность и артефакты

- ~2.4 страницы/сек при 6 потоках; память стабилизируется ~700-800 МБ с
  ротируемыми пулами. Для десятков-сотен страниц берите ThreadPoolExecutor
  и пул на поток.
- Vision читает «№» как `Nº`/`No`/`Ne` — нормализуйте:
  `re.sub(r'(?<![A-Za-zА-Яа-яЁё])N\s*[ºoоO0](?![а-яёa-zА-ЯЁё])', '№ ', s)`.
- Буквы в словах иногда «опадают» («Дефектная» → «Дефекная»), номера дел
  и дат бывают разорваны переносами строк — при парсинге реквизитов
  допускайте пробелы и символы `[-–/]` внутри номеров.
- Российские даты часто в форме «30 июня 2021 г.» — ищите месяцы словами.
- Плотные таблички/сметы: Accurate уровень медленно, но надёжнее Fast;
  для огромных объёмов можно Fast, если допустимы ошибки.

## Быстрый старт

```bash
python3 /path/to/this/skill/vision_ocr.py "scan.pdf" photo.jpg > text.txt
```

или импортировать функции из `vision_ocr.py`:
`ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`.
