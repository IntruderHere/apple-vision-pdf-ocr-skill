# Apple Vision PDF OCR — a skill for agents (macOS only)

A skill that teaches an AI agent to extract text from scanned PDFs and images with Apple Vision, plus a
standalone script (`vision_ocr.py`) you can call directly. It works with any agent that can read `SKILL.md`
and run shell commands; the only hard requirement is macOS.

🇬🇧 [English](#english) · 🇷🇺 [Русский](#русский)

---

## English

### What it does

`vision_ocr.py` reads a PDF's own text layer only when that layer is genuinely readable — visible text that
covers a real part of the page. A scan carrying an invisible EDMS stamp ("generated in system X", white on
white, `opacity 0`, render mode 3) is OCR'd instead of being skipped, so the content is never silently lost.
Scanned pages are rendered to a CGImage (~150 dpi) and read with Apple Vision (`ru-RU` + `en-US`); raster
images go straight to Vision. Output is in reading order: one visual line per row, cells of a table row
joined by a tab.

### Features

- **Page detection** — a page is OCR'd when its *visible* text layer has fewer than 40 characters, or covers
  under 1 % of a page that carries images. `--force-ocr` overrides the check.
- **Images** — PNG/JPG/TIFF/HEIC via ImageIO; PIL only as a fallback for exotic formats.
- **Reading order** — blocks are grouped into visual lines by bbox overlap, sorted top→bottom, cells joined
  with a tab; text-layer pages go through the same path. `--raw` keeps Vision's own order for debugging.
- **Sideways pages** — a photo rotated by 90° is detected from block geometry and turned upright before OCR.
- **High-res re-OCR** — `crop_ocr()` finds a line at 300 dpi (auto-retry at 450 when the needle is missed),
  then re-reads only that strip from an 800-dpi region render; `row=True` takes the whole visual line.
  Matching ignores case, ё/е and lost spaces inside numbers.
- **Table rows** — `scripts/vision_table_row.py` prints the cells of one table row left to right; `--json`
  for machine use.
- **CLI** — `--pages 1-5,9`, `--force-ocr`, `--json` (per-page text, or blocks with bboxes and confidence),
  `--raw`, `--workers`, `--dpi`. One bad file no longer aborts a batch, and files are dispatched by content,
  not by extension.
- **Self-test** — `scripts/selftest.py` generates its own fixtures (text PDF, scan, invisible-stamp scan,
  dense 9 pt table, sideways page, 12-page scan) and asserts 34 checks; no real documents needed.

### Requirements

- macOS (Apple Vision is a system framework; nothing else can run it)
- System Python 3 with the pyobjc frameworks `Vision` and `Quartz`
- PyMuPDF; Pillow only as a fallback for unusual image formats

```bash
pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz PyMuPDF Pillow
```

> In a sandboxed Python (for example an agent's in-process sandbox) pyobjc is usually unavailable — run the
> scripts through a real shell with the system `python3`.

### Installation

The skill is a folder containing `SKILL.md`; the folder name is the skill name.

```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git apple-vision-pdf-ocr
```

Then put that folder where your agent looks for skills — the layout is the same everywhere, only the parent
directory differs (user-level or project-level, per agent):

```bash
~/.hermes/skills/media/apple-vision-pdf-ocr        # Hermes Agent, user-level
<project>/.agents/skills/apple-vision-pdf-ocr      # project-level convention
```

An agent that has no skill folders at all can simply be pointed at `SKILL.md` and `vision_ocr.py`: the
knowledge lives in the markdown, the work is done by the script.

### Usage

```bash
python3 vision_ocr.py scan.pdf photo.jpg > text.txt
python3 vision_ocr.py big.pdf --pages 1-5,9 --json > blocks.json
python3 vision_ocr.py scan.pdf --force-ocr --workers 6
```

Or import the functions:

```python
import vision_ocr
text = vision_ocr.ocr_pdf("scan.pdf")                 # whole document
pages = vision_ocr.ocr_pdf_pages("scan.pdf")          # (page_no, kind, payload) per page
blocks = vision_ocr.vision_blocks(cgimage)            # text, confidence, x, y, w, h (0..1, bottom-left)
lines = vision_ocr.reading_order(blocks)              # tab-joined visual lines
hits = vision_ocr.crop_ocr("scan.pdf", 0, "Итого", row=True)   # re-read one line at high resolution
```

Output: text to stdout in reading order — tab-separated cells, `--- page N ---` markers, and
`[OCR ERROR ...]` for pages Vision could not read. `--json` returns either `{"page": N, "text": ...}` or
`{"page": N, "blocks": [...]}`, and `{"page": N, "error": ...}` when a page failed.

Read one table row left to right (`--page` is 0-based, as everywhere in this skill):

```bash
python3 scripts/vision_table_row.py invoice.pdf --page 0 --label "Всего к оплате"
# → Всего к оплате | 6 200,00 | 1 033,33 | 7 233,33
python3 scripts/vision_table_row.py invoice.pdf --page 0 --label "Всего к оплате" --json
```

Re-read a garbled line at high resolution:

```python
import vision_ocr
for matched, lines in vision_ocr.crop_ocr("act.pdf", 0, "Итого", row=True, dpi=800):
    print(matched, "→", lines)
```

### Self-test

```bash
python3 scripts/selftest.py         # 34 checks, ~10–15 s
python3 scripts/selftest.py --keep  # keep the generated fixtures and print their path
```

### Files

| File | Description |
|---|---|
| `SKILL.md` | The skill itself: strategy, pyobjc pitfalls, reading order, form-header playbook, verification |
| `vision_ocr.py` | CLI + library (`ocr_pdf`, `ocr_pdf_pages`, `vision_blocks`, `reading_order`, `crop_ocr`, `pdf_page_cgimage`, `pdf_region_cgimage`) |
| `scripts/vision_table_row.py` | One table row by label: `render_page`, `ocr_bboxes`, `--json` |
| `scripts/make_test_scan.py` | Writes the three base fixtures (text PDF, PNG, scan PDF) |
| `scripts/selftest.py` | Full self-test on generated fixtures |
| `references/upd.md` | Universal transfer document (УПД): key fields, totals line, how to verify sums |

### Known limits

- A scan rotated by 180° is read correctly, but line order comes out reversed — rotate it upright beforehand.
- On dense tables Vision occasionally drops a single small cell; verify totals arithmetically.
- A dense A4 page costs ~0.5 s (Vision dominates, the render is ~0.15 s), so four threads buy only a few
  percent; ~2.5 pages/s is a realistic figure.
- `crop_ocr` holds ~25–30 MB RSS per call (Vision keeps the image of each request): for hundreds of crops run
  per document or per page range (`--pages`) instead of one giant batch.

---

## Русский

### Что делает

`vision_ocr.py` читает собственный текстовый слой PDF только если тот действительно читаем — это видимый
текст, занимающий реальную часть страницы. Скан с невидимой печатью ЭДО («сформировано в системе …», белым
по белому, `opacity 0`, render mode 3) уходит в OCR, а не пропускается, поэтому содержимое не теряется
молча. Страницы-сканы рендерятся в CGImage (~150 dpi) и распознаются Apple Vision (`ru-RU` + `en-US`);
растровые картинки отправляются в Vision напрямую. Вывод — в порядке чтения: одна визуальная строка на
строку, клетки строки таблицы склеены табом.

### Возможности

- **Детект страницы** — страница уходит в OCR, если её *видимый* текстовый слой короче 40 символов или
  занимает меньше 1 % площади страницы с картинками. `--force-ocr` отключает проверку.
- **Картинки** — PNG/JPG/TIFF/HEIC через ImageIO; PIL только как fallback для экзотических форматов.
- **Порядок чтения** — блоки собираются в визуальные строки по перекрытию bbox, сортируются сверху вниз,
  клетки склеиваются табом; страницы с текстовым слоем идут тем же путём. `--raw` оставляет порядок Vision
  для отладки.
- **Страница «на боку»** — фото, повёрнутое на 90°, определяется по геометрии блоков и разворачивается
  перед OCR.
- **Высоко-резкое повторное OCR** — `crop_ocr()` находит строку на 300 dpi (авторетрай 450, если метка не
  нашлась), затем перечитывает только её полосу из региона-рендера 800 dpi; `row=True` берёт всю визуальную
  строку. Сравнение нечувствительно к регистру, ё/е и потерянным пробелам внутри чисел.
- **Строки таблиц** — `scripts/vision_table_row.py` печатает клетки одной строки слева→направо; `--json`
  для машинной обработки.
- **CLI** — `--pages 1-5,9`, `--force-ocr`, `--json` (текст по страницам либо блоки с bbox и confidence),
  `--raw`, `--workers`, `--dpi`. Битый файл больше не обрывает пакет, а тип файла определяется по
  содержимому, а не по расширению.
- **Самопроверка** — `scripts/selftest.py` сам строит образцы (текстовый PDF, скан, скан с невидимой
  печатью, плотная таблица 9 pt, «боковая» страница, 12-страничный скан) и проверяет 34 утверждения;
  реальные документы не нужны.

### Требования

- macOS (Apple Vision — системный фреймворк, вне macOS работать не будет)
- Системный Python 3 с pyobjc-фреймворками `Vision` и `Quartz`
- PyMuPDF; Pillow — только как fallback для редких форматов картинок

```bash
pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz PyMuPDF Pillow
```

> В песочнице Python (например, внутрипроцессный sandbox агента) pyobjc обычно нет — запускайте скрипты
> через настоящий shell с системным `python3`.

### Установка

Скилл — это папка с `SKILL.md`; имя папки = имя скилла.

```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git apple-vision-pdf-ocr
```

Дальше папку кладут туда, где ваш агент ищет скиллы — раскладка везде одна, различается только родительский
каталог (пользовательский или проектный, по правилам конкретного агента):

```bash
~/.hermes/skills/media/apple-vision-pdf-ocr        # Hermes Agent, пользовательский уровень
<project>/.agents/skills/apple-vision-pdf-ocr      # проектная конвенция
```

Агенту, который вообще не умеет папки скиллов, достаточно указать на `SKILL.md` и `vision_ocr.py`:
знание живёт в markdown, работу делает скрипт.

### Использование

```bash
python3 vision_ocr.py scan.pdf photo.jpg > text.txt
python3 vision_ocr.py big.pdf --pages 1-5,9 --json > blocks.json
python3 vision_ocr.py scan.pdf --force-ocr --workers 6
```

Или импортировать функции:

```python
import vision_ocr
text = vision_ocr.ocr_pdf("scan.pdf")                 # весь документ
pages = vision_ocr.ocr_pdf_pages("scan.pdf")          # (page_no, kind, payload) по страницам
blocks = vision_ocr.vision_blocks(cgimage)            # text, confidence, x, y, w, h (0..1, от низа)
lines = vision_ocr.reading_order(blocks)              # визуальные строки, склеенные табом
hits = vision_ocr.crop_ocr("scan.pdf", 0, "Итого", row=True)   # перечитать строку в высоком разрешении
```

Вывод: текст в stdout в порядке чтения — клетки через таб, маркеры `--- page N ---`, `[OCR ERROR ...]` для
страниц, которые Vision не прочитал. `--json` отдаёт либо `{"page": N, "text": ...}`, либо
`{"page": N, "blocks": [...]}`, а при сбое страницы — `{"page": N, "error": ...}`.

Чтение одной строки таблицы слева→направо (`--page` 0-based, как и везде в скилле):

```bash
python3 scripts/vision_table_row.py счёт.pdf --page 0 --label "Всего к оплате"
# → Всего к оплате | 6 200,00 | 1 033,33 | 7 233,33
python3 scripts/vision_table_row.py счёт.pdf --page 0 --label "Всего к оплате" --json
```

Перечитать неразборчивую строку в высоком разрешении:

```python
import vision_ocr
for matched, lines in vision_ocr.crop_ocr("акт.pdf", 0, "Итого", row=True, dpi=800):
    print(matched, "→", lines)
```

### Самопроверка

```bash
python3 scripts/selftest.py         # 34 проверки, ~10–15 с
python3 scripts/selftest.py --keep  # оставить сгенерированные образцы и напечатать путь
```

### Файлы

| Файл | Описание |
|---|---|
| `SKILL.md` | Сам скилл: стратегия, подводные камни pyobjc, порядок чтения, шапка бланков, верификация |
| `vision_ocr.py` | CLI + библиотека (`ocr_pdf`, `ocr_pdf_pages`, `vision_blocks`, `reading_order`, `crop_ocr`, `pdf_page_cgimage`, `pdf_region_cgimage`) |
| `scripts/vision_table_row.py` | Одна строка таблицы по метке: `render_page`, `ocr_bboxes`, `--json` |
| `scripts/make_test_scan.py` | Пишет три базовых образца (текстовый PDF, PNG, PDF-скан) |
| `scripts/selftest.py` | Полная самопроверка на сгенерированных образцах |
| `references/upd.md` | УПД: ключевые поля, строка итогов, как проверять суммы |

### Известные ограничения

- Скан, перевёрнутый на 180°, читается верно, но порядок строк выходит обратным — разверните файл заранее.
- На плотных таблицах Vision иногда теряет одиночную мелкую клетку; итоги проверяйте арифметикой.
- Плотная страница A4 стоит ~0.5 с (доминирует вызов Vision, рендер ~0.15 с), поэтому четыре потока дают
  лишь единицы процентов; реалистичная цифра — ~2.5 страницы/с.
- `crop_ocr` держит ~25–30 МБ RSS на вызов (Vision удерживает изображение каждого запроса): сотни кропов
  гоняйте по документам или диапазонам страниц (`--pages`), а не одним пакетом.

---

## License / Лицензия

MIT — use as-is. / Использовать как есть.
