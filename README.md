# Apple Vision PDF OCR — LM Studio Bionic Skill (macOS)

A skill that teaches the agent to extract text from scanned PDFs and images using Apple Vision on macOS.

🇬🇧 [English](#english) · 🇷🇺 [Русский](#русский)

---

## English

### What it does

The skill reads the PyMuPDF text layer first; pages that turn out to be scans (fewer than 40 characters of text) are rendered to a CGImage at ~150 dpi and OCR'd with Apple Vision (ru-RU + en-US). Raster images are sent to Vision directly.

### Features

- **PDF:** pages with a text layer are read directly; "scans" (pages with < 40 chars) are rendered to CGImage (~150 dpi) and OCR'd with Vision, with a PyMuPDF render fallback for rare broken PDFs.
- **Images:** PNG/JPG/TIFF are OCR'd directly via Vision.
- **Performance:** parallel page processing (ThreadPoolExecutor) with rotating autorelease pools — stable memory (~700–800 MB), ~2.4 pages/s on 6 threads.
- **High-res re-OCR:** `crop_ocr()` runs Vision over the full page at a low dpi to find the line, then at 800+ dpi over that strip only — fixes garbled formulas, superscripts and requisites without the cost of a full-page high-dpi pass.
- **Table rows in reading order:** `scripts/vision_table_row.py` returns the cells of one table row left to right (label → y-band → sort by x), with per-block bounding boxes available for anything else.
- **Self-check:** `scripts/make_test_scan.py` builds a synthetic sample (a PDF with a real text layer, the same page as a PNG, and an image-only PDF) so OCR changes are verified without touching real documents.
- **Knowledge base:** `SKILL.md` documents pyobjc pitfalls (autorelease pools, no manual release — SIGSEGV, 1-based page indices, why a hand-rolled `CGBitmapContextCreate` must pass `bytesPerRow=0` + explicit colorspace) and OCR artifacts ("№" → `Nº`, dropped letters, broken numbers), plus a playbook for form headers (КС-2/КС-3, acts) and arithmetic self-checks of recognised numbers. `references/upd.md` maps the УПД fields (counterparty, totals line, sum checks).

### Requirements

- macOS (Darwin only)
- System Python 3 with pyobjc (`Vision`, `Quartz`, `Foundation`)
- PyMuPDF, Pillow

```bash
pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz PyMuPDF Pillow
```

> In sandboxed environments (e.g. `run_python`) pyobjc is usually unavailable — run the script via a regular shell with system `python3`.

### Installation

The skill is a folder containing `SKILL.md` (folder name = skill name).

Global skill (available in all projects):

```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git ~/.lmstudio/skills/apple-vision-pdf-ocr
```

(on older installs the skills folder is `~/.cache/lm-studio/skills`)

Project skill (for a specific project only):

```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git <project>/.agents/skills/apple-vision-pdf-ocr
```

After cloning, rename the folder to `apple-vision-pdf-ocr` (as in the examples above) — it must match `name` in the front matter.

### Usage

```bash
python3 vision_ocr.py scan.pdf photo.jpg > text.txt
# or:
python3 vision_ocr.py big_scan.pdf --workers 6 --dpi 150 > text.txt
```

Or import the functions: `ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`, `crop_ocr(path, page_index, needle, det_dpi=200, dpi=800)`.

Output: text to stdout; PDF pages are marked with `--- page N ---`. Per-page errors appear as `[OCR ERROR ...]` markers.

Read one table row left to right (cells of the row containing the label):

```bash
python3 scripts/vision_table_row.py invoice.pdf --page 1 --label "Всего к оплате"
# → 6 200,00 | 1 033,33 | 7 233,33
```

High-res re-OCR of a single garbled line:

```python
import sys
sys.path.insert(0, '/path/to/this/skill')
import vision_ocr
for matched, lines in vision_ocr.crop_ocr('act.pdf', 0, 'Итого', dpi=800):
    print(matched, '→', lines[0] if lines else '')
```

### Files

| File | Description |
|---|---|
| `SKILL.md` | Skill prompt: OCR strategy, pyobjc pitfalls, recognition artifacts, form-header playbook |
| `vision_ocr.py` | Ready-to-use script: CLI + importable functions (`ocr_pdf`, `ocr_image`, `vision_page`, `crop_ocr`) |
| `scripts/vision_table_row.py` | CLI + helpers to read one table row by label (`render_page`, `ocr_bboxes`) |
| `scripts/make_test_scan.py` | Generates a synthetic scan (text PDF + image-only PDF + PNG) for smoke tests |
| `references/upd.md` | УПД field map: key fields, the totals line, how to verify sums |

---

## Русский

### Что делает

Скилл сначала читает текстовый слой PyMuPDF; страницы, оказавшиеся сканами (меньше 40 символов текста), рендерятся в CGImage при ~150 dpi и распознаются Apple Vision (ru-RU + en-US). Растровые картинки отправляются в Vision напрямую.

### Возможности

- **PDF:** страницы с текстовым слоем читаются напрямую; «сканы» (страницы с < 40 символов) рендерятся в CGImage (~150 dpi) и распознаются Vision; для редких битых PDF есть fallback-рендер через PyMuPDF.
- **Картинки:** PNG/JPG/TIFF распознаются напрямую через Vision.
- **Производительность:** параллельная обработка страниц (ThreadPoolExecutor), ротация autorelease-пулов — память стабильна (~700–800 МБ), ~2.4 стр/сек на 6 потоках.
- **Высоко-резкое повторное OCR:** `crop_ocr()` находит строку Vision'ом на низком dpi, затем распознаёт только её полоску из рендера 800+ dpi — чинит схлопнувшиеся формулы, верхние индексы и реквизиты без медленного прохода всей страницы на высоком разрешении.
- **Строки таблиц по порядку:** `scripts/vision_table_row.py` печатает клетки одной строки слева→направо (метка → y-полоса → сортировка по x) и отдаёт bbox всех блоков, если нужно своё чтение.
- **Самопроверка:** `scripts/make_test_scan.py` собирает синтетический образец (PDF с настоящим текстовым слоем, та же страница в PNG и PDF только из картинки) — правки OCR проверяются, не трогая реальные документы.
- **База знаний:** в `SKILL.md` задокументированы подводные камни pyobjc (autorelease-пулы, запрет ручного release — SIGSEGV, 1-based индексы страниц, обязательные `bytesPerRow=0` и явный colorspace в `CGBitmapContextCreate`) и артефакты распознавания («№» → `Nº`, опавшие буквы, разорванные номера), а также порядок чтения реквизитов шапки бланков (КС-2/КС-3, акты) и арифметическая проверка распознанных цифр. В `references/upd.md` — карта полей УПД (контрагент, строка итогов, проверка сумм).

### Требования

- macOS (только Darwin)
- Системный Python 3 с pyobjc (`Vision`, `Quartz`, `Foundation`)
- PyMuPDF, Pillow

```bash
pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz PyMuPDF Pillow
```

> В изолированных sandbox-окружениях (например, `run_python`) pyobjc обычно нет — скрипт выполняется через обычный shell с системным `python3`.

### Установка

Скилл — это папка с `SKILL.md` (имя папки = имя скилла).

Глобальный скилл (доступен во всех проектах):

```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git ~/.lmstudio/skills/apple-vision-pdf-ocr
```

(на старых установках папка скиллов — `~/.cache/lm-studio/skills`)

Проектный скилл (только для конкретного проекта):

```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git <project>/.agents/skills/apple-vision-pdf-ocr
```

После клонирования переименуйте папку в `apple-vision-pdf-ocr` (как в примерах выше) — имя должно совпадать с `name` во front matter.

### Использование

```bash
python3 vision_ocr.py scan.pdf photo.jpg > text.txt
# или:
python3 vision_ocr.py big_scan.pdf --workers 6 --dpi 150 > text.txt
```

Или импортировать функции: `ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`, `crop_ocr(path, page_index, needle, det_dpi=200, dpi=800)`.

Вывод: текст в stdout; для PDF страницы помечены `--- page N ---`. Ошибки отдельных страниц — маркеры `[OCR ERROR ...]`.

Чтение одной строки таблицы слева→направо (клетки строки с меткой):

```bash
python3 scripts/vision_table_row.py счёт.pdf --page 1 --label "Всего к оплате"
# → 6 200,00 | 1 033,33 | 7 233,33
```

Высоко-резкое повторное OCR одной неразборчивой строки:

```python
import sys
sys.path.insert(0, '/path/to/this/skill')
import vision_ocr
for matched, lines in vision_ocr.crop_ocr('акт.pdf', 0, 'Итого', dpi=800):
    print(matched, '→', lines[0] if lines else '')
```

### Файлы

| Файл | Описание |
|---|---|
| `SKILL.md` | Промпт скилла: стратегия OCR, подводные камни pyobjc, артефакты распознавания, порядок чтения шапки бланков |
| `vision_ocr.py` | Готовый скрипт: CLI + импортируемые функции (`ocr_pdf`, `ocr_image`, `vision_page`, `crop_ocr`) |
| `scripts/vision_table_row.py` | CLI + хелперы для чтения одной строки таблицы по метке (`render_page`, `ocr_bboxes`) |
| `scripts/make_test_scan.py` | Генерирует синтетический скан (текстовый PDF + PDF из картинки + PNG) для самопроверки |
| `references/upd.md` | Карта полей УПД: ключевые поля, строка итогов, как проверять суммы |

---

## License / Лицензия

MIT — use as-is. / Использовать как есть.
