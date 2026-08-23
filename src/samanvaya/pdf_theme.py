"""The house style: one palette, one set of fonts, one page furniture, two documents.

Both documents this tool produces reach someone other than the person who ran it. The
conformance report goes to a client as an annexure to advice; the questionnaire goes
out over an advocate's name a week before a meeting. Until now both were drawn in one
core font, pure black on pure white, with every table cell boxed — the look a program
has when nobody has decided how it should look. That is a real defect in a legal
deliverable, because a document that appears unconsidered invites a reader to treat
what it says the same way.

This module is that decision, made once. It exists as a module rather than as a habit
because a habit drifts between two renderers and a module cannot.

WHAT IS SHARED AND WHAT IS NOT
------------------------------
`BMAD/08` set the boundary between the two documents and said they share "exactly one
thing: the preparer letterhead". That sentence is amended here, deliberately and in
one direction only: they now also share the HOUSE STYLE — the wordmark, the palette,
the fonts, the running head and foot. Two documents from one firm that do not look
related is the failure the amendment prevents.

The boundary the original sentence was protecting is untouched, and is now explicit
rather than implied: **nothing about findings is shared**. There is no verdict
vocabulary in this module, no colour keyed to a finding, and no table renderer. Those
live in `pdf_report`, which is the only place in the product where a finding exists.
The questionnaire cannot reach a verdict colour from here because there is not one to
reach, and a test asserts it.

COLOUR IS NEVER THE ONLY CHANNEL
--------------------------------
Colour was introduced to end the black-and-white look, and introducing colour into a
document that reports legal findings creates a hazard the previous version did not
have: a reader could take a hue as the message. So the rule is absolute and tested —
every finding is printed as a WORD, and colour only ever repeats what the word already
says. A monochrome printout and a colour-blind reader lose decoration and no
information.

Every colour that carries text is held to a WCAG 2.1 contrast floor against the paper
(4.5:1 for text at normal size, 3:1 for text at 14pt bold or larger). That is an
objective standard rather than a matter of taste, and it is what makes the palette
survive a bad office printer.

CORE FONTS ONLY
---------------
No font is embedded. The constraint is inherited from `BMAD/08` and it is worth
keeping: an embedded typeface is a redistribution licence to audit inside a tool a
lawyer hands to clients, and the single-file binary would carry it. The professional
register is therefore bought with typography, colour, and space rather than with a
purchased typeface — a serif for prose, a sans for the system layer around it, and a
monospace where a hash has to be compared character by character.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fpdf import FPDF

from samanvaya.credentials import assert_clean

RGB = tuple[int, int, int]


# --------------------------------------------------------------------------- palette
#
# An ink-and-paper palette rather than a screen one: a deep navy that reads as
# authority in print and falls to a solid dark grey on a monochrome printer, and a
# single brass accent for rules and marks. Two colours plus neutrals is a palette; a
# third would be decoration competing with content.

PAPER: RGB = (255, 255, 255)
#: Body text. Near-black rather than #000: pure black on white is harsh in long prose
#: and is the first thing that makes a page read as machine output.
INK: RGB = (27, 31, 36)
#: Secondary prose — the reason under a question, a caption, a running head.
INK_SOFT: RGB = (90, 98, 108)
#: Muted text — an entry a reader does not need to dwell on. Dark enough to clear AA.
INK_MUTED: RGB = (99, 107, 118)
#: Primary brand. Headings, the table header band, the cover title.
NAVY: RGB = (22, 50, 79)
#: The deeper end of the primary, for the cover rule and the wordmark.
NAVY_DEEP: RGB = (13, 32, 52)
#: The accent. Rules, section marks, the number beside a question. Used at 14pt bold
#: or larger, or as a graphic, which is the register its 3:1 contrast is fit for.
BRASS: RGB = (168, 118, 44)
#: Hairlines between rows and under headings.
RULE: RGB = (201, 208, 216)
#: The lightest rule — writing guides on a form, where a darker line would compete
#: with the reader's own handwriting.
RULE_SOFT: RGB = (222, 227, 233)
#: Panel and row banding.
TINT: RGB = (243, 246, 248)
#: A warmer panel, for the cover note and the disclaimer block.
TINT_WARM: RGB = (250, 247, 240)


#: Colours used for text at normal size. Held to WCAG AA (4.5:1) against PAPER.
BODY_TEXT_COLOURS: dict[str, RGB] = {
    "INK": INK,
    "INK_SOFT": INK_SOFT,
    "INK_MUTED": INK_MUTED,
    "NAVY": NAVY,
    "NAVY_DEEP": NAVY_DEEP,
}

#: Colours used only as a graphic or at 14pt bold and above. Held to 3:1.
ACCENT_COLOURS: dict[str, RGB] = {
    "BRASS": BRASS,
}


# ----------------------------------------------------------------------------- fonts
#
# Core fonts, paired rather than defaulted. Serif for anything a reader reads in
# sentences, sans for the system layer that labels and frames it, monospace for a
# value that is compared character by character.

SERIF: str = "Times"
SANS: str = "Helvetica"
MONO: str = "Courier"


WORDMARK: str = "SAMANVAYA"
#: The one-line statement of what the tool is, set under the wordmark. It describes
#: the tool, never the document's contents.
WORDMARK_RULE: str = "Multi-jurisdiction privacy conformance"


# ------------------------------------------------------------------- colour utilities


def _channel(value: int) -> float:
    """Linearise one 0-255 sRGB channel, per WCAG 2.1."""
    proportion = value / 255.0
    if proportion <= 0.03928:
        return proportion / 12.92
    # `**` on two floats is typed as returning Any by the stubs; the cast states the
    # obvious rather than letting an untyped value leak into the contrast maths.
    return cast(float, ((proportion + 0.055) / 1.055) ** 2.4)


def relative_luminance(colour: RGB) -> float:
    """Return the WCAG relative luminance of ``colour``, 0.0 (black) to 1.0 (white)."""
    red, green, blue = colour
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(first: RGB, second: RGB) -> float:
    """Return the WCAG contrast ratio between two colours, from 1.0 to 21.0.

    Order-independent: the lighter of the two is always the numerator.
    """
    lighter = max(relative_luminance(first), relative_luminance(second))
    darker = min(relative_luminance(first), relative_luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


def hue_degrees(colour: RGB) -> float:
    """Return the hue of ``colour`` in degrees, 0.0 to 360.0. Grey returns 0.0."""
    red, green, blue = (component / 255.0 for component in colour)
    high = max(red, green, blue)
    low = min(red, green, blue)
    spread = high - low
    if spread == 0:
        return 0.0
    if high == red:
        raw = ((green - blue) / spread) % 6.0
    elif high == green:
        raw = (blue - red) / spread + 2.0
    else:
        raw = (red - green) / spread + 4.0
    return (raw * 60.0) % 360.0


def saturation(colour: RGB) -> float:
    """Return HSL saturation, 0.0 (grey) to 1.0 (fully chromatic).

    Used to hold one rule the report cannot break: a finding the tool could not
    resolve must never be drawn in a more insistent colour than a finding it could.
    """
    red, green, blue = (component / 255.0 for component in colour)
    high = max(red, green, blue)
    low = min(red, green, blue)
    spread = high - low
    if spread == 0:
        return 0.0
    total = high + low
    return spread / total if total <= 1.0 else spread / (2.0 - total)


# --------------------------------------------------------------------- text sanitiser

#: Typographic characters common in regulatory text and outside latin-1. Mapping them
#: to ASCII keeps the visual sense of the source while staying inside the core fonts'
#: repertoire.
#:
#: There were two of these maps, one per renderer, and they disagreed: the report
#: mapped U+00B7 and the questionnaire did not, so the same middle dot survived one
#: document and became a substitution mark in the other. One map, one function.
_TYPOGRAPHIC: dict[str, str] = {
    "—": "-",    # em dash
    "–": "-",    # en dash
    "‘": "'",    # left single quotation
    "’": "'",    # right single quotation
    "“": '"',    # left double quotation
    "”": '"',    # right double quotation
    "′": "'",    # prime
    "·": ".",    # middle dot
    "•": "-",    # bullet
    " ": " ",    # non-breaking space
    " ": " ",    # thin space
    " ": " ",    # narrow no-break space
    "…": "...",  # horizontal ellipsis
    "→": "->",   # rightwards arrow
    "₹": "Rs.",  # Indian rupee sign, absent from latin-1
}


def latin1(text: str) -> str:
    """Return ``text`` reduced to something a core PDF font can draw.

    Core fonts are normalised by fpdf2 through ``core_fonts_encoding``, which defaults
    to latin-1 — narrower than cp1252. This tool's own name is in Devanagari and many
    obligation summaries carry typographic dashes or curly quotes; handing either to
    the renderer unchanged raises at draw time. Every string reaching the renderer goes
    through here, in both documents.

    Order matters. Typographic substitution runs first, so an em dash becomes a hyphen
    rather than being discarded, and only then does the encode/decode round trip drop
    what genuinely has no representation.
    """
    if not text:
        return ""
    mapped = "".join(_TYPOGRAPHIC.get(character, character) for character in text)
    return mapped.encode("latin-1", errors="replace").decode("latin-1")


# ------------------------------------------------------------------------- letterhead


@dataclass(frozen=True)
class Preparer:
    """Letterhead profile — who prepared this document.

    This is the one store both documents read. Two stores would let a report and the
    questionnaire that preceded it name different firms.

    All four fields are optional because a user who wants no letterhead must not be
    forced to invent one. The firewall in ``validate`` still runs on whatever is set,
    because the letterhead reaches a file that may travel beyond the adviser.
    """

    firm: str | None = None
    adviser: str | None = None
    email: str | None = None
    phone: str | None = None

    @property
    def is_empty(self) -> bool:
        """Return True when every field is None or blank.

        A blank string is treated as absent because shell-level quoting frequently
        yields ``""`` where the user meant "not given", and rendering an empty
        letterhead line would be a defect.
        """
        return all(
            value is None or not str(value).strip()
            for value in (self.firm, self.adviser, self.email, self.phone)
        )

    def validate(self) -> None:
        """Run the credential firewall over the letterhead fields.

        The letterhead is free text and reaches a file. Connection strings, API keys
        and similar secrets must never find their way in here, so the same firewall
        used for declarations is applied to the profile. An ordinary email address
        and an ordinary phone number are NOT credential-shaped and must pass clean.
        """
        assert_clean(
            {
                "firm": self.firm,
                "adviser": self.adviser,
                "email": self.email,
                "phone": self.phone,
            }
        )

    def save(self, path: Path) -> None:
        """Write the profile as JSON so it round-trips exactly.

        This is the ONE place the tool creates a directory. Everywhere else a missing
        parent is a refusal, because silently materialising a path is how a report ends
        up somewhere nobody looks. Here the user has explicitly asked for a letterhead to
        be persisted, so creating the config directory is what they asked for rather than
        something the tool decided on their behalf.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "firm": self.firm,
                    "adviser": self.adviser,
                    "email": self.email,
                    "phone": self.phone,
                },
                ensure_ascii=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> Preparer:
        """Load a saved profile, returning an empty Preparer on any failure.

        This is the deliberately permissive counterpart to ``save``: a malformed
        letterhead profile must not stop an adviser producing a document. A missing
        file, an unreadable file, malformed JSON, a wrong top-level type, or
        unexpected keys all collapse to ``Preparer()``. The exception discipline is
        "never raise", because a saved profile that once worked is allowed to keep
        working even if its on-disk shape has drifted.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()

        def _coerce(value: object) -> str | None:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            # Any non-string, non-None value is treated as absent rather than coerced,
            # so a corrupted profile cannot smuggle an arbitrary object through into
            # the renderer.
            return None

        return cls(
            firm=_coerce(raw.get("firm")),
            adviser=_coerce(raw.get("adviser")),
            email=_coerce(raw.get("email")),
            phone=_coerce(raw.get("phone")),
        )


def letterhead_lines(preparer: Preparer) -> list[tuple[str, str]]:
    """Return the letterhead as label/value pairs, with absent fields dropped.

    Returned as pairs rather than pre-joined strings so a renderer can set the label
    and the value in different weights — which is the difference between a letterhead
    and four lines of text.
    """
    pairs = (
        ("Firm", preparer.firm),
        ("Adviser", preparer.adviser),
        ("Email", preparer.email),
        ("Phone", preparer.phone),
    )
    return [
        (label, str(value).strip())
        for label, value in pairs
        if value is not None and str(value).strip()
    ]


# ------------------------------------------------------------------- the page itself


class HouseStylePDF(FPDF):
    """An A4 page with this tool's furniture on it.

    Subclasses set :attr:`DOC_TITLE` and :attr:`FOOT_NOTE` and then draw their own
    body. Everything around the body — margins, the running head, the rule under it,
    the running foot with its page count — is settled here so the two documents cannot
    drift apart.

    The cover page carries no running head. ``_chrome`` is False until the cover has
    been drawn, which is what suppresses it; a running head above a cover title is the
    mark of a template nobody looked at.
    """

    #: Set by the subclass. Appears at the left of the running head.
    DOC_TITLE: str = ""
    #: Set by the subclass. Appears at the left of the running foot, small and grey.
    FOOT_NOTE: str = ""

    MARGIN_L: float = 18.0
    MARGIN_R: float = 18.0
    MARGIN_T: float = 26.0
    MARGIN_B: float = 20.0

    def __init__(self, preparer: Preparer) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.preparer = preparer
        self.set_margins(self.MARGIN_L, self.MARGIN_T, self.MARGIN_R)
        self.set_auto_page_break(auto=False, margin=self.MARGIN_B)
        # `{nb}` in the running foot is substituted with the final page count, so the
        # foot can say "Page 3 of 11" rather than "Page 3" — on a printed deliverable
        # that is what tells a reader a page is missing.
        self.alias_nb_pages()
        self.set_creator("samanvaya")
        self.set_title(latin1(self.DOC_TITLE))
        if preparer.firm:
            self.set_author(latin1(str(preparer.firm)))
        self._chrome = False

    # ---------------------------------------------------------------- measurements

    @property
    def usable_width(self) -> float:
        """Width between the left and right margins, in millimetres."""
        return self.w - self.l_margin - self.r_margin

    @property
    def content_bottom(self) -> float:
        """The y below which the running foot begins and body content must not go."""
        return self.h - self.MARGIN_B

    # ------------------------------------------------------------------- primitives

    def ink(self, colour: RGB) -> None:
        """Set the text colour."""
        self.set_text_color(*colour)

    def hairline(
        self,
        y: float,
        *,
        colour: RGB = RULE,
        width: float = 0.2,
        x_from: float | None = None,
        x_to: float | None = None,
    ) -> None:
        """Draw one horizontal rule and restore the previous line width.

        Rules are drawn with ``line`` and never with ``rect``. In `pdf_report` that is
        load-bearing: a regression test spies on ``rect`` to prove table rows do not
        overprint, and it counts one call per table cell. Decoration drawn with
        ``rect`` would be counted as a table row and the test would report a defect
        that is not there — or, worse, stop reporting one that is.
        """
        previous = self.line_width
        self.set_draw_color(*colour)
        self.set_line_width(width)
        self.line(
            self.l_margin if x_from is None else x_from,
            y,
            self.w - self.r_margin if x_to is None else x_to,
            y,
        )
        self.set_line_width(previous)

    def panel(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: RGB = TINT,
    ) -> None:
        """Fill a rectangle without calling ``rect`` — see :meth:`hairline`."""
        origin_x, origin_y = self.get_x(), self.get_y()
        self.set_fill_color(*fill)
        self.set_xy(x, y)
        self.cell(width, height, "", fill=True)
        self.set_xy(origin_x, origin_y)

    def spaced_text(
        self,
        text: str,
        *,
        size: float,
        colour: RGB,
        spacing: float = 0.9,
        style: str = "B",
        height: float = 5.0,
        align: str = "L",
        width: float | None = None,
    ) -> None:
        """Draw one letterspaced line and reset the spacing afterwards.

        Letterspaced small capitals are the whole vocabulary of the system layer here —
        the running head, a section's eyebrow, a table's column names. Tracking is what
        distinguishes a label from a heading when both are set in the same sans face.
        """
        self.set_font(SANS, style, size)
        self.ink(colour)
        self.set_char_spacing(spacing)
        self.cell(
            self.usable_width if width is None else width,
            height,
            latin1(text),
            new_x="LMARGIN",
            new_y="NEXT",
            align=align,
        )
        self.set_char_spacing(0.0)

    def eyebrow(self, text: str, *, colour: RGB = BRASS) -> None:
        """Draw the small letterspaced label that introduces a section."""
        self.spaced_text(text.upper(), size=7.5, colour=colour, spacing=1.1, height=4.4)

    def heading(
        self,
        text: str,
        *,
        size: float = 15.0,
        colour: RGB = NAVY,
        font: str = SERIF,
        height: float = 8.0,
    ) -> None:
        """Draw a section heading in the serif face."""
        self.set_font(font, "B", size)
        self.ink(colour)
        self.cell(0, height, latin1(text), new_x="LMARGIN", new_y="NEXT")

    def body(
        self,
        text: str,
        *,
        size: float = 9.5,
        colour: RGB = INK,
        font: str = SERIF,
        style: str = "",
        leading: float = 4.8,
        width: float | None = None,
    ) -> None:
        """Draw wrapped prose in the serif face."""
        self.set_font(font, style, size)
        self.ink(colour)
        self.multi_cell(
            self.usable_width if width is None else width, leading, latin1(text)
        )

    def label_value(
        self,
        label: str,
        value: str,
        *,
        label_width: float = 34.0,
        value_font: str = SANS,
        value_style: str = "",
        size: float = 8.6,
        height: float = 5.2,
    ) -> None:
        """Draw one label/value row: label in small grey caps, value in ink."""
        self.set_font(SANS, "", 7.4)
        self.ink(INK_SOFT)
        self.set_char_spacing(0.7)
        self.cell(label_width, height, latin1(label.upper()), new_x="RIGHT", new_y="TOP")
        self.set_char_spacing(0.0)
        self.set_font(value_font, value_style, size)
        self.ink(INK)
        self.cell(
            self.usable_width - label_width,
            height,
            latin1(value),
            new_x="LMARGIN",
            new_y="NEXT",
        )

    # ------------------------------------------------------------- composed blocks

    def wordmark(self, y: float) -> None:
        """Draw the wordmark and the rule beneath it at the top of a cover page."""
        self.set_xy(self.l_margin, y)
        self.spaced_text(
            WORDMARK, size=13.0, colour=NAVY_DEEP, spacing=3.4, height=7.0
        )
        self.set_x(self.l_margin)
        self.set_font(SANS, "", 7.6)
        self.ink(INK_SOFT)
        self.set_char_spacing(0.6)
        self.cell(
            0, 4.4, latin1(WORDMARK_RULE.upper()), new_x="LMARGIN", new_y="NEXT"
        )
        self.set_char_spacing(0.0)
        self.hairline(self.get_y() + 2.4, colour=BRASS, width=0.7)
        self.set_y(self.get_y() + 4.0)

    def letterhead_block(self, *, title: str = "Prepared by") -> None:
        """Draw the letterhead, or nothing at all when there is nothing to draw.

        The whole block is skipped when the preparer is empty, because a letterhead
        section with no content under it is a defect and not a placeholder.
        """
        lines = letterhead_lines(self.preparer)
        if not lines:
            return
        self.eyebrow(title)
        self.set_y(self.get_y() + 0.6)
        for label, value in lines:
            self.label_value(label, value, label_width=22.0)
        self.set_y(self.get_y() + 2.0)

    def note_panel(self, text: str, *, fill: RGB = TINT_WARM, size: float = 8.4) -> None:
        """Draw wrapped prose inside a tinted panel with a brass edge.

        Used for the two blocks a reader must not skim past: the disclaimer on the
        report and the cover note on the questionnaire.
        """
        padding = 4.0
        self.set_font(SERIF, "I", size)
        inner = self.usable_width - 2 * padding
        # `output="LINES"` returns the wrapped lines, whose count is the block height in
        # leadings. fpdf2's return type is a union across every `output` mode, so the
        # cast names the mode this call actually asked for.
        wrapped = cast(
            list[str],
            self.multi_cell(inner, size * 0.46, latin1(text), dry_run=True, output="LINES"),
        )
        height = len(wrapped) * (size * 0.46) + 2 * padding
        top = self.get_y()
        self.panel(self.l_margin, top, self.usable_width, height, fill=fill)
        self.hairline(
            top,
            colour=BRASS,
            width=0.5,
            x_from=self.l_margin,
            x_to=self.l_margin + self.usable_width,
        )
        self.set_xy(self.l_margin + padding, top + padding)
        self.set_font(SERIF, "I", size)
        self.ink(INK_SOFT)
        self.multi_cell(inner, size * 0.46, latin1(text))
        self.set_xy(self.l_margin, top + height + 3.0)

    def ensure_room(self, height: float) -> None:
        """Start a new page when ``height`` would not fit above the running foot."""
        if self.get_y() + height > self.content_bottom:
            self.add_page()

    # -------------------------------------------------------------- page lifecycle

    def header(self) -> None:  # pragma: no cover - fpdf2 calls this per page
        if not self._chrome:
            return
        self.set_y(12.0)
        self.set_font(SANS, "", 7.2)
        self.ink(INK_SOFT)
        self.set_char_spacing(0.8)
        self.cell(
            self.usable_width * 0.6, 4.0, latin1(self.DOC_TITLE.upper()), align="L"
        )
        right = self.preparer.firm or WORDMARK
        self.cell(self.usable_width * 0.4, 4.0, latin1(str(right).upper()), align="R")
        self.set_char_spacing(0.0)
        self.hairline(18.0, colour=RULE, width=0.2)
        self.set_y(self.MARGIN_T)

    def footer(self) -> None:  # pragma: no cover - fpdf2 calls this per page
        if not self._chrome:
            return
        self.hairline(self.h - 14.0, colour=RULE, width=0.2)
        self.set_y(self.h - 12.5)
        self.set_font(SANS, "", 7.2)
        self.ink(INK_MUTED)
        self.cell(self.usable_width * 0.65, 5.0, latin1(self.FOOT_NOTE), align="L")
        self.cell(
            self.usable_width * 0.35,
            5.0,
            latin1(f"Page {self.page_no()} of {{nb}}"),
            align="R",
        )
