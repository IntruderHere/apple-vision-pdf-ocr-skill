#!/usr/bin/env python3
"""Apple Vision OCR for PDFs and images on macOS (pyobjc required).

Usage:
    python3 vision_ocr.py FILE [FILE...] [--workers N] [--dpi 150]
                               [--force-ocr] [--pages 1-5,9] [--raw] [--json]

- PDF: a page goes to Vision unless it has a *readable* text layer: the layer
  must be visible (not render-mode-3 / white watermark text, as EDMS and
  signature services add) and cover a non-trivial share of the page.
- Images (png/jpg/jpeg/tif/tiff): Apple Vision OCR directly.
- Output: text in reading order — blocks of one visual line are joined by a
  tab, lines run top to bottom. '--- page N ---' markers for PDFs, per-page
  '[OCR ERROR ...]' markers on failure.
"""
import argparse
import functools
import json
import os
import platform
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import fitz

try:
    from objc import autorelease_pool as _autorelease_pool
except Exception:  # pragma: no cover - pyobjc is required at runtime only
    _autorelease_pool = None

# A page is treated as a scan when its *visible* text layer is thinner than
# this, or when the layer covers almost nothing while the page carries images.
_TEXT_MIN_CHARS = 40
_TEXT_MIN_AREA_SHARE = 0.01


# ---------------------------------------------------------------- pools ---
@contextmanager
def _pool_scope():
    """Fresh autorelease pool for one unit of work, released on this thread.

    Use `objc.autorelease_pool()` — never create an NSAutoreleasePool and call
    drain() by hand: the python wrapper still owns the drained pool, and the
    later dealloc releases it a second time ("pool has already been drained")
    or frees CoreFoundation images from another thread. Both end in SIGSEGV
    after a few dozen pages, and in between Vision starts returning empty
    results for whole pages.
    """
    if _autorelease_pool is None:  # pragma: no cover
        yield
        return
    with _autorelease_pool():
        yield


def _scoped(func):
    """Run a public entry point inside one autorelease pool."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _pool_scope():
            return func(*args, **kwargs)
    return wrapper


def _get_pool():
    """Deprecated no-op, kept for snippets that used to call it."""
    return None


# -------------------------------------------------- text-layer detection ---
_SPACE_VARIANTS = re.compile('[\u00a0\u2007\u2009\u202f]')


def _clean_text_layer(text):
    """Text-layer text: NBSP → space, CRLF → LF.

    PyMuPDF keeps U+00A0/U+202F between words, so `'Всего к оплате' in text`
    fails on a perfectly good text layer while the same page OCR'd from an
    image matches. Normalising here keeps both branches consistent.
    """
    text = _SPACE_VARIANTS.sub(' ', text.replace('\r\n', '\n').replace('\r', '\n'))
    return '\n'.join(line.rstrip() for line in text.split('\n')).strip()


def _text_layer_status(page):
    """(visible_chars, area_share) of the page's text layer.

    Spans with render mode 3 (invisible), near-zero opacity or white fill are
    not what a human reads — counting them as page text is how a scanned page
    with a "Сформировано в системе ..." stamp gets silently skipped.
    """
    try:
        spans = page.get_texttrace()
    except Exception:
        spans = None
    if not spans:
        text = page.get_text('text').strip()
        return len(text), (0.5 if text else 0.0)
    visible_chars = 0
    area = 0.0
    for sp in spans:
        if sp.get('type') == 3 or (sp.get('opacity') or 1) <= 0.05:
            continue
        color = sp.get('color')
        if isinstance(color, int) and (color & 0xFFFFFF) == 0xFFFFFF:
            continue
        visible_chars += len(sp.get('chars') or ())
        bb = sp.get('bbox')
        if bb:
            area += max(0.0, bb[2] - bb[0]) * max(0.0, bb[3] - bb[1])
    page_area = max(1.0, float(page.rect.width) * float(page.rect.height))
    return visible_chars, area / page_area


def _page_needs_ocr(page):
    """True when the page's own text layer cannot be trusted as page text."""
    chars, share = _text_layer_status(page)
    if chars < _TEXT_MIN_CHARS:
        return True
    if share < _TEXT_MIN_AREA_SHARE and page.get_images():
        return True
    return False


