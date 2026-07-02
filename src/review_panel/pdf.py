"""Load a PDF once into content the Agent SDK can send to every reviewer.

Rather than have each reviewer re-open the PDF with the ``Read`` tool (which
re-renders the whole file per session — slow and redundant), we parse the paper
a **single time** here: extract its text and render each page to a PNG. Those are
packaged as reusable message *content blocks* (one text block + one image block
per page) that the panel hands to every reviewer, so the paper is loaded once and
shared. Reviewers still see figures and tables (via the page images).
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pymupdf
from pypdf import PdfReader

from .config import DEFAULT_MAX_PAGES, MAX_PDF_BYTES

_DOWNLOAD_TIMEOUT = 60.0
# 1.5 zoom ≈ 108 dpi ≈ 1.1 MP per letter/A4 page — right under Anthropic's
# ~1.15 MP vision-ingest ceiling, so pages are taken as-is (no re-encoding).
_RENDER_ZOOM = 1.5


@dataclass
class PdfDoc:
    source: str
    filename: str
    path: str  # absolute filesystem path to the PDF
    n_pages: int
    text: str = ""                       # extracted text of the whole paper
    page_images: list[str] = field(default_factory=list)  # base64 PNG per page

    @property
    def dir(self) -> str:
        return os.path.dirname(self.path)

    def content_blocks(self) -> list[dict[str, Any]]:
        """Message content blocks representing the paper: text + page images.

        Built once and shared across every reviewer call so the PDF is parsed a
        single time. The list is a fresh copy per call (cheap — the base64 image
        strings are shared by reference), safe to append a per-reviewer prompt to.
        """
        blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"=== PAPER TEXT ({self.filename}, {self.n_pages} pages) ===\n"
                    f"{self.text}\n=== END PAPER TEXT ===\n\n"
                    "The page images that follow show the exact layout, including "
                    "all figures, tables, and equations. Use them to judge visuals."
                ),
            }
        ]
        for i, b64 in enumerate(self.page_images, start=1):
            blocks.append({"type": "text", "text": f"[Page {i}]"})
            blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                }
            )
        return blocks


def _looks_like_url(src: str) -> bool:
    return src.startswith("http://") or src.startswith("https://")


def _fetch_url(url: str) -> tuple[bytes, str]:
    with httpx.Client(follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as client:
        resp = client.get(url)
        resp.raise_for_status()
    name = os.path.basename(url.split("?", 1)[0]) or "paper.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return resp.content, name


def _extract(data: bytes) -> tuple[str, list[str]]:
    """Return (full text, list of base64 PNG page images) for a PDF byte string."""
    text_parts: list[str] = []
    images: list[str] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        matrix = pymupdf.Matrix(_RENDER_ZOOM, _RENDER_ZOOM)
        for page in doc:
            text_parts.append(page.get_text("text"))
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
    return "\n\n".join(text_parts).strip(), images


def load_pdf(src: str, max_pages: int = DEFAULT_MAX_PAGES) -> PdfDoc:
    """Load ``src`` (http(s) URL or local path), validate it, parse it once.

    Extracts the full text and renders every page to a PNG so the paper can be
    sent inline to each reviewer. Local paths are used in place; URLs download to
    a temp file.
    """
    if _looks_like_url(src):
        data, filename = _fetch_url(src)
        path = None
    else:
        p = Path(src).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"PDF not found: {src}")
        data = p.read_bytes()
        filename = p.name
        path = str(p.resolve())

    if not data[:5].startswith(b"%PDF"):
        raise ValueError(f"{src} does not look like a PDF (missing %PDF header).")

    if len(data) > MAX_PDF_BYTES:
        raise ValueError(
            f"PDF is {len(data) / 1_048_576:.1f} MB, over the "
            f"{MAX_PDF_BYTES / 1_048_576:.0f} MB limit."
        )

    try:
        n_pages = len(PdfReader(io.BytesIO(data)).pages)
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        raise ValueError(f"Could not parse PDF {src}: {exc}") from exc

    if n_pages > max_pages:
        raise ValueError(
            f"PDF has {n_pages} pages, over the --max-pages limit of {max_pages}."
        )

    if path is None:  # downloaded URL — keep a copy on disk for reference
        tmp_dir = tempfile.mkdtemp(prefix="review-panel-")
        path = os.path.join(tmp_dir, filename)
        Path(path).write_bytes(data)

    text, page_images = _extract(data)

    return PdfDoc(
        source=src,
        filename=filename,
        path=path,
        n_pages=n_pages,
        text=text,
        page_images=page_images,
    )
