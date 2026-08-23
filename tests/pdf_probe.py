"""Read back what a rendered PDF actually draws.

The existing PDF tests assert on the content model — what the tool DECIDED — and on a
handful of geometry facts. Neither can answer the question a redesign has to answer:
does the artefact a client opens use colour at all, and does the right word appear on
the right page? Both are properties of the drawn bytes, not of the model.

fpdf2 compresses page content streams, so the operators are not visible in the raw
file. These helpers inflate every stream that will inflate and hand back the operator
text. Nothing here parses PDF properly — it does not need to. It needs to answer
"is there a non-grey colour operator" and "does this string appear on page 2", and a
regex over inflated operators answers both without taking on a PDF parser as a test
dependency.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path

# `q ... Q` graphics blocks and text-showing operators are all we look at. `rg` sets a
# non-stroking colour, `RG` a stroking one; both take three operands in 0..1.
_COLOUR_OP = re.compile(
    r"([0-9]*\.?[0-9]+)\s+([0-9]*\.?[0-9]+)\s+([0-9]*\.?[0-9]+)\s+(rg|RG)\b"
)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)


def content_ops(path: Path) -> str:
    """Return the concatenated, inflated content-stream operators of ``path``.

    A stream that does not inflate is skipped rather than raised on: fonts and
    metadata streams are not compressed the same way and are not what we are asking
    about.
    """
    raw = path.read_bytes()
    chunks: list[str] = []
    for match in _STREAM.finditer(raw):
        blob = match.group(1)
        try:
            blob = zlib.decompress(blob)
        except zlib.error:
            pass
        chunks.append(blob.decode("latin-1", errors="replace"))
    return "\n".join(chunks)


def colours_used(path: Path) -> set[tuple[float, float, float]]:
    """Return every RGB colour set by a colour operator, rounded to 3 places."""
    found: set[tuple[float, float, float]] = set()
    for r, g, b, _op in _COLOUR_OP.findall(content_ops(path)):
        found.add((round(float(r), 3), round(float(g), 3), round(float(b), 3)))
    return found


def has_non_grey_colour(path: Path) -> bool:
    """True when any colour operator sets three components that are not all equal.

    A pure black-and-white document sets only colours where r == g == b. This is the
    mechanical form of "it is not black and white".
    """
    return any(
        not (abs(r - g) < 0.002 and abs(g - b) < 0.002) for r, g, b in colours_used(path)
    )


def drawn_text(path: Path) -> str:
    """Return every literal string handed to a text-showing operator, whitespace-joined.

    Core-font text is written as `(literal) Tj`, so the literals are readable once the
    stream is inflated. Escaped parentheses are unescaped; nothing else is decoded,
    because nothing else is asked of this helper.
    """
    ops = content_ops(path)
    pieces = re.findall(r"\((?:\\.|[^\\()])*\)", ops)
    out: list[str] = []
    for piece in pieces:
        body = piece[1:-1]
        body = body.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
        out.append(body)
    return " ".join(out)


def page_count(path: Path) -> int:
    """Return the number of pages, counting /Type /Page and discarding /Type /Pages."""
    raw = path.read_bytes()
    return raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")


def page_texts(path: Path) -> list[str]:
    """Return the drawn text of each page separately, in page order.

    fpdf2 emits one content stream per page, in order, ahead of the font and metadata
    streams. Streams that carry no text-showing operator are dropped, which leaves the
    page streams in document order.
    """
    raw = path.read_bytes()
    pages: list[str] = []
    for match in _STREAM.finditer(raw):
        blob = match.group(1)
        try:
            blob = zlib.decompress(blob)
        except zlib.error:
            continue
        text = blob.decode("latin-1", errors="replace")
        if " Tj" not in text and " TJ" not in text:
            continue
        pieces = re.findall(r"\((?:\\.|[^\\()])*\)", text)
        rendered = " ".join(
            p[1:-1].replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
            for p in pieces
        )
        pages.append(rendered)
    return pages