# --------------------------------------------------------- rasterisation ---
def _cgimage_from_png(tmp_path):
    import Quartz
    url = Quartz.CFURLCreateWithFileSystemPath(
        None, os.path.abspath(tmp_path), Quartz.kCFURLPOSIXPathStyle, False)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if not src:
        raise RuntimeError('cannot load image via CGImageSource')
    return Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)


def pdf_page_cgimage(path, page_index, dpi=150, tmpdir=None):
    """CGImage of one PDF page: Quartz render, PyMuPDF+PNG fallback.

    NOTE: no manual CFRelease/CGContextRelease/CGPDFDocumentClose calls —
    manual release of CGBitmapContextCreateImage results double-frees and
    crashes (SIGSEGV) in this pyobjc build: pyobjc owns the returned image
    (metadata says already_cfretained) and releases it on wrapper dealloc.
    The caller keeps the reference alive; the public entry points hold one
    autorelease pool per call.
    """
    import Quartz
    try:
        url = Quartz.CFURLCreateWithFileSystemPath(
            None, os.path.abspath(path), Quartz.kCFURLPOSIXPathStyle, False)
        doc = Quartz.CGPDFDocumentCreateWithURL(url)
        page = Quartz.CGPDFDocumentGetPage(doc, page_index + 1) if doc else None  # 1-based!
        if not page:
            raise RuntimeError('Quartz: page unreadable')
        media = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
        scale = dpi / 72.0
        w_px = max(1, int(media.size.width * scale))
        h_px = max(1, int(media.size.height * scale))
        cs = Quartz.CGColorSpaceCreateDeviceRGB()
        ctx = Quartz.CGBitmapContextCreate(
            None, w_px, h_px, 8, 0, cs, Quartz.kCGImageAlphaPremultipliedLast)
        Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
        Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w_px, h_px))
        Quartz.CGContextScaleCTM(ctx, scale, scale)
        Quartz.CGContextDrawPDFPage(ctx, page)
        img = Quartz.CGBitmapContextCreateImage(ctx)
        if not img:
            raise RuntimeError('Quartz: no CGImage')
        return img
    except Exception:
        # rare: Quartz cannot parse the page (e.g. corrupt xref) — use PyMuPDF
        return _pdf_page_cgimage_fitz(path, page_index, dpi, tmpdir)


def pdf_region_cgimage(path, page_index, box, dpi=800, pad_px=0):
    """Render just `box` (normalised, origin bottom-left) of a PDF page.

    A full-page 800-dpi render of A4 is ~250 MB; cropping a rendered full page
    is the biggest memory driver in `crop_ocr`, so the region is drawn straight
    into a context sized to it. Coordinates stay in page points, the context
    transform maps the strip onto the bitmap.
    """
    import Quartz
    x0, y0, x1, y1 = box
    try:
        url = Quartz.CFURLCreateWithFileSystemPath(
            None, os.path.abspath(path), Quartz.kCFURLPOSIXPathStyle, False)
        doc = Quartz.CGPDFDocumentCreateWithURL(url)
        page = Quartz.CGPDFDocumentGetPage(doc, page_index + 1) if doc else None
        if not page:
            raise RuntimeError('Quartz: page unreadable')
        media = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
        pw_pt, ph_pt = float(media.size.width), float(media.size.height)
        scale = dpi / 72.0
        px0 = max(0.0, x0 * pw_pt * scale - pad_px)
        px1 = min(pw_pt * scale, x1 * pw_pt * scale + pad_px)
        py0 = max(0.0, y0 * ph_pt * scale - pad_px)
        py1 = min(ph_pt * scale, y1 * ph_pt * scale + pad_px)
        w_px = max(1, int(round(px1 - px0)))
        h_px = max(1, int(round(py1 - py0)))
        cs = Quartz.CGColorSpaceCreateDeviceRGB()
        ctx = Quartz.CGBitmapContextCreate(
            None, w_px, h_px, 8, 0, cs, Quartz.kCGImageAlphaPremultipliedLast)
        if not ctx:
            raise RuntimeError('Quartz: no bitmap context')
        Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
        Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w_px, h_px))
        Quartz.CGContextScaleCTM(ctx, scale, scale)
        Quartz.CGContextTranslateCTM(ctx, -px0 / scale, -py0 / scale)
        Quartz.CGContextDrawPDFPage(ctx, page)
        img = Quartz.CGBitmapContextCreateImage(ctx)
        if not img:
            raise RuntimeError('Quartz: no CGImage')
        return img
    except Exception:
        return _pdf_region_cgimage_fitz(path, page_index, box, dpi, pad_px)


