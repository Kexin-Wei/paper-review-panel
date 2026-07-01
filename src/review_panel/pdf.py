"""Load a PDF from a URL or local path into a form Claude can consume.

Claude renders every PDF page as an image *and* extracts its text, so attaching
the raw PDF is enough for the panel to judge figures and tables directly.
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from pypdf import PdfReader

from .config import DEFAULT_MAX_PAGES, MAX_PDF_BYTES

_DOWNLOAD_TIMEOUT = 60.0


@dataclass
class PdfDoc:
    source: str
    filename: str
    data: bytes
    n_pages: int

    @property
    def size_bytes(self) -> int:
        return len(self.data)

    @property
    def b64(self) -> str:
        return base64.standard_b64encode(self.data).decode("ascii")

    def document_block(self, cache: bool = True) -> dict:
        """A Messages API ``document`` content block for this PDF.

        When ``cache`` is set, a ``cache_control`` breakpoint is attached so the
        (large) PDF is cached once and re-read cheaply by every later call.
        """
        block: dict = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": self.b64,
            },
        }
        if cache:
            block["cache_control"] = {"type": "ephemeral"}
        return block


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


def load_pdf(src: str, max_pages: int = DEFAULT_MAX_PAGES) -> PdfDoc:
    """Load ``src`` (http(s) URL or local path) and validate size/page limits."""
    if _looks_like_url(src):
        data, filename = _fetch_url(src)
    else:
        path = Path(src).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"PDF not found: {src}")
        data = path.read_bytes()
        filename = path.name

    if not data[:5].startswith(b"%PDF"):
        raise ValueError(f"{src} does not look like a PDF (missing %PDF header).")

    if len(data) > MAX_PDF_BYTES:
        raise ValueError(
            f"PDF is {len(data) / 1_048_576:.1f} MB, over the "
            f"{MAX_PDF_BYTES / 1_048_576:.0f} MB per-request limit."
        )

    try:
        n_pages = len(PdfReader(io.BytesIO(data)).pages)
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        raise ValueError(f"Could not parse PDF {src}: {exc}") from exc

    if n_pages > max_pages:
        raise ValueError(
            f"PDF has {n_pages} pages, over the --max-pages limit of {max_pages}."
        )

    return PdfDoc(source=src, filename=filename, data=data, n_pages=n_pages)
