# Apple Vision PDF OCR — LM Studio Bionic Skill (macOS)

A skill that teaches the agent to extract text from scanned PDFs and images using Apple Vision on macOS.

🇬🇧 [English](#english) · 🇷🇺 [Русский](#русский)

---

## English

### What it does

The skill reads the PyMuPDF text layer first, but only trusts it when that layer is *visible* text covering a real part of the page: a scan carrying an invisible EDMS stamp ("Сформировано в системе …") is OCR'd, not skipped. Scan pages are rendered to a CGImage at ~150 dpi and read with Apple Vision (ru-RU + en-US). Output comes in reading order — one visual line per row, cells of a table row joined by a tab. Raster images go to Vision directly.

### Features

- **Page detection:** a page goes to Vision when its *visible* text layer has fewer than 40 characters, or covers under 1 % of a page that carries images; invisible or white text never counts as content. `--force-ocr` overrides.
- **Images:** PNG/JPG/TIFF/HEIC are read through ImageIO; PIL only as a fallback for exotic formats.
- **Reading order:** blocks are grouped into visual lines by bbox overlap, sorted top→bottom, cells of one row joined with a tab; `--raw` keeps Vision's own order for debugging. A sideways page (a photo rotated 90°) is detected and turned upright before OCR.
- **CLI:** `--pages 1-5,9`, `--force-ocr`, `--json` (per-page text, or blocks with bboxes and confidence), `--workers` (default `min(4, CPUs)`), `--dpi`.
- **Performance:** parallel page OCR (ThreadPoolExecutor), one autorelease pool per call — ~6–8 pages/s on 4 threads.
- **High-res re-OCR:** `crop_ocr()` finds the line at 300 dpi (auto-retry at 450 when the needle is missed), then re-reads only that strip from an 800-dpi region render; `row=True` takes the whole visual line. Matching ignores case, ё/е and lost spaces inside numbers.
- **Table rows:** `scripts/vision_table_row.py` prints the cells of one table row left to right (label → y-band → sort by x), `--json` for machine use.
- **Self-check:** `scripts/selftest.py` builds the fixtures (text PDF, scan, watermark scan, dense 9 pt table, 12-page scan) and asserts 21 checks; `scripts/make_test_scan.py` writes just the three base files.
- **Knowledge base:** `SKILL.md` documents pyobjc pitfalls — one `objc.autorelease_pool()` per call (manual `drain()` double-releases → SIGSEGV and empty pages), never `CGImageRelease` (pyobjc already owns the image), why a PyMuPDF→PNG→CGImageSource loop wedges Vision after ~30 calls, the Vision warm-up before spawning threads, 1-based page indices, `bytesPerRow=0` + explicit colorspace — plus OCR artifacts and a form-header playbook; `references/upd.md` maps the УПД fields.

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

```bash
python3 vision_ocr.py big.pdf --pages 1-5,9 --json > blocks.json   # blocks + bboxes
python3 vision_ocr.py scan.pdf --force-ocr --workers 6            # ignore the text layer
```

Or import the functions: `ocr_pdf(path)`, `ocr_pdf_pages(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`, `vision_blocks(cgimage)`, `reading_order(blocks)`, `crop_ocr(path, page_index, needle, det_dpi=300, dpi=800, row=False)`.

Output: text to stdout in reading order — tab-separated cells, `--- page N ---` markers. Per-page errors appear as `[OCR ERROR ...]` markers.

Read one table row left to right (cells of the row containing the label):

```bash
python3 scripts/vision_table_row.py invoice.pdf --page 1 --label "Всего к оплате"
# → Всего к оплате | 6 200,00 | 1 033,33 | 7 233,33
python3 scripts/vision_table_row.py invoice.pdf --page 1 --label "Всего к оплате" --json
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
| `scripts/make_test_scan.py` | Generates a synthetic sample (text PDF + image-only PDF + PNG) for smoke tests |
| `scripts/selftest.py` | Runs the 21-check self-test on generated fixtures |
| `references/upd.md` | УПД field map: key fields, the totals line, how to verify sums |

---

## Русский

### Что делает

Скилл сначала читает текстовый слой PyMuPDF, но доверяет ему только если это *видимый* текст, занимающий реальную часть страницы: скан с невидимой печатью ЭДО («Сформировано в системе …») распознаётся, а не пропускается. Страницы-сканы рендерятся в CGImage при ~150 dpi и читаются Apple Vision (ru-RU + en-US). Вывод идёт в порядке чтения — одна визуальная строка на строку, клетки строки таблицы склеены табом. Растровые картинки отправляются в Vision напрямую.

### Возможности

- **Детект страницы:** страница уходит в Vision, если её *видимый* текстовый слой короче 40 символов или занимает меньше 1 % площади страницы с картинками; невидимый или белый текст содержимым не считается. `--force-ocr` отключает проверку.
- **Картинки:** PNG/JPG/TIFF/HEIC читаются через ImageIO, PIL — только fallback для экзотических форматов.
- **Порядок чтения:** блоки собираются в визуальные строки по перекрытию bbox, сортируются сверху вниз, клетки строки склеиваются табом; `--raw` оставляет порядок Vision для отладки. Страница «на боку» (фото, повёрнутое на 90°) определяется по геометрии блоков и разворачивается перед OCR.
- **CLI:** `--pages 1-5,9`, `--force-ocr`, `--json` (текст по страницам либо блоки с bbox и confidence), `--workers` (по умолчанию `min(4, CPU)`), `--dpi`.
- **Производительность:** параллельная обработка страниц (ThreadPoolExecutor), один autorelease-пул на вызов — ~6–8 стр/сек на 4 потоках.
- **Высоко-резкое повторное OCR:** `crop_ocr()` находит строку на 300 dpi (авторетрай 450, если метка не нашлась), затем перечитывает только её полосу из региона-рендера 800 dpi; `row=True` берёт всю визуальную строку. Сравнение нечувствительно к регистру, ё/е и потерянным пробелам внутри чисел.
- **Строки таблиц:** `scripts/vision_table_row.py` печатает клетки одной строки слева→направо (метка → y-полоса → сортировка по x), `--json` — для машинной обработки.
- **Самопроверка:** `scripts/selftest.py` строит образцы (текстовый PDF, скан, скан со «штампом», плотная таблица 9 pt, 12-страничный скан) и проверяет 21 утверждение; `scripts/make_test_scan.py` пишет только три базовых файла.
- **База знаний:** в `SKILL.md` задокументированы подводные камни pyobjc — один `objc.autorelease_pool()` на вызов (ручной `drain()` даёт двойное освобождение → SIGSEGV и пустые страницы), запрет `CGImageRelease` (pyobjc владеет образом сам), почему цикл «PyMuPDF → PNG → CGImageSource» вешает Vision после ~30 вызовов, прогрев Vision перед пулом потоков, 1-based индексы страниц, обязательные `bytesPerRow=0` и явный colorspace, — а также артефакты распознавания и порядок чтения реквизитов шапки бланков (КС-2/КС-3, акты), арифметическая проверка цифр. В `references/upd.md` — карта полей УПД.

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

```bash
python3 vision_ocr.py big.pdf --pages 1-5,9 --json > blocks.json   # блоки с bbox
python3 vision_ocr.py scan.pdf --force-ocr --workers 6            # игнорировать слой
```

Или импортировать функции: `ocr_pdf(path)`, `ocr_pdf_pages(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`, `vision_blocks(cgimage)`, `reading_order(blocks)`, `crop_ocr(path, page_index, needle, det_dpi=300, dpi=800, row=False)`.

Вывод: текст в stdout в порядке чтения — клетки через таб, страницы помечены `--- page N ---`. Ошибки отдельных страниц — маркеры `[OCR ERROR ...]`.

Чтение одной строки таблицы слева→направо (клетки строки с меткой):

```bash
python3 scripts/vision_table_row.py счёт.pdf --page 1 --label "Всего к оплате"
# → Всего к оплате | 6 200,00 | 1 033,33 | 7 233,33
python3 scripts/vision_table_row.py счёт.pdf --page 1 --label "Всего к оплате" --json
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
| `scripts/make_test_scan.py` | Генерирует синтетический образец (текстовый PDF + PDF из картинки + PNG) для самопроверки |
| `scripts/selftest.py` | Прогоняет самопроверку из 21 проверки на сгенерированных образцах |
| `references/upd.md` | Карта полей УПД: ключевые поля, строка итогов, как проверять суммы |

---

## License / Лицензия

MIT — use as-is. / Использовать как есть.
