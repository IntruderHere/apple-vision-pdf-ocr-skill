#!/usr/bin/env python3
"""Сгенерировать синтетический «скан» для самопроверки OCR-скриптов.

    python3 scripts/make_test_scan.py /tmp/ocrtest

Пишет три файла:
  test_text.pdf  — страница с настоящим текстовым слоем (проверяет пропуск OCR)
  test_scan.png  — растр 150 dpi (проверяет путь картинки)
  test_scan.pdf  — та же страница, вставленная картинкой (текстового слоя нет —
                   именно этот файл гоняет OCR-путь vision_ocr/vision_table_row)

Таблица на странице: подпись + три суммы в строке, две строки — удобно для
vision_table_row.py (--label) и crop_ocr() (needle).
"""
import os
import sys

import fitz

# Шрифт с кириллицей: встроенный helv её не содержит и даёт «квадратики».
FONT_CANDIDATES = [
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/Library/Fonts/Arial.ttf',
    '/System/Library/Fonts/Supplemental/Verdana.ttf',
    '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
]

ROWS = [
    ('Всего к оплате', ('6 200,00', '1 033,33', '7 233,33'), 200),
    ('Итого по смете', ('117 862,90', '19 640,48', '137 503,38'), 240),
]
VALUE_X = (250, 360, 470)


def _font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    sys.exit('no Cyrillic TTF found; extend FONT_CANDIDATES')


def build_page(doc, fontfile):
    page = doc.new_page(width=595, height=400)
    page.insert_font(fontname='F1', fontfile=fontfile)
    page.insert_text((40, 60),
                     'АКТ о приёмке выполненных работ N 12 от 27.03.2026',
                     fontname='F1', fontsize=13)
    for label, vals, y in ROWS:
        page.insert_text((40, y), label, fontname='F1', fontsize=12)
        for x, v in zip(VALUE_X, vals):
            page.insert_text((x, y), v, fontname='F1', fontsize=12)
    return page


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else '/tmp/ocrtest'
    os.makedirs(outdir, exist_ok=True)
    fontfile = _font()

    doc = fitz.open()
    build_page(doc, fontfile)
    text_pdf = os.path.join(outdir, 'test_text.pdf')
    doc.save(text_pdf)

    png = os.path.join(outdir, 'test_scan.png')
    doc.load_page(0).get_pixmap(dpi=150, alpha=False).save(png)
    doc.close()

    scan = fitz.open()
    page = scan.new_page(width=595, height=400)
    page.insert_image(page.rect, filename=png)
    scan_pdf = os.path.join(outdir, 'test_scan.pdf')
    scan.save(scan_pdf)
    scan.close()

    for f in (text_pdf, png, scan_pdf):
        print(f'{f}  {os.path.getsize(f)} bytes')


if __name__ == '__main__':
    main()
