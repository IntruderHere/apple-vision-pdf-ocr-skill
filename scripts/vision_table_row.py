#!/usr/bin/env python3
"""Позиционно читать строку таблицы на странице PDF (по метке-подписи).

Рендерит страницу Quartz'ом (PyMuPDF как fallback), гоняет Vision и печатает
строку одной линией: блоки, чей y-центр попадает в полосу вокруг метки,
отсортированные по x (слева направо).

Использование:
    python3 vision_table_row.py scan.pdf --page 1 --label "Всего к оплате"
    python3 vision_table_row.py scan.pdf --page 0 --label "Итого" --dpi 300
    python3 vision_table_row.py scan.pdf --page 0 --label "Итого" --json

Полоса по умолчанию — 0.6 высоты самой метки: соседняя строка попадает в неё
только в очень плотных таблицах; тогда задайте `--band` руками и разбирайте
строку по арифметике (без налога + НДС = итого с налогом).
"""
import argparse
import json
import os
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SKILL_DIR)

import vision_ocr  # noqa: E402  (ротация autorelease-пулов, Vision, Quartz)


def render_page(path, page_index, dpi):
    """CGImage страницы PDF (Quartz, с fallback на PyMuPDF внутри vision_ocr)."""
    return vision_ocr.pdf_page_cgimage(path, page_index, dpi)


def ocr_bboxes(cgimage):
    """Блоки Vision с полями, удобными для чтения строки.

    Ключи: text, y_center (норм. от НИЗА страницы), x0, x1, h, confidence.
    """
    out = []
    for b in vision_ocr.vision_blocks(cgimage):
        out.append({
            'text': b['text'],
            'y_center': b['y'] + b['h'] / 2.0,
            'x0': b['x'],
            'x1': b['x'] + b['w'],
            'h': b['h'],
            'confidence': b['confidence'],
        })
    return out


def _default_band(labels):
    """0.6 высоты метки — строка читается целиком, соседние не липнут."""
    worst = min(labels, key=lambda b: b['h'])
    return max(0.004, 0.6 * worst['h'])


def main():
    ap = argparse.ArgumentParser(
        description='Print one table row (by label) left-to-right.')
    ap.add_argument('path')
    ap.add_argument('--page', type=int, default=0,
                    help='0-based page index (default 0)')
    ap.add_argument('--label', required=True,
                    help='label text identifying the row (substring, case-insensitive)')
    ap.add_argument('--dpi', type=int, default=200)
    ap.add_argument('--band', type=float, default=None,
                    help='y-band half-width, normalized (default: 0.6 of label height)')
    ap.add_argument('--json', action='store_true',
                    help='emit cells as JSON objects instead of one line')
    a = ap.parse_args()

    blocks = ocr_bboxes(render_page(a.path, a.page, a.dpi))
    needle = vision_ocr._normalize(a.label)
    labels = [b for b in blocks if needle and needle in vision_ocr._normalize(b['text'])]
    if not labels:
        sys.exit('label %r not found on page %d (%d blocks); '
                 'try another page or check --label' % (a.label, a.page, len(blocks)))
    if len(labels) > 1:
        print('note: %d blocks match %r — using the topmost one'
              % (len(labels), a.label), file=sys.stderr)
    labels.sort(key=lambda b: -b['y_center'])
    anchor = labels[0]
    band = a.band if a.band is not None else _default_band(labels)
    row = [b for b in blocks if abs(b['y_center'] - anchor['y_center']) <= band]
    row.sort(key=lambda b: b['x0'])

    if a.json:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    else:
        print(' | '.join(b['text'] for b in row))


if __name__ == '__main__':
    main()