def _pdf_region_cgimage_fitz(path, page_index, box, dpi=800, pad_px=0):
    """Fallback region render via PyMuPDF (used when Quartz cannot read the page)."""
    x0, y0, x1, y1 = box
    with fitz.open(path) as doc:
        page = doc.load_page(page_index)
        rect = page.rect
        pad_pt = pad_px * 72.0 / dpi
        clip = fitz.Rect(
            max(rect.x0, rect.x0 + x0 * rect.width - pad_pt),
            max(rect.y0, rect.y0 + (1 - y1) * rect.height - pad_pt),
            min(rect.x1, rect.x0 + x1 * rect.width + pad_pt),
            min(rect.y1, rect.y0 + (1 - y0) * rect.height + pad_pt),
        )
        pix = page.get_pixmap(dpi=dpi, alpha=False, clip=clip)
    return _cgimage_from_pixmap(pix)


def _cgimage_from_pixmap(pix):
    """PyMuPDF pixmap → CGImage without a PNG round-trip."""
    import Quartz
    data = pix.samples
    cfdata = Quartz.CFDataCreate(None, bytes(data), len(data))
    provider = Quartz.CGDataProviderCreateWithCFData(cfdata)
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    return Quartz.CGImageCreate(
        pix.width, pix.height, 8, 24, pix.stride, cs,
        Quartz.kCGBitmapByteOrderDefault, provider, None, False,
        Quartz.kCGRenderingIntentDefault)


def _pdf_page_cgimage_fitz(path, page_index, dpi=150, tmpdir=None):
    """Fallback: render the page with PyMuPDF to PNG, then load via Quartz."""
    tmpdir = tmpdir or os.path.dirname(os.path.abspath(__file__))
    with fitz.open(path) as doc:
        pix = doc.load_page(page_index).get_pixmap(dpi=dpi, alpha=False)
    tmp = os.path.join(tmpdir, f'_vision_pg{page_index}_{os.getpid()}_{id(pix)}.png')
    pix.save(tmp)
    try:
        img = _cgimage_from_png(tmp)
        if not img:
            raise RuntimeError('cannot create CGImage from rendered page')
        return img
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ------------------------------------------------------------------ OCR ---
def vision_blocks(cgimage, min_confidence=0.0):
    """Vision OCR with geometry: one dict per text block.

    Keys: text, confidence, x, y, w, h — normalised 0..1, origin BOTTOM-left
    (Vision `boundingBox()`). Raises RuntimeError when Vision itself fails:
    an empty list must mean "nothing recognised", not "the request broke".
    """
    import Vision
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLanguages_(["ru-RU", "en-US"])
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cgimage, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f'Vision OCR failed: {err}')
    out = []
    for obs in (req.results() or []):
        cands = obs.topCandidates_(1)
        if not cands:
            continue
        text = str(cands[0].string()).strip()
        if not text:
            continue
        try:
            conf = float(cands[0].confidence())
        except Exception:
            conf = 1.0
        if conf < min_confidence:
            continue
        b = obs.boundingBox()
        out.append({
            'text': text,
            'confidence': conf,
            'x': float(b.origin.x),
            'y': float(b.origin.y),
            'w': float(b.size.width),
            'h': float(b.size.height),
        })
    return out


