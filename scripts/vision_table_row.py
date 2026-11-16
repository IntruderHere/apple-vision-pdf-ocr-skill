#!/usr/bin/env python3
"""Позиционно читать строку таблицы на странице PDF (по метке-подписи).

Рендерит страницу Quartz'ом, гоняет Vision, собирает (текст, bbox) по каждому
блоку и печатает строку в одну линию: блоки, чей y-центр в ±band от
y-центра метки, отсортированные по x (слева направо).

Использование:
    python3 vision_table_row.py scan.pdf --page 1 --label "Всего к оплате"
    python3 vision_table_row.py scan.pdf --page 0 --label "Итого" --dpi 300 --band 0.015

Подводка: соседняя строка (например, последняя позиция над итоговой)
может попасть в band — разбирать по смыслу/арифметике
(без налога + НДС = итого с налогом).
"""
import argparse
import os
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SKILL_DIR)

import Quartz   # noqa: E402
import Vision   # noqa: E402
import vision_ocr  # noqa: E402  (ротация autorelease-пулов)


def render_page(path, page_index, dpi):
    """Render PDF page to CGImage. Parameters — exactly as vision_ocr._vision_page:
    bytesPerRow=0 + kCGImageAlphaPremultipliedLast, otherwise 0x0 image."""
    vision_ocr._get_pool()
    url = Quartz.CFURLCreateWithFileSystemPath(
        None, os.path.abspath(path), Quartz.kCFURLPOSIXPathStyle, False)
    doc = Quartz.CGPDFDocumentCreateWithURL(url)
    page = Quartz.CGPDFDocumentGetPage(doc, page_index + 1)  # 1-based!
    if not page:
        raise RuntimeError('Quartz: cannot read page %d' % (page_index + 1))
    media = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
    scale = dpi / 72.0
    w = max(1, int(media.size.width * scale))
    h = max(1, int(media.size.height * scale))
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(
        None, w, h, 8, 0, cs, Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w, h))
    Quartz.CGContextScaleCTM(ctx, scale, scale)
    Quartz.CGContextDrawPDFPage(ctx, page)
    img = Quartz.CGBitmapContextCreateImage(ctx)
    if not img:
        raise RuntimeError('Quartz: no CGImage')
    return img


def ocr_bboxes(cgimage):
    """VNRecognizeTextRequest with per-block bboxes.
    Vision bbox: normalized, origin BOTTOM-left of image."""
    vision_ocr._get_pool()
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLanguages_(["ru-RU", "en-US"])
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cgimage, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError('Vision OCR failed: %s' % err)
    out = []
    for obs in (req.results() or []):
        c = obs.topCandidates_(1)
        if not c:
            continue
        t = str(c[0].string()).strip()
        if not t:
            continue
        b = obs.boundingBox()
        out.append({
            'text': t,
            'y_center': float(b.origin.y) + float(b.size.height) / 2.0,
            'x0': float(b.origin.x),
        })
    return out


def main():
    ap = argparse.ArgumentParser(
        description='Print one table row (by label) left-to-right.')
    ap.add_argument('path')
    ap.add_argument('--page', type=int, default=0,
                    help='0-based page index (default 0)')
    ap.add_argument('--label', required=True,
                    help='label text identifying the row (substring match)')
    ap.add_argument('--dpi', type=int, default=200)
    ap.add_argument('--band', type=float, default=0.02,
                    help='y-band half-width in normalized coords (default 0.02)')
    a = ap.parse_args()

    blocks = ocr_bboxes(render_page(a.path, a.page, a.dpi))
    labels = [b for b in blocks if a.label.lower() in b['text'].lower()]
    if not labels:
        sys.exit('label %r not found on page %d (%d blocks); '
                 'try another page or check --label' % (a.label, a.page, len(blocks)))
    ty = labels[0]['y_center']
    row = [b for b in blocks if abs(b['y_center'] - ty) <= a.band]
    row.sort(key=lambda b: b['x0'])
    print(' | '.join(b['text'] for b in row))


if __name__ == '__main__':
    main()
