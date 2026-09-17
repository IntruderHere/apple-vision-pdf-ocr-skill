#!/usr/bin/env python3
"""Apple Vision OCR for PDFs and images on macOS (macOS only, pyobjc required).

Usage:
    python3 vision_ocr.py FILE [FILE...] [--workers N] [--dpi 150]

- PDF: PyMuPDF text layer first; pages with < 40 chars of text are OCR'd
  with Apple Vision (Quartz render @150 dpi, fitz render fallback).
- Images (png/jpg/jpeg/tif/tiff): Apple Vision OCR directly.

Output: text to stdout, order-preserving ('--- page N ---' markers for PDFs).
Errors on individual pages are printed as '[OCR ERROR ...]' markers.
"""
import argparse
import os
import platform
import queue
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import fitz

# ---------------------------------------------------------------- pools ---
# Per-thread rotating autorelease pools: drain every N Vision calls so
# memory stays bounded. NSAutoreleasePool is NOT a context manager in
# pyobjc — drain() must be called manually (in finally).
_TL = threading.local()
_POOL_EVERY = 50


def _get_pool():
    from Foundation import NSAutoreleasePool
    if not hasattr(_TL, 'pool') or getattr(_TL, 'count', 0) >= _POOL_EVERY:
        if hasattr(_TL, 'pool'):
            try:
                _TL.pool.drain()
            except Exception:
                pass
            _TL.pool = None
        _TL.pool = NSAutoreleasePool.alloc().init()
        _TL.count = 0
    _TL.count += 1
    return _TL.pool


# ------------------------------------------------------------------ OCR ---
def vision_ocr_lines(cgimage):
    """Run VNRecognizeTextRequest on a CGImage, return list of text blocks."""
    import Vision
    _get_pool()
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLanguages_(["ru-RU", "en-US"])
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cgimage, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f'Vision OCR failed: {err}')
    lines = []
    for obs in (req.results() or []):
        cands = obs.topCandidates_(1)
        if cands:
            t = str(cands[0].string()).strip()
            if t:
                lines.append(t)
    return lines


def _cgimage_from_png(tmp_path):
    import Quartz
    url = Quartz.CFURLCreateWithFileSystemPath(
        None, os.path.abspath(tmp_path), Quartz.kCFURLPOSIXPathStyle, False)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if not src:
        raise RuntimeError('cannot load image via CGImageSource')
    return Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)


def _vision_page(path, page_index, dpi=150, tmpdir=None):
    """OCR one PDF page. Quartz render, PyMuPDF+PNG fallback on failure.

    NOTE: no manual CFRelease/CGContextRelease/CGPDFDocumentClose calls —
    manual release of CGBitmapContextCreateImage results double-frees and
    crashes (SIGSEGV) in this pyobjc build. Ownership is handled by the
    python wrappers + the rotating autorelease pools.
    """
    import Quartz
    try:
        _get_pool()
        url = Quartz.CFURLCreateWithFileSystemPath(
            None, os.path.abspath(path), Quartz.kCFURLPOSIXPathStyle, False)
        doc = Quartz.CGPDFDocumentCreateWithURL(url)
        page = Quartz.CGPDFDocumentGetPage(doc, page_index + 1) if doc else None  # 1-based!
        if not page:
            return _vision_page_fitz(path, page_index, dpi, tmpdir)
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
        return '\n'.join(vision_ocr_lines(img))
    except Exception:
        # rare: Quartz cannot parse the page (e.g. corrupt xref) — use PyMuPDF
        return _vision_page_fitz(path, page_index, dpi, tmpdir)


def _vision_page_fitz(path, page_index, dpi=150, tmpdir=None):
    """Fallback: render the page with PyMuPDF to PNG, then OCR the PNG."""
    import Quartz
    tmpdir = tmpdir or os.path.dirname(os.path.abspath(__file__))
    with fitz.open(path) as doc:
        pix = doc.load_page(page_index).get_pixmap(dpi=dpi, alpha=False)
    tmp = os.path.join(tmpdir, f'_vision_pg{page_index}_{os.getpid()}_{id(pix)}.png')
    pix.save(tmp)
    try:
        _get_pool()
        img = _cgimage_from_png(tmp)
        if not img:
            raise RuntimeError('cannot create CGImage from rendered page')
        return '\n'.join(vision_ocr_lines(img))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def vision_page(path, page_index, dpi=150):
    return _vision_page(path, page_index, dpi)


# ------------------------------------------------------------- documents ---
def ocr_pdf(path, dpi=150, workers=1, progress=None):
    """Return full text of a PDF: text layer where present, Vision OCR for
    scanned pages. Optional progress(page_index, text) callback."""
    scan_pages = []
    page_texts = []
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise RuntimeError('PDF is encrypted')
        for i in range(doc.page_count):
            t = doc.load_page(i).get_text('text')
            if len(t.strip()) < 40:
                scan_pages.append(i)
                page_texts.append(None)
            else:
                page_texts.append(t.strip())

    if scan_pages:
        # Pre-import pyobjc framework modules on the current thread BEFORE
        # spawning workers: concurrent first import of Quartz/Vision from
        # several threads can race during module init.
        import Quartz  # noqa
        import Vision  # noqa
        from Foundation import NSAutoreleasePool  # noqa
        _get_pool()
        jobs = list(enumerate(scan_pages))
        if workers > 1 and len(jobs) > 1:
            def _job(j):
                orig_idx, pi = j
                try:
                    return orig_idx, _vision_page(path, pi, dpi)
                except Exception as e:
                    return orig_idx, f'[OCR ERROR p{pi + 1}: {e}]'
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for orig_idx, text in ex.map(_job, jobs):
                    page_texts[orig_idx] = text
                    if progress:
                        progress(orig_idx, text)
        else:
            for i in scan_pages:
                try:
                    page_texts[i] = _vision_page(path, i, dpi)
                except Exception as e:
                    page_texts[i] = f'[OCR ERROR p{i + 1}: {e}]'
                if progress:
                    progress(i, page_texts[i])

    return '\n\n'.join(f'--- page {i + 1} ---\n{t}' for i, t in enumerate(page_texts))


def ocr_image(path):
    """OCR a raster image file (png/jpg/tiff/...) via Apple Vision."""
    from PIL import Image
    import tempfile
    with Image.open(path) as im:
        im.draft('RGB', (2500, 2500))
        im = im.convert('RGB')
        fd, tmp = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        im.save(tmp, 'PNG')
    try:
        _get_pool()
        img = _cgimage_from_png(tmp)
        if not img:
            raise RuntimeError('cannot create CGImage')
        return '\n'.join(vision_ocr_lines(img))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('files', nargs='+', help='PDF or image files')
    ap.add_argument('--workers', type=int, default=1,
                    help='parallel Vision OCR threads for PDFs (default 1)')
    ap.add_argument('--dpi', type=int, default=150)
    args = ap.parse_args()

    if platform.system() != 'Darwin':
        sys.exit('Apple Vision is available on macOS only.')

    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        if len(args.files) > 1:
            print(f'=== FILE: {f} ===')
        try:
            if ext == '.pdf':
                print(ocr_pdf(f, dpi=args.dpi, workers=args.workers))
            else:
                print(ocr_image(f))
        except Exception as e:
            sys.exit(f'ERROR {f}: {e}')
        print()


if __name__ == '__main__':
    main()