def rotated_cgimage(cgimage, degrees):
    """Rotate a CGImage by 90/180/270 degrees (counter-clockwise)."""
    import Quartz
    W = int(Quartz.CGImageGetWidth(cgimage))
    H = int(Quartz.CGImageGetHeight(cgimage))
    if degrees in (90, 270):
        w, h = H, W
    else:
        w, h = W, H
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(
        None, max(1, w), max(1, h), 8, 0, cs, Quartz.kCGImageAlphaPremultipliedLast)
    if not ctx:
        return None
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, max(1, w), max(1, h)))
    Quartz.CGContextTranslateCTM(ctx, w / 2.0, h / 2.0)
    Quartz.CGContextRotateCTM(ctx, degrees * 3.141592653589793 / 180.0)
    Quartz.CGContextTranslateCTM(ctx, -W / 2.0, -H / 2.0)
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, W, H), cgimage)
    return Quartz.CGBitmapContextCreateImage(ctx)


def _heading_score(blocks):
    """Vertical position (0 = bottom) of the tallest — then widest — block.

    Used only to choose between two sideways interpretations: the heading of a
    document belongs near the top, so the candidate that puts it higher wins.
    """
    if not blocks:
        return 0.0
    tallest = max(blocks, key=lambda b: (b['h'], b['w']))
    return tallest['y'] + tallest['h'] / 2.0


def ocr_upright(cgimage):
    """Vision blocks of an image, rotated upright if the page is sideways.

    Vision recognises text at any angle but reports bboxes in the unrotated
    image, so line grouping falls apart on a sideways page. Only a sideways
    page pays for the extra passes; an upright page is never re-rotated, and
    180°-rotated scans are left as Vision reads them (there is no cheap signal
    that says which way round a page is — crop/rotate it upright beforehand).
    """
    blocks = vision_blocks(cgimage)
    if not looks_rotated(blocks):
        return blocks
    candidates = []
    for degrees in (90, 270):
        turned = rotated_cgimage(cgimage, degrees)
        if not turned:
            continue
        alt = vision_blocks(turned)
        if alt and not looks_rotated(alt):
            candidates.append(alt)
    if not candidates:
        return blocks
    return max(candidates, key=_heading_score)


def _same_line(a, b):
    """Vertical-overlap test: two blocks belong to the same visual line."""
    a1, a2 = a['y'], a['y'] + a['h']
    b1, b2 = b['y'], b['y'] + b['h']
    overlap = min(a2, b2) - max(a1, b1)
    return overlap > 0.5 * min(a['h'], b['h'])


def _same_column(a, b):
    """Horizontal-overlap test: two blocks belong to the same column."""
    a1, a2 = a['x'], a['x'] + a['w']
    b1, b2 = b['x'], b['x'] + b['w']
    overlap = min(a2, b2) - max(a1, b1)
    return overlap > 0.5 * min(a['w'], b['w'])


def looks_rotated(blocks):
    """True when most blocks are taller than wide — the page is sideways.

    Vision recognises rotated text but keeps bboxes in the unrotated image
    space, so line grouping by y would shred a sideways page into nonsense.
    """
    if not blocks:
        return False
    tall = sum(1 for b in blocks if b['h'] > 1.6 * b['w'])
    return tall / float(len(blocks)) > 0.6


