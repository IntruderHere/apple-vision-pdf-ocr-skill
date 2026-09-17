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
- **Knowledge base:** `SKILL.md` documents pyobjc pitfalls (autorelease pools, no manual release — SIGSEGV, 1-based page indices) and OCR artifacts ("№" → `Nº`, dropped letters, broken numbers).

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

Or import the functions: `ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`.

Output: text to stdout; PDF pages are marked with `--- page N ---`. Per-page errors appear as `[OCR ERROR ...]` markers.

### Files

| File | Description |
|---|---|
| `SKILL.md` | Skill prompt: OCR strategy, pyobjc pitfalls, recognition artifacts |
| `vision_ocr.py` | Ready-to-use script: CLI + importable functions |

---

## Русский

### Что делает

Скилл сначала читает текстовый слой PyMuPDF; страницы, оказавшиеся сканами (меньше 40 символов текста), рендерятся в CGImage при ~150 dpi и распознаются Apple Vision (ru-RU + en-US). Растровые картинки отправляются в Vision напрямую.

### Возможности

- **PDF:** страницы с текстовым слоем читаются напрямую; «сканы» (страницы с < 40 символов) рендерятся в CGImage (~150 dpi) и распознаются Vision; для редких битых PDF есть fallback-рендер через PyMuPDF.
- **Картинки:** PNG/JPG/TIFF распознаются напрямую через Vision.
- **Производительность:** параллельная обработка страниц (ThreadPoolExecutor), ротация autorelease-пулов — память стабильна (~700–800 МБ), ~2.4 стр/сек на 6 потоках.
- **База знаний:** в `SKILL.md` задокументированы подводные камни pyobjc (autorelease-пулы, запрет ручного release — SIGSEGV, 1-based индексы страниц) и артефакты распознавания («№» → `Nº`, опавшие буквы, разорванные номера).

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

Или импортировать функции: `ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`.

Вывод: текст в stdout; для PDF страницы помечены `--- page N ---`. Ошибки отдельных страниц — маркеры `[OCR ERROR ...]`.

### Файлы

| Файл | Описание |
|---|---|
| `SKILL.md` | Промпт скилла: стратегия OCR, подводные камни pyobjc, артефакты распознавания |
| `vision_ocr.py` | Готовый скрипт: CLI + импортируемые функции |

---

## License / Лицензия

MIT — use as-is. / Использовать как есть.
