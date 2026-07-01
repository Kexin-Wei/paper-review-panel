"""PDF loading + guards. No network: we synthesise a tiny valid PDF with pypdf."""

from __future__ import annotations

import base64
import io

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
    assert doc.size_bytes > 0
    # base64 round-trips back to the original bytes
    assert base64.standard_b64decode(doc.b64) == doc.data


def test_document_block_has_cache_control_when_enabled(tmp_path):
    p = tmp_path / "paper.pdf"
    p.write_bytes(_make_pdf(1))
    doc = load_pdf(str(p))
    block = doc.document_block(cache=True)
    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"
    assert block["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in doc.document_block(cache=False)


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