def reading_order(blocks, sep='\t', rotated=None):
    """Group blocks into visual lines and join them with `sep`.

    Vision returns blocks in no useful order — column-major output of a table
    is the default. Upright text: lines top→bottom, cells left→right, joined
    with a tab. Sideways text (a photo rotated 90°): columns are the original
    lines, read left→right, each column bottom→top.
    """
    if rotated is None:
        rotated = looks_rotated(blocks)
    if rotated:
        columns = []
        for b in sorted(blocks, key=lambda b: (b['x'], b['y'])):
            for column in columns:
                if _same_column(column[0], b):
                    column.append(b)
                    break
            else:
                columns.append([b])
        out = []
        for column in columns:
            column.sort(key=lambda b: -b['y'])
            out.append(sep.join(b['text'] for b in column))
        return out

    lines = []
    for b in sorted(blocks, key=lambda b: (-(b['y'] + b['h'] / 2.0), b['x'])):
        for line in lines:
            if _same_line(line[0], b):
                line.append(b)
                break
        else:
            lines.append([b])
    out = []
    for line in lines:
        line.sort(key=lambda b: b['x'])
        out.append(sep.join(b['text'] for b in line))
    return out


def vision_ocr_lines(cgimage, ordered=True, sep='\t'):
    """OCR a CGImage → list of strings (one per visual line)."""
    blocks = ocr_upright(cgimage)
    if not ordered:
        return [b['text'] for b in blocks]
    return reading_order(blocks, sep=sep)


@_scoped
def vision_page(path, page_index, dpi=150, ordered=True):
    """OCR one PDF page: text, one visual line per output line."""
    img = pdf_page_cgimage(path, page_index, dpi)
    return '\n'.join(vision_ocr_lines(img, ordered=ordered))


# -------------------------------------------------- high-res re-OCR (crop) ---
def _normalize(s):
    return re.sub(r'\s+', ' ', s.casefold().replace('ё', 'е')).strip()


def _needle_variants(needle):
    base = _normalize(needle)
    variants = {base, base.replace(' ', '')}
    variants.discard('')
    return variants


def _find_hits(blocks, needle):
    """Substring match immune to case, ё/е and spaces lost inside numbers."""
    variants = _needle_variants(needle)
    hits = []
    for b in blocks:
        text = _normalize(b['text'])
        if not text:
            continue
        squash = text.replace(' ', '')
        if any(v in text or v in squash for v in variants):
            hits.append(b)
    return hits


def crop_ocr(path, page_index, needle, det_dpi=300, dpi=800, pad=25,
             row=False, retries=(450,), max_det_dpi=600):
    """High-res OCR of a line of a PDF page (two-stage, retry-safe).

    Stage 1: Vision at `det_dpi` finds every block containing `needle`
    (case/ё-insensitive, spaces ignored). No hit → retried at each dpi in
    `retries` up to `max_det_dpi`, because Vision drops small text at low
    resolution and a silent `[]` looks like "the line is not there".
    Stage 2: that strip is cropped from a Quartz render at `dpi` (bboxes are
    normalised, so the crop scales linearly; `pad` is scaled too) and only the
    crop is OCR'd. Full-page Vision at 600+ dpi is very slow; this is not.
    `row=True` widens the crop to the whole visual line (every cell of the
    table row, the rest of the formula); `row=False` keeps the matched block.

    Both stages render through Quartz, not "PyMuPDF → PNG → CGImageSource":
    the PNG round-trip wedges Vision after a few dozen calls in one process
    (requests stop returning), while the Quartz path survives hundreds.

    Returns list of (matched_text, [lines_of_the_crop]); [] if nothing matched.
    """
    def _detect(dpi_det):
        return ocr_upright(pdf_page_cgimage(path, page_index, dpi_det))

    with _pool_scope():
        det_used = det_dpi
        blocks = _detect(det_used)
        hits = _find_hits(blocks, needle)
        for next_dpi in retries:
            if hits or next_dpi > max_det_dpi:
                break
            det_used = next_dpi
            blocks = _detect(det_used)
            hits = _find_hits(blocks, needle)
        if not hits:
            return []

        if row:
            boxes = []
            for hit in hits:
                line = [b for b in blocks if _same_line(b, hit)]
                boxes.append((
                    hit['text'],
                    (min(b['x'] for b in line),
                     min(b['y'] for b in line),
                     max(b['x'] + b['w'] for b in line),
                     max(b['y'] + b['h'] for b in line)),
                ))
        else:
            boxes = [(h['text'], (h['x'], h['y'], h['x'] + h['w'], h['y'] + h['h']))
                     for h in hits]

        pad_px = int(round(pad * dpi / float(det_used)))
        results = []
        for matched_text, (x0, y0, x1, y1) in boxes:
            sub = pdf_region_cgimage(path, page_index, (x0, y0, x1, y1), dpi, pad_px)
            lines = vision_ocr_lines(sub) if sub else []
            results.append((matched_text, lines))
        return results


