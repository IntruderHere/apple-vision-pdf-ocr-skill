# Apple Vision PDF OCR — скилл для LM Studio Bionic

**RU:** Скилл, который учит агента распознавать текст в сканах PDF и картинках через Apple Vision (macOS). Сначала берёт текстовый слой PyMuPDF, а страницы-сканы и изображения распознаёт Vision OCR (ru-RU + en-US).

**EN:** A skill that teaches the agent to extract text from scanned PDFs and images using Apple Vision on macOS. It reads the PyMuPDF text layer first, then OCRs scanned pages and images with Vision (ru-RU + en-US).

---

## Возможности / Features

- **RU:** PDF: страницы с текстовым слоем читаются напрямую, «сканы» (страницы с < 40 символов) рендерятся в CGImage (~150 dpi) и распознаются Vision; есть fallback-рендер через PyMuPDF для редких битых PDF.
  **EN:** PDF: pages with a text layer are read directly; "scans" (pages with < 40 chars) are rendered to CGImage (~150 dpi) and OCR'd with Vision, with a PyMuPDF render fallback for rare broken PDFs.
- **RU:** Картинки (PNG/JPG/TIFF) распознаются напрямую через Vision.
  **EN:** Images (PNG/JPG/TIFF) are OCR'd directly via Vision.
- **RU:** Параллельная обработка страниц (ThreadPoolExecutor), ротация autorelease-пулов — память стабильна (~700–800 МБ), ~2.4 стр/сек на 6 потоках.
  **EN:** Parallel page processing (ThreadPoolExecutor) with rotating autorelease pools — stable memory (~700–800 MB), ~2.4 pages/s on 6 threads.
- **RU:** В `SKILL.md` задокументированы подводные камни pyobjc (autorelease-пулы, запрет ручного release — SIGSEGV, 1-based индексы страниц) и артефакты распознавания («№» → `Nº`, опавшие буквы, разорванные номера).
  **EN:** `SKILL.md` documents pyobjc pitfalls (autorelease pools, no manual release — SIGSEGV, 1-based page indices) and OCR artifacts ("№" → `Nº`, dropped letters, broken numbers).

## Требования / Requirements

- **RU:** macOS (только Darwin), системный Python 3 с pyobjc (`Vision`, `Quartz`, `Foundation`), PyMuPDF, Pillow.
  **EN:** macOS (Darwin only), system Python 3 with pyobjc (`Vision`, `Quartz`, `Foundation`), PyMuPDF, Pillow.

```bash
pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz PyMuPDF Pillow
```

> **RU:** В изолированных sandbox-окружениях (например, `run_python`) pyobjc обычно нет — скрипт выполняется через обычный shell с системным `python3`.
> **EN:** In sandboxed environments (e.g. `run_python`) pyobjc is usually unavailable — run the script via a regular shell with system `python3`.

## Установка / Installation

Скилл — это папка с `SKILL.md` (имя папки = имя скилла). / The skill is a folder containing `SKILL.md` (folder name = skill name).

**RU:** Глобальный скилл (доступен во всех проектах):
```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git ~/.lmstudio/skills/apple-vision-pdf-ocr
```
(на старых установках папка скиллов — `~/.cache/lm-studio/skills`)

**EN:** Global skill (available in all projects):
```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git ~/.lmstudio/skills/apple-vision-pdf-ocr
```
(on older installs the skills folder is `~/.cache/lm-studio/skills`)

**RU:** Проектный скилл (только для конкретного проекта):
```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git <project>/.agents/skills/apple-vision-pdf-ocr
```

**EN:** Project skill (for a specific project only):
```bash
git clone https://github.com/IntruderHere/apple-vision-pdf-ocr-skill.git <project>/.agents/skills/apple-vision-pdf-ocr
```

После клонирования переименуйте папку в `apple-vision-pdf-ocr` (как в примерах выше) — имя папки должно совпадать с `name` во front matter. / After cloning, rename the folder to `apple-vision-pdf-ocr` (as in the examples above) — the folder name must match `name` in the front matter.

## Использование / Usage

```bash
python3 vision_ocr.py scan.pdf photo.jpg > text.txt
# или / or:
python3 vision_ocr.py big_scan.pdf --workers 6 --dpi 150 > text.txt
```

**RU:** Или импортировать функции: `ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`.
**EN:** Or import the functions: `ocr_pdf(path)`, `ocr_image(path)`, `vision_page(path, page_index, dpi=150)`.

Вывод: текст в stdout; для PDF страницы помечены `--- page N ---`. Ошибки отдельных страниц — маркеры `[OCR ERROR ...]`. / Output: text to stdout; PDF pages are marked with `--- page N ---`. Per-page errors appear as `[OCR ERROR ...]` markers.

## Файлы / Files

| File | Description (RU) |
|---|---|
| `SKILL.md` | Промпт скилла: стратегия, подводные камни pyobjc, артефакты OCR |
| `vision_ocr.py` | Готовый скрипт: CLI + импортируемые функции |

## Лицензия / License

MIT — используйте как есть. / MIT — use as-is.
