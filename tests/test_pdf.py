"""PDF loading + guards. No network: we synthesise a tiny valid PDF with pypdf."""

from __future__ import annotations

import io
import os

import pytest
from pypdf import PdfWriter

from review_panel.pdf import load_pdf


def _make_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_load_local_pdf(tmp_path):
    p = tmp_path / "paper.pdf"
    p.write_bytes(_make_pdf(3))
    doc = load_pdf(str(p))
    assert doc.n_pages == 3
    assert doc.filename == "paper.pdf"
    # path is an absolute filesystem path, and dir is its parent
    assert os.path.isabs(doc.path) and os.path.isfile(doc.path)
    assert doc.dir == os.path.dirname(doc.path)
    assert os.path.basename(doc.path) == "paper.pdf"
    # the paper is parsed once: one rendered PNG per page
    assert len(doc.page_images) == 3
    # content blocks share the paper: a leading text block + one image per page
    blocks = doc.content_blocks()
    assert blocks[0]["type"] == "text"
    images = [b for b in blocks if b["type"] == "image"]
    assert len(images) == 3
    assert images[0]["source"]["media_type"] == "image/png"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pdf(str(tmp_path / "nope.pdf"))


def test_non_pdf_raises(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(ValueError):
        load_pdf(str(bad))


def test_max_pages_guard(tmp_path):
    p = tmp_path / "long.pdf"
    p.write_bytes(_make_pdf(5))
    with pytest.raises(ValueError, match="max-pages"):
        load_pdf(str(p), max_pages=2)