# ------------------------------------------------------------- documents ---
def _default_workers():
    return max(1, min(4, os.cpu_count() or 1))


def _parse_pages(spec, page_count):
    """'1-5,9' → {1,2,3,4,5,9} (1-based, clamped to the document)."""
    wanted = set()
    for chunk in str(spec).replace(' ', '').split(','):
        if not chunk:
            continue
        if '-' in chunk:
            first, _, last = chunk.partition('-')
            start = int(first or 1)
            stop = int(last) if last else page_count
            wanted.update(range(start, stop + 1))
        else:
            wanted.add(int(chunk))
    return {p for p in wanted if 1 <= p <= page_count}


@_scoped
def ocr_pdf_pages(path, dpi=150, workers=None, progress=None,
                  force_ocr=False, pages=None):
    """Per-page OCR result of a PDF.

    Returns a list of (page_no_1based, kind, payload) sorted by page, where
    kind is 'text' (trusted text layer), 'blocks' (Vision blocks) or 'error'
    (message string). `pages` is a 1-based iterable; `force_ocr` OCRs every
    selected page regardless of its text layer.
    """
    results = {}
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise RuntimeError('PDF is encrypted')
        count = doc.page_count
        selected = (_parse_pages(pages, count) if pages is not None
                    else set(range(1, count + 1)))
        text_pages = []
        job_pages = []
        for i in range(count):
            if (i + 1) not in selected:
                continue
            page = doc.load_page(i)
            if not force_ocr and not _page_needs_ocr(page):
                text_pages.append((i + 1, _clean_text_layer(str(page.get_text('text')))))
            else:
                job_pages.append(i)

    for page_no, text in text_pages:
        results[page_no] = ('text', text)
        if progress:
            progress(page_no - 1, text)

    if job_pages:
        # Pre-import pyobjc framework modules on the current thread BEFORE
        # spawning workers: concurrent first import of Quartz/Vision from
        # several threads can race during module init.
        import Quartz  # noqa
        import Vision  # noqa
        workers = workers or _default_workers()

        def _job(page_index):
            try:
                img = pdf_page_cgimage(path, page_index, dpi)
                return page_index, 'blocks', ocr_upright(img)
            except Exception as e:
                return page_index, 'error', f'[OCR ERROR p{page_index + 1}: {e}]'

        if workers > 1 and len(job_pages) > 1:
            # Vision initialises its recogniser lazily. The first concurrent
            # batch races and some pages come back with zero blocks — one cheap
            # warm-up call on this thread (72 dpi) removes that failure mode.
            try:
                ocr_upright(pdf_page_cgimage(path, job_pages[0], 72))
            except Exception:
                pass
            with ThreadPoolExecutor(max_workers=workers) as ex:
                done = list(ex.map(_job, job_pages))
        else:
            done = [_job(i) for i in job_pages]
        for page_index, kind, payload in done:
            results[page_index + 1] = (kind, payload)
            if progress:
                text = ('\n'.join(reading_order(payload))
                        if kind == 'blocks' else payload)
                progress(page_index, text)

    return [(page_no, results[page_no][0], results[page_no][1])
            for page_no in sorted(results)]


def ocr_pdf(path, dpi=150, workers=None, progress=None, force_ocr=False, pages=None):
    """Return full text of a PDF: text layer where trustworthy, OCR elsewhere."""
    out = []
    for page_no, kind, payload in ocr_pdf_pages(
            path, dpi=dpi, workers=workers, progress=progress,
            force_ocr=force_ocr, pages=pages):
        body = '\n'.join(reading_order(payload)) if kind == 'blocks' else payload
        out.append(f'--- page {page_no} ---\n{body}')
    return '\n\n'.join(out)


