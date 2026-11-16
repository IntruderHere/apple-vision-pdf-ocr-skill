---
name: apple-vision-pdf-ocr
display-name: Apple Vision PDF OCR
description: OCR сканов PDF и картинок через Apple Vision на macOS.
  Использовать, когда нужно извлечь текст из PDF/изображений без текстового
  слоя.
version: "1.1"
author: ivan
license: MIT
tags: [ocr, pdf, images, vision, quartz, pyobjc]
related_skills: []
---

# Apple Vision OCR для PDF и картинок (macOS)

## When to Use

- PDF-файлы без текстового слоя (сканы, фотографии документов) — нужно извлечь текст.
- Отдельные изображения (PNG, JPG, TIFF) — нужен OCR русского/английского текста.
- Документы с табличками/сметами/датами словами — Accurate уровень Vision лучше Fast.
- **Не использовать** для PDF с уже присутствующим текстовым слоем — PyMuPDF вытянет его мгновенно; OCR-скрипт сам распознаёт и пропустит такие страницы.

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
как есть, если порядок не важен. Для строки ТАБЛИЦЫ (клетки одной строки,
слева→направо) `vision_page()`/`vision_ocr_lines()` не подходят — координаты
не возвращают; используйте **`scripts/vision_table_row.py`**: метка строки →
y-полоса ±band → сортировка блоков по x (собственный проход Vision с bbox).

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
- Собственный рендер (не через `_vision_page`):
  `CGBitmapContextCreate(None, w, h, 8, 0, CGColorSpaceCreateDeviceRGB(),
  kCGImageAlphaPremultipliedLast)` — `bytesPerRow=0` и явный colorspace
  обязательны; иначе контекст 0×0 и Vision отклоняет «zero-dimensioned image
  (0 x 0)». CGRect — `CGContextMake(0,0,w,h)` или вложенный кортеж
  `((x,y),(w,h))`; «плоский» `(x,y,w,h)` pyobjc не примет (ValueError при
  депипонизации).
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

## Высоко-резкое повторное OCR (неразборчивые места)

Если отдельная строка распознана мусором — формула схлопнулась в
`= 7` / `= =`, слово выросло до абсурда («пошех»), номер/реквизит
искажён, верхний/нижний индекс потерян — не доверяйте одному проходу 150 dpi:
1. `vision_page(path, idx, dpi=300)` — пере-OCR всей страницы (300 dpi ≈ 4x
   пикселей, заметно медленнее);
2. всё ещё неясно — `crop_ocr(path, idx, needle, det_dpi=200, dpi=800)`:
   двухэтапно — строки с `needle` находит Vision на низком `det_dpi` (быстро),
   затем вырезанную полоску берёт из рендера в `dpi` (800+) и OCR-ит только
   кроп. **Никогда не гоняйте Vision по полной странице на 500+ dpi** —
   это в разы медленнее (минуты на страницу); bbox линейно масштабируется,
   поэтому детекция на 200 dpi + кроп с 800 dpi дают тот же результат.

Верхние индексы — слабое место: номера сносок читаются как §/И/3, дроби в
формулах (t/T) схлопываются в «7» или «=». Формулы и реквизиты (номера
приказов, даты, инициалы) всегда верифицируйте через `crop_ocr`.

## Реквизиты шапки формы (КС-2, КС-3, акты, СЗ-бланки)

Нужны не «весь текст», а конкретные клетки: номер/дата договора, № акта,
«Дата составления», «Отчетный период», «Сметная стоимость».

1. Скан-формы (КС-2/КС-3) обычно без текстового слоя — сразу Vision, не тратя
   проход на `get_text()`. Предупреждения `Unexpected EOF in JBIG2 stream`
   при рендере — шум декодера, страница читается нормально.
2. `vision_table_row.py --label "Дата составления"` находит строку только при
   точном совпадении с распознанным текстом: Vision стабильно портит
   подписи («Дата составпения», «Сметкая стоимость»), и метка не находится.
   Не перебирайте варианты — читайте координаты напрямую:

