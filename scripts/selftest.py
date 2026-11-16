#!/usr/bin/env python3
"""Самопроверка OCR-скриптов на синтетических образцах.

    python3 scripts/selftest.py [--keep]

Строит образцы во временной папке (текстовый PDF, скан-PDF, PNG, PDF с
невидимым текстовым слоем-«штампом», плотная таблица 9 pt) и проверяет:
порядок чтения, детект текстового слоя, crop_ocr (включая retry на мелком
тексте), vision_table_row и JSON-режим CLI.

Код возврата 0 — всё сошлось. `--keep` оставляет образцы и печатает путь.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_HERE)
sys.path.insert(0, _SKILL_DIR)
sys.path.insert(0, _HERE)

import fitz  # noqa: E402

import make_test_scan as mts  # noqa: E402
import vision_ocr  # noqa: E402

FAILED = []


def check(name, cond, detail=''):
    if cond:
        print(f'PASS  {name}')
    else:
        print(f'FAIL  {name}' + (f' — {detail}' if detail else ''))
        FAILED.append(name)


def build_fixtures(outdir):
    """Синтетические документы; возвращает пути."""
    font = mts._font()
    paths = {k: os.path.join(outdir, v) for k, v in (
        ('text_pdf', 'test_text.pdf'),
        ('png', 'test_scan.png'),
        ('scan_pdf', 'test_scan.pdf'),
        ('wm_pdf', 'test_wm.pdf'),
        ('dense_pdf', 'test_dense_scan.pdf'),
        ('many_pdf', 'test_many_scans.pdf'),
    )}

    doc = fitz.open()
    mts.build_page(doc, font)
    doc.save(paths['text_pdf'])
    doc.load_page(0).get_pixmap(dpi=150, alpha=False).save(paths['png'])
    doc.close()

    scan = fitz.open()
    page = scan.new_page(width=595, height=400)
    page.insert_image(page.rect, filename=paths['png'])
    scan.save(paths['scan_pdf'])
    scan.close()

    # скан + невидимый «штамп» ЭДО: раньше такая страница молча пропускалась
    wm = fitz.open()
    page = wm.new_page(width=595, height=400)
    page.insert_image(page.rect, filename=paths['png'])
    page.insert_font(fontname='F1', fontfile=font)
    page.insert_text((20, 20),
                     'Сформировано в системе электронного документооборота 1',
                     fontname='F1', fontsize=4, render_mode=3)
    wm.save(paths['wm_pdf'])
    wm.close()

    # плотная таблица 9 pt: Vision теряет часть строк на низком dpi
    dense = fitz.open()
    page = dense.new_page(width=595, height=500)
    page.insert_font(fontname='F1', fontfile=font)
    page.insert_text((40, 40), 'Ведомость объёмов работ', fontname='F1', fontsize=13)
    for i in range(12):
        y = 80 + i * 14
        page.insert_text((40, y), f'Строка {i + 1}', fontname='F1', fontsize=9)
        page.insert_text((200, y), f'{1000 + i * 111},00', fontname='F1', fontsize=9)
        page.insert_text((320, y), f'{(i + 1) * 3}', fontname='F1', fontsize=9)
    dense_png = os.path.join(outdir, 'dense.png')
    dense.load_page(0).get_pixmap(dpi=150, alpha=False).save(dense_png)
    dense_scan = fitz.open()
    page = dense_scan.new_page(width=595, height=500)
    page.insert_image(page.rect, filename=dense_png)
    dense_scan.save(paths['dense_pdf'])
    dense_scan.close()

    # 12 одинаковых скан-страниц: многопоточный режим и повторные прогоны
    many = fitz.open()
    for _ in range(12):
        page = many.new_page(width=595, height=400)
        page.insert_image(page.rect, filename=paths['png'])
    many.save(paths['many_pdf'])
    many.close()

    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--keep', action='store_true',
                    help='keep the generated fixtures and print the path')
    args = ap.parse_args()

    outdir = tempfile.mkdtemp(prefix='ocr_selftest_')
    paths = build_fixtures(outdir)

    # --- 1. текстовый слой: страница с настоящим текстом не идёт в Vision
    pages = vision_ocr.ocr_pdf_pages(paths['text_pdf'])
    check('текстовый PDF читается слоем', pages[0][1] == 'text', str(pages[0][1]))
    check('текстовый PDF содержит текст', 'Всего к оплате' in pages[0][2])
    check('текстовый слой без NBSP', '\u00a0' not in pages[0][2])

    # --- 2. скан: OCR и порядок чтения (клетки строки склеены табом)
    text = vision_ocr.ocr_pdf(paths['scan_pdf'])
    check('скан распознан',
          re.search(r'Всего к оплате\t.*6\s?200,00.*7\s?233,33', text) is not None,
          text.replace('\n', ' / ')[:160])
    check('порядок строк сверху вниз',
          text.find('Всего к оплате') < text.find('Итого по смете'),
          text.replace('\n', ' / ')[:160])
    check('скан помечен как OCR-страница',
          vision_ocr.ocr_pdf_pages(paths['scan_pdf'])[0][1] == 'blocks')

    # --- 3. невидимый текстовый слой не отменяет OCR
    wm_pages = vision_ocr.ocr_pdf_pages(paths['wm_pdf'])
    check('страница со «штампом» уходит в OCR', wm_pages[0][1] == 'blocks',
          f"kind={wm_pages[0][1]}")
    check('штамп не подменяет содержимое',
          'Всего к оплате' in vision_ocr.ocr_pdf(paths['wm_pdf']))

    # --- 4. force_ocr и --pages
    check('force_ocr игнорирует текстовый слой',
          vision_ocr.ocr_pdf_pages(paths['text_pdf'], force_ocr=True)[0][1] == 'blocks')
    check('_parse_pages: 2,4-5 из 6', vision_ocr._parse_pages('2,4-5', 6) == {2, 4, 5})
    check('_parse_pages: клип по границам', vision_ocr._parse_pages('0-2,99', 6) == {1, 2})

    # --- 5. crop_ocr: регистр, отсутствие совпадений, строка целиком, retry
    hits = vision_ocr.crop_ocr(paths['scan_pdf'], 0, 'всего к оплате')
    check('crop_ocr не зависит от регистра', bool(hits), str(hits)[:120])
    check('crop_ocr: пустой результат на мусоре',
          vision_ocr.crop_ocr(paths['scan_pdf'], 0, 'нет такой строки') == [])
    row_hits = vision_ocr.crop_ocr(paths['scan_pdf'], 0, 'Итого по смете', row=True)
    check('crop_ocr(row=True) читает строку целиком',
          bool(row_hits) and any('137' in line for line in row_hits[0][1]),
          str(row_hits)[:160])
    dense_hits = vision_ocr.crop_ocr(paths['dense_pdf'], 0, 'Строка 5')
    check('crop_ocr находит мелкий текст (9 pt)', bool(dense_hits), str(dense_hits)[:120])

    # --- 5b. многопоточный режим: ни одна страница не «теряется»
    # (гонка инициализации Vision и пулы отдавали пустые страницы / SIGSEGV)
    for trial in range(2):
        many = vision_ocr.ocr_pdf_pages(paths['many_pdf'], workers=4)
        lost = [no for no, kind, payload in many if kind != 'blocks' or not payload]
        check(f'12 страниц в 4 потока, прогон {trial + 1}: пустых нет',
              len(many) == 12 and not lost, f'страниц {len(many)}, пустые {lost}')

    # --- 6. vision_blocks: геометрия и уверенность
    blocks = vision_ocr.vision_blocks(vision_ocr.pdf_page_cgimage(paths['scan_pdf'], 0, 150))
    ok_box = all(0.0 <= b['x'] <= 1.0 and 0.0 <= b['y'] <= 1.0
                 and b['w'] > 0 and b['h'] > 0 for b in blocks)
    check('vision_blocks: bbox в 0..1', ok_box and bool(blocks))
    check('vision_blocks: confidence присутствует',
          all(0.0 <= b['confidence'] <= 1.0 for b in blocks))

    # --- 7. CLI: таблица по метке и JSON
    row = subprocess.run(
        [sys.executable, os.path.join(_HERE, 'vision_table_row.py'),
         paths['scan_pdf'], '--page', '0', '--label', 'Всего к оплате'],
        capture_output=True, text=True)
    check('vision_table_row читает строку',
          row.returncode == 0 and row.stdout.startswith('Всего к оплате | '),
          (row.stdout or row.stderr).strip()[:120])

    js = subprocess.run(
        [sys.executable, os.path.join(_SKILL_DIR, 'vision_ocr.py'),
         paths['scan_pdf'], '--json'],
        capture_output=True, text=True)
    try:
        data = json.loads(js.stdout)
        has_blocks = bool(data[0]['pages'][0]['blocks'][0]['text'])
    except Exception as e:  # noqa: BLE001
        data, has_blocks = None, False
        check('CLI --json разбирается', False, f'{e}: {js.stdout[:120]}')
    else:
        check('CLI --json разбирается', has_blocks)

    if args.keep:
        print(f'\nfixtures: {outdir}')
    else:
        shutil.rmtree(outdir, ignore_errors=True)

    print()
    if FAILED:
        print(f'ПРОВАЛЕНО {len(FAILED)}: ' + ', '.join(FAILED))
        return 1
    print('все проверки пройдены')
    return 0


if __name__ == '__main__':
    sys.exit(main())