def _image_cgimage_via_pil(path):
    """Fallback loader for formats ImageIO refuses: PIL → PNG → CGImage."""
    from PIL import Image
    import tempfile
    with Image.open(path) as im:
        im.draft('RGB', (2500, 2500))
        im = im.convert('RGB')
        fd, tmp = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        im.save(tmp, 'PNG')
    try:
        return _cgimage_from_png(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def image_blocks(path, min_confidence=0.0):
    """Vision blocks of a raster image (png/jpg/tiff/heic/...)."""
    import Quartz
    with _pool_scope():
        url = Quartz.CFURLCreateWithFileSystemPath(
            None, os.path.abspath(path), Quartz.kCFURLPOSIXPathStyle, False)
        src = Quartz.CGImageSourceCreateWithURL(url, None)
        img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None) if src else None
        if img is None:
            img = _image_cgimage_via_pil(path)
        if img is None:
            raise RuntimeError(f'cannot read image: {path}')
        return ocr_upright(img) if min_confidence <= 0 else vision_blocks(
            img, min_confidence=min_confidence)


def ocr_image(path):
    """OCR a raster image file (png/jpg/tiff/...) via Apple Vision."""
    return '\n'.join(reading_order(image_blocks(path)))


# ------------------------------------------------------------------- CLI ---
def main():
    ap = argparse.ArgumentParser(
        description='Apple Vision OCR for PDFs and images (macOS).',
        epilog='Reading order: blocks of one visual line are joined by a tab.')
    ap.add_argument('files', nargs='+', help='PDF or image files')
    ap.add_argument('--workers', type=int, default=None,
                    help='parallel OCR threads for PDFs (default: min(4, CPUs))')
    ap.add_argument('--dpi', type=int, default=150)
    ap.add_argument('--force-ocr', action='store_true',
                    help='OCR every selected page, ignore its text layer')
    ap.add_argument('--pages', default=None,
                    help="PDF pages to process, 1-based, e.g. '1-5,9'")
    ap.add_argument('--raw', action='store_true',
                    help='keep Vision block order instead of reading order')
    ap.add_argument('--json', action='store_true',
                    help='emit JSON: per-page text or blocks with bboxes')
    args = ap.parse_args()

    if platform.system() != 'Darwin':
        sys.exit('Apple Vision is available on macOS only.')

    payload = []
    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        try:
            if ext == '.pdf':
                pages = ocr_pdf_pages(f, dpi=args.dpi, workers=args.workers,
                                      force_ocr=args.force_ocr, pages=args.pages)
                rendered = []
                for page_no, kind, body in pages:
                    if kind == 'blocks':
                        if args.json:
                            rendered.append({'page': page_no, 'blocks': body})
                        else:
                            lines = ([b['text'] for b in body] if args.raw
                                     else reading_order(body))
                            rendered.append(f'--- page {page_no} ---\n' + '\n'.join(lines))
                    elif args.json:
                        rendered.append({'page': page_no, 'text': body})
                    else:
                        rendered.append(f'--- page {page_no} ---\n{body}')
                if args.json:
                    payload.append({'file': f, 'pages': rendered})
                else:
                    if len(args.files) > 1:
                        print(f'=== FILE: {f} ===')
                    print('\n\n'.join(rendered))
                    print()
            else:
                blocks = image_blocks(f)
                if args.json:
                    payload.append({'file': f, 'pages': [{'page': 1, 'blocks': blocks}]})
                else:
                    if len(args.files) > 1:
                        print(f'=== FILE: {f} ===')
                    print('\n'.join([b['text'] for b in blocks] if args.raw
                                    else reading_order(blocks)))
                    print()
        except Exception as e:
            sys.exit(f'ERROR {f}: {e}')

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