```python
import sys
sys.path.insert(0, '/path/to/this/skill')
sys.path.insert(0, '/path/to/this/skill/scripts')
import vision_table_row as vt
img = vt.render_page('ks2.pdf', 0, 250)      # 250 dpi хватает для шапки
blocks = vt.ocr_bboxes(img)                  # bbox: origin СНИЗУ-слева, 0..1
for b in sorted(blocks, key=lambda b: -b['y_center']):
    if 0.73 < b['y_center'] < 0.81 and b['x0'] > 0.30:
        print(f"y={b['y_center']:.3f} x={b['x0']:.3f} :: {b['text']}")
```

3. `y_center` — нормированная координата от НИЗА страницы: шапка бланка
   лежит в верхних 20–30 %, то есть y ≈ 0.7–0.85, а не 0.15–0.30. Значение
   поля — блок с тем же `y_center` (±0.005) и `x0` правее подписи; подписи
   и значения часто распознаются с разным `x0`, поэтому фильтруйте по
   полосе y, а не по номеру строки.
4. Значения читайте как есть: «1179_25-рдог-МР78» (подчёркивание вместо
   слэша), «27.03.2026». Номер акта в клетке «Номер документа» может выйти
   мусором («HOMED») — тогда в отчёт берите дату и объект, а номер акта не
   выдумывайте.
5. **Штамп исходящей даты/номера (ЭП, «08.10.2026 № КС/47757/26») OCR не
   берёт вообще** — это оттиск подписи, отрисованный как appearance виджета
   (`/Annots` → `/Widget` → `/AP` → `/N`), а не текст страницы: его нет ни в
   текстовом слое, ни в рендере на 300–500 dpi, ни в кропе. Проверяйте наличие
   штампа через `pypdf`: `[a.get_object().get('/Subtype') for a in page['/Annots']]`
   и поля `/Widget` с `/T` наподобие `Reg_...`. Не подставляйте вместо даты
   `/CreationDate` (это время записи файла, а не дата письма) и не пишите
   пользователю «даты нет» — попросите скриншот шапки: человек видит оттиск
   в просмотрщике.

## Верификация распознанных цифр

Дешевле crop_ocr — арифметика самой строки: в строках итогов
«без налога + сумма налога = итого с налогом», в строках позиций
«цена × количество = стоимость». Если тройки сходятся во всех документах —
цифры прочитаны верно, повторный кроп не нужен; только при несходжении —
`crop_ocr`. При банд-чтении строки (`vision_table_row.py`) в полосу попадают
и клетки соседних строк (например, последняя позиция над итоговой) —
разбирать по арифметически сходящимся группам, не по порядку.

## Самопроверка после правок скриптов

Правили `vision_ocr.py` / `scripts/vision_table_row.py` — проверяйте на синтетическом
«скане», а не на документах пользователя:

```bash
python3 /path/to/this/skill/scripts/make_test_scan.py /tmp/ocrtest
python3 /path/to/this/skill/vision_ocr.py /tmp/ocrtest/test_scan.pdf
python3 /path/to/this/skill/scripts/vision_table_row.py \
        /tmp/ocrtest/test_scan.pdf --page 0 --label "Всего к оплате"
```

Ожидаемо: `Всего к оплате | 6200,00 | 1 033,33 | 7 233,33` (Vision теряет пробел
в первой сумме — норма), `crop_ocr(..., 'нет такой строки')` → `[]`, а `test_text.pdf`
читается с текстового слоя без вызова Vision. Два файла из генератора различаются
именно наличием текстового слоя — на них проверяются обе ветки (`get_text()` и Vision).

Гоняйте скрипты из ТОЙ папки, где лежит итоговая версия: после синхронизации —
из клона репозитория. `scripts/vision_table_row.py` сам добавляет родительскую
папку в `sys.path`, и битый layout (`vision_ocr.py` не рядом со `scripts/`)
всплывает только при запуске из опубликованного дерева.

## Быстрый старт

```bash
python3 /path/to/this/skill/vision_ocr.py "scan.pdf" photo.jpg > text.txt
```

или импортировать функции из `vision_ocr.py`:
`ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`,
`crop_ocr(path, page_index, needle, det_dpi=200, dpi=800)`.

Строка таблицы по метке (клетки слева→направо):
`python3 /path/to/this/skill/scripts/vision_table_row.py scan.pdf --page 1 --label "Всего к оплате"`
(если метка не находится — см. «Реквизиты шапки формы», читайте bbox напрямую)

УПД (куда смотреть ключевые поля и сумму, формат отчёта) — `references/upd.md`.
