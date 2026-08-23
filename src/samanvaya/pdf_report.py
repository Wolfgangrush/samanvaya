"""The conformance report — the document that reaches a client.

Two things separate it from the Markdown report the adviser reads: a **letterhead**
naming who prepared it, and **tables** rather than prose. The split in this module is
deliberate. ``report_tables`` builds the content model — plain data, fully testable.
``render_pdf`` draws it. Testing a PDF by parsing the binary back would test the drawing
library, not this tool; testing the model tests the decisions this tool actually makes
about what a reader sees.

One rule carries over from every other surface: a ``contested`` finding must never be
presented as a failure. A client reading a table cannot see a rationale three columns
wide, so the verdict column has to be unambiguous on its own. That is why
``ObligationResult.CONTESTED`` becomes ``"Unresolved"`` and never anything containing
``fail`` or ``gap``.

THE HAZARD COLOUR INTRODUCED
----------------------------
The report used to be black on white. It now uses the house style in
:mod:`samanvaya.pdf_theme`, and colour in a document that reports legal findings is a
hazard the black-and-white version did not have: a reader can take a hue as the
message. Three rules answer it, and each is tested.

1. **The verdict word is always printed.** Colour repeats what the word says and never
   replaces it. A monochrome printout loses decoration and no information.
2. **No verdict is drawn in a red hue.** A gap is an obligation the declared facts
   leave unaddressed. It is not an alarm, and drawing it in red would report an
   assessment this tool does not make.
3. **Unresolved is the least insistent colour of the three.** It is a neutral slate,
   less saturated than a gap, because an unresolved finding is a fact not yet supplied
   rather than a finding against the client. Colour is the one channel that could
   quietly undo the rule the whole tool exists to enforce, so it is held to it.

The report also states no tally by verdict — not on the cover, not anywhere. The
count of obligations examined is a fact about the run; a count of satisfied ones
beside a count of gaps is a score, and a score invites the comparison between
jurisdictions that this tool refuses to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from samanvaya import __build__, __version__
from samanvaya.pdf_theme import (
    BRASS,
    INK,
    INK_MUTED,
    INK_SOFT,
    MONO,
    NAVY,
    PAPER,
    RGB,
    RULE,
    RULE_SOFT,
    SANS,
    SERIF,
    TINT,
    HouseStylePDF,
    Preparer as Preparer,
    latin1,
)
from samanvaya.report import _check_target
from samanvaya.types import (
    DISCLAIMER,
    Divergence,
    DivergencePosition,
    EngineResult,
    ObligationResult,
    RegimeId,
    RegimeRollup,
)


# Mapping from the internal ``ObligationResult`` enum to the plain-English verdict a
# client reads in the verdict column. The strings have no underscore (``not_applicable``
# is a field name, not a verdict) and ``CONTESTED`` is rendered as "Unresolved" so that
# a contested finding cannot be mistaken for a failure by a reader who has no context
# beyond the table.
_VERDICT_TEXT: dict[ObligationResult, str] = {
    ObligationResult.SATISFIED: "Satisfied",
    ObligationResult.GAP: "Gap",
    ObligationResult.CONTESTED: "Unresolved",
    ObligationResult.NOT_APPLICABLE: "Not applicable",
    ObligationResult.DOES_NOT_EXIST: "No such provision",
}


#: The colour each verdict is drawn in, keyed by the word the reader sees rather than
#: by the enum, so that the mapping cannot drift from the printed vocabulary.
#:
#: None of these is a red hue and none is brighter than the word beside it needs. See
#: the module docstring; the constraints are asserted in ``tests/test_pdf_report.py``.
_VERDICT_COLOUR: dict[str, RGB] = {
    "Satisfied": (30, 91, 62),        # deep green
    "Gap": (138, 75, 20),             # burnt amber, deliberately not red
    "Unresolved": (74, 87, 101),      # neutral slate, the least insistent of the three
    "Not applicable": INK_MUTED,
    "No such provision": INK_MUTED,
}


#: One line per verdict, printed on the report's legend page. A reader who has never
#: seen this tool's output has to be told what the five words mean before the tables
#: start, and has to be told plainly that an unresolved finding is not a failure.
_VERDICT_MEANING: tuple[tuple[str, str], ...] = (
    (
        "Satisfied",
        "The declaration establishes the facts this obligation requires.",
    ),
    (
        "Gap",
        "The declaration establishes facts that leave this obligation unaddressed.",
    ),
    (
        "Unresolved",
        "The declaration does not establish the facts this obligation turns on. This is "
        "not a finding against the client: it records a fact that has not been supplied, "
        "and it is reported rather than guessed at.",
    ),
    (
        "Not applicable",
        "The obligation exists in the instrument but does not reach the declared facts.",
    ),
    (
        "No such provision",
        "The instrument named contains no provision on this point.",
    ),
)


_COLOUR_IS_REDUNDANT: str = (
    "Colour repeats the word beside it and never carries meaning on its own. This "
    "report reads identically in black and white."
)


@dataclass(frozen=True)
class Table:
    """A single table to draw in the PDF.

    ``kind`` distinguishes the three families of table: per-regime obligation tables,
    cross-regime divergence tables and per-country incompleteness notice tables.
    ``regime`` is set only on ``kind == "regime"`` tables; the divergence and notice
    tables are about cross-regime material and have no single regime.
    """

    kind: str
    title: str
    header: list[str] | tuple[str, ...]
    rows: list[list[str]]
    regime: RegimeId | None = None
    draft: bool = False


# The jurisdiction a reader recognises, not the identifier the code uses. A client
# opening this PDF should not have to work out that `eu_gdpr` and `uk_gdpr` are two
# countries; a pack_id is an internal handle and putting it on a client-facing
# deliverable is the same class of mistake as printing `not_applicable` as a verdict.
_JURISDICTION_NAME: dict[RegimeId, str] = {
    RegimeId.INDIA: "India",
    RegimeId.EU_GDPR: "European Union",
    RegimeId.UK_GDPR: "United Kingdom",
    RegimeId.SINGAPORE_PDPA: "Singapore",
    RegimeId.US: "United States",
    RegimeId.CANADA: "Canada",
}


def _regime_title(rollup: RegimeRollup) -> str:
    """Title a per-regime table, marking draft packs.

    The word "draft" must appear in the title whenever ``pack_info.draft`` is True so
    that a reader of the PDF is warned at the heading level, not buried in a footnote
    they may miss.

    The instruments themselves are NOT repeated in the heading: every row already
    carries its instrument in its own column, and a heading that lists five statutes
    stops being a heading.
    """
    name = _JURISDICTION_NAME.get(rollup.regime) or str(rollup.pack_info.pack_id)
    if rollup.pack_info.draft:
        return f"{name} — DRAFT pack"
    return name


def report_tables(result: EngineResult) -> list[Table]:
    """Build the content model for the PDF report.

    Exactly one ``regime`` table per entry in ``result.per_regime``, one ``divergence``
    table when ``result.divergences`` is non-empty, and one ``notice`` table when
    ``result.notices`` is non-empty. The order is regimes first, then divergences,
    then notices — the order a reader scans a report: own obligations, then where
    regimes differ, then known blind spots.

    Determinism: regime iteration follows ``RegimeId`` declaration order (the same
    order ``EngineResult.all_findings`` uses), finding order within a regime follows
    the rollup order, divergence order follows the engine's order and notice order
    follows the engine's order. No dict-ordering dependence, no set iteration, no
    timestamps in the model.
    """
    tables: list[Table] = []

    for regime in RegimeId:
        rollup = result.per_regime.get(regime)
        if rollup is None:
            continue
        header = ["Result", "Obligation", "Instrument", "Provision"]
        rows: list[list[str]] = []
        for finding in rollup.findings:
            verdict = _VERDICT_TEXT[finding.result]
            rows.append(
                [
                    verdict,
                    finding.obligation.obligation_summary,
                    finding.obligation.instrument,
                    finding.obligation.provision,
                ]
            )
        tables.append(
            Table(
                kind="regime",
                title=_regime_title(rollup),
                header=header,
                rows=rows,
                regime=regime,
                draft=rollup.pack_info.draft,
            )
        )

    if result.divergences:
        divergence_header = ["Topic", "Dimension", "Regime", "Instrument", "Provision", "Position"]
        divergence_rows: list[list[str]] = []
        for divergence in result.divergences:
            for position in divergence.positions:
                divergence_rows.append(
                    [
                        _humanise(divergence.topic.value),
                        _humanise(divergence.dimension),
                        _JURISDICTION_NAME.get(position.regime, position.regime.value),
                        position.instrument,
                        position.provision,
                        _position_text(position, divergence),
                    ]
                )
        tables.append(
            Table(
                kind="divergence",
                title="Cross-regime divergences",
                header=divergence_header,
                rows=divergence_rows,
            )
        )

    if result.notices:
        notice_header = ["Regime", "Country", "Notice"]
        # A notice with ``regime is None`` is an uncovered declared
        # jurisdiction; reading ``notice.regime.value`` would raise, and
        # collapsing the row to two cells would silently drop the Regime
        # column for the case this whole table exists to surface. Render
        # the Regime cell as ``None declared`` and keep the row width at
        # three so the table stays well-formed for every reader.
        notice_rows: list[list[str]] = [
            [
                notice.regime.value if notice.regime is not None else "None declared",
                notice.country,
                notice.message,
            ]
            for notice in result.notices
        ]
        tables.append(
            Table(
                kind="notice",
                title="Incompleteness notices",
                header=notice_header,
                rows=notice_rows,
            )
        )

    return tables


def _humanise(identifier: str) -> str:
    """Render an internal identifier as something a client can read.

    The same rule the verdict column obeys: ``dsr_response_period`` is a field name, not
    a phrase, and a client-facing table that prints one is showing the reader the inside
    of the program. Underscores become spaces and the first letter is capitalised; the
    words themselves are left alone, because rewriting a statutory term into prose is
    interpretation and this function is not entitled to do that.
    """
    cleaned = identifier.replace("_", " ").strip()
    if not cleaned:
        return identifier
    return cleaned[0].upper() + cleaned[1:]


def _position_text(position: DivergencePosition, divergence: Divergence) -> str:
    """Render one regime's position, carrying its unit.

    The unit is NOT decoration. ``DivergencePosition.value`` for the GDPR Article 12(3)
    response period is the string ``"1"``, and its unit is ``"months"``. Printing the
    value alone puts a bare ``1`` in a column a client reads as a deadline, against
    another regime's ``"none prescribed"`` — a difference of a month reported as a
    difference of nothing. The position's own unit is preferred; the divergence's unit
    is the fallback for a position that does not carry one.
    """
    unit = position.unit or divergence.unit
    if unit and position.value:
        return f"{position.value} {unit}"
    return position.value


def _table_cell_widths(usable_width: float, header: list[str] | tuple[str, ...]) -> list[float]:
    """Pick cell widths proportional to the column's expected content.

    A weighted split keeps the verdict column readable on A4 portrait without making
    the obligation column absurdly narrow. The weights are deliberately coarse; a
    legal deliverable that wraps gracefully is more important than a precise fit.
    """
    weights: dict[str, list[float]] = {
        # Per-regime table: verdict narrow, obligation wide, instrument + provision
        # share the rest.
        # Wide enough to hold "Not applicable" and "No such provision" without
        # breaking mid-word. An earlier weighting gave this column 1.2 against the
        # obligation column's 5.0, which rendered the verdict as "Not applicab / le" —
        # the one column a client actually reads, broken across a line.
        "result": [2.6],
        "obligation": [1.2, 3.0, 5.0],
        "instrument": [1.2, 2.0, 3.2],
        "provision": [1.2, 1.6, 3.0],
        # Divergence table: topic + dimension narrow, position wide.
        "topic": [1.2, 1.6, 3.0],
        "dimension": [1.2, 1.8, 3.0],
        "regime": [1.0, 1.4, 2.0],
        "position": [1.2, 2.4, 5.0],
        # Notice table.
        "country": [1.0, 1.4, 2.0],
        "notice": [1.2, 3.0, 5.0],
    }
    chosen: list[float] = []
    for column in header:
        key = column.lower()
        for needle, options in weights.items():
            if needle in key:
                chosen.append(options[-1])
                break
        else:
            chosen.append(2.0)

    total = sum(chosen)
    if total <= 0:
        # Degenerate header (all empty): fall back to equal widths.
        equal = usable_width / max(len(header), 1)
        return [equal] * len(header)
    return [usable_width * (w / total) for w in chosen]


# Measured against every obligation in the six first-party packs on 2026-08-19: the
# longest ``obligation_summary`` is 516 characters and none exceeds 600. The cap is
# therefore set above the real maximum so that a client-facing deliverable does not cut
# a statutory summary mid-sentence; it exists only to stop a pathological declaration
# producing a cell taller than the page. Re-measure it if a pack grows.
_MAX_CELL_CHARS: int = 600

#: Horizontal breathing room inside a table cell. Without it, text sits hard against
#: the banding and the table reads as a spreadsheet dump rather than a set table.
_CELL_PAD: float = 2.0


def _truncate(text: str, max_chars: int) -> str:
    """Truncate ``text`` to ``max_chars`` with an ellipsis when shortened.

    A legal deliverable must stay legible, so the renderer truncates cell content to
    a sane length rather than letting long strings overflow the page boundary. The
    threshold is generous enough that real regulatory text rarely triggers it.
    """
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip() + "…"


class _SamanvayaPDF(HouseStylePDF):
    """The report's pages: a cover, a legend, and one banded table per jurisdiction."""

    DOC_TITLE = "Conformance report"
    FOOT_NOTE = "Conformance report — not legal advice"

    def draw_table(self, table: Table) -> None:
        """Draw ``table``, breaking to a new page when a row will not fit.

        The banding is drawn cell by cell with ``rect`` and the separators with
        ``line``. That division is load-bearing rather than incidental: a regression
        test spies on ``rect`` and requires exactly one call per table cell, all cells
        of a row sharing one y. It caught a defect where every row was drawn at the
        same y — a PDF that opened fine, passed every content-model test, and was
        unreadable. Nothing outside a table cell may call ``rect``, or that test starts
        measuring decoration instead of rows.

        ``output="HEIGHT"`` on the measuring pass is likewise load-bearing.
        ``multi_cell(dry_run=True)`` alone returns a BOOLEAN — whether a page break was
        triggered — not a height. Taking that bool as a height is what produced the
        defect above.

        A table that runs past a page does NOT repeat its header row. It prints a
        continuation line instead, because repeating the header would add a drawn row
        the regression test cannot tell apart from a real one.
        """
        widths = _table_cell_widths(self.usable_width, table.header)

        # ---- header band -------------------------------------------------------
        self.set_font(SANS, "B", 7.4)
        header_height = 7.4
        self.ensure_room(header_height + 8.0)
        x_start = self.l_margin
        y_start = self.get_y()
        for _column, width in zip(table.header, widths):
            self.set_fill_color(*NAVY)
            self.rect(x_start, y_start, width, header_height, style="F")
            x_start += width
        x_start = self.l_margin
        self.ink(PAPER)
        self.set_char_spacing(0.7)
        for column, width in zip(table.header, widths):
            self.set_xy(x_start + _CELL_PAD, y_start + 1.7)
            self.cell(
                width - 2 * _CELL_PAD,
                4.0,
                latin1(_truncate(str(column).upper(), 40)),
                new_x="RIGHT",
                new_y="TOP",
            )
            x_start += width
        self.set_char_spacing(0.0)
        self.set_xy(self.l_margin, y_start + header_height)

        # ---- data rows ---------------------------------------------------------
        verdict_column = 0 if table.kind == "regime" else -1
        for index, row in enumerate(table.rows):
            cell_texts = [
                latin1(_truncate(str(cell), _MAX_CELL_CHARS)) for cell in row
            ]
            self.set_font(SERIF, "", 8.6)
            heights: list[float] = []
            for position, (text, width) in enumerate(zip(cell_texts, widths)):
                self.set_font(
                    SANS if position == verdict_column else SERIF,
                    "B" if position == verdict_column else "",
                    8.0 if position == verdict_column else 8.6,
                )
                height = self.multi_cell(
                    width - 2 * _CELL_PAD,
                    4.4,
                    text,
                    border=0,
                    align="L",
                    new_x="RIGHT",
                    new_y="TOP",
                    dry_run=True,
                    output="HEIGHT",
                )
                heights.append(float(cast(float, height)))
            row_height = (max(heights) if heights else 4.4) + 2.6
            # A row taller than the page can never be laid out by paging alone, so the
            # height is clamped rather than allowed to run off the bottom edge.
            row_height = min(row_height, self.h - self.MARGIN_T - self.MARGIN_B)

            if self.get_y() + row_height > self.content_bottom:
                self.add_page()
                self._continuation_line(table.title)
            x_start = self.l_margin
            y_start = self.get_y()

            banded = index % 2 == 1
            for width in widths:
                self.set_fill_color(*(TINT if banded else PAPER))
                self.rect(x_start, y_start, width, row_height, style="F")
                x_start += width

            # The verdict's colour as a bar at the row's leading edge. Drawn with a
            # thick line, never a rect — see the note above.
            if verdict_column == 0 and cell_texts:
                self.hairline(
                    y_start + row_height / 2.0,
                    colour=_VERDICT_COLOUR.get(cell_texts[0], INK_MUTED),
                    width=row_height,
                    x_from=self.l_margin,
                    x_to=self.l_margin + 1.1,
                )

            x_start = self.l_margin
            for position, (text, width) in enumerate(zip(cell_texts, widths)):
                is_verdict = position == verdict_column
                self.set_font(
                    SANS if is_verdict else SERIF, "B" if is_verdict else "", 8.0 if is_verdict else 8.6
                )
                self.ink(
                    _VERDICT_COLOUR.get(text, INK_MUTED) if is_verdict else INK
                )
                self.set_xy(x_start + _CELL_PAD + (1.4 if position == 0 else 0.0), y_start + 1.3)
                self.multi_cell(
                    width - 2 * _CELL_PAD - (1.4 if position == 0 else 0.0),
                    4.4,
                    text,
                    border=0,
                    align="L",
                    new_x="RIGHT",
                    new_y="TOP",
                )
                x_start += width

            self.hairline(y_start + row_height, colour=RULE_SOFT, width=0.15)
            self.set_xy(self.l_margin, y_start + row_height)

        self.hairline(self.get_y(), colour=RULE, width=0.3)
        self.set_y(self.get_y() + 1.0)

    def _continuation_line(self, title: str) -> None:
        """Name the table again at the top of a continuation page.

        A reader who turns the page mid-table otherwise has a grid of provisions with
        no jurisdiction attached to it.
        """
        self.set_font(SANS, "I", 7.6)
        self.ink(INK_SOFT)
        self.cell(0, 4.6, latin1(f"{title} (continued)"), new_x="LMARGIN", new_y="NEXT")
        self.set_y(self.get_y() + 1.0)


def _cover(pdf: _SamanvayaPDF, result: EngineResult) -> None:
    """Draw the cover page: wordmark, title, particulars, letterhead, disclaimer.

    The particulars panel states what the run was, never what it found. A count of
    obligations examined is a fact about the run; a count of satisfied ones beside a
    count of gaps would be a score, and a score invites exactly the comparison between
    jurisdictions this tool refuses to make.
    """
    pdf.wordmark(20.0)
    pdf.set_y(pdf.get_y() + 26.0)

    pdf.eyebrow("Conformance report")
    pdf.set_font(SERIF, "B", 27.0)
    pdf.ink(NAVY)
    pdf.cell(0, 13.0, latin1("Conformance Report"), new_x="LMARGIN", new_y="NEXT")

    names = [
        _JURISDICTION_NAME.get(regime, regime.value)
        for regime in RegimeId
        if regime in result.per_regime
    ]
    if names:
        pdf.set_font(SERIF, "I", 12.0)
        pdf.ink(INK_SOFT)
        pdf.cell(0, 7.0, latin1(", ".join(names)), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(pdf.get_y() + 8.0)

    rows: list[tuple[str, str, str]] = [
        ("As at", result.as_at.isoformat(), SANS),
        ("Jurisdictions", str(len(result.per_regime)), SANS),
        ("Obligations", str(len(result.all_findings)), SANS),
        ("Tool", f"samanvaya {__version__} (build {__build__})", SANS),
        ("Declaration", result.declaration_hash, MONO),
    ]
    panel_height = len(rows) * 5.6 + 7.0
    top = pdf.get_y()
    pdf.panel(pdf.l_margin, top, pdf.usable_width, panel_height, fill=TINT)
    pdf.hairline(top, colour=NAVY, width=0.5)
    pdf.set_xy(pdf.l_margin + 4.0, top + 3.6)
    for label, value, font in rows:
        pdf.set_x(pdf.l_margin + 4.0)
        pdf.set_font(SANS, "", 7.4)
        pdf.ink(INK_SOFT)
        pdf.set_char_spacing(0.7)
        pdf.cell(26.0, 5.6, latin1(label.upper()), new_x="RIGHT", new_y="TOP")
        pdf.set_char_spacing(0.0)
        pdf.set_font(font, "", 8.2 if font is SANS else 7.4)
        pdf.ink(INK)
        pdf.cell(
            pdf.usable_width - 34.0,
            5.6,
            latin1(value),
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.set_y(top + panel_height + 9.0)

    pdf.letterhead_block()

    pdf.set_y(max(pdf.get_y(), pdf.h - 66.0))
    pdf.note_panel(DISCLAIMER)


def _legend(pdf: _SamanvayaPDF) -> None:
    """Draw the page that tells a first-time reader what the five verdicts mean.

    This page is not decoration. The tables use five words that look like ordinary
    English and are not: "Unresolved" in particular reads as a criticism to anyone who
    has not been told otherwise, and the whole tool exists to stop that reading. It is
    stated once, plainly, before the first table.
    """
    pdf.add_page()
    pdf.eyebrow("Before the tables")
    pdf.heading("How to read this report", size=17.0)
    pdf.set_y(pdf.get_y() + 1.0)
    pdf.hairline(pdf.get_y(), colour=BRASS, width=0.6)
    pdf.set_y(pdf.get_y() + 5.0)

    pdf.body(
        "Each table below lists the obligations of one jurisdiction and records, "
        "against the declaration supplied, what the tool found for each. One of five "
        "words appears in the first column.",
        size=9.6,
        leading=5.0,
    )
    pdf.set_y(pdf.get_y() + 3.0)

    for verdict, meaning in _VERDICT_MEANING:
        colour = _VERDICT_COLOUR.get(verdict, INK_MUTED)
        top = pdf.get_y()
        pdf.panel(pdf.l_margin, top + 1.0, 2.6, 3.4, fill=colour)
        pdf.set_xy(pdf.l_margin + 6.0, top)
        pdf.set_font(SANS, "B", 9.0)
        pdf.ink(colour)
        pdf.cell(34.0, 5.0, latin1(verdict), new_x="RIGHT", new_y="TOP")
        pdf.set_font(SERIF, "", 9.2)
        pdf.ink(INK)
        pdf.multi_cell(pdf.usable_width - 40.0, 4.7, latin1(meaning))
        pdf.set_xy(pdf.l_margin, pdf.get_y() + 2.6)

    pdf.set_y(pdf.get_y() + 2.0)
    pdf.note_panel(_COLOUR_IS_REDUNDANT, fill=TINT, size=8.6)


def render_pdf(result: EngineResult, out: Path, preparer: Preparer) -> None:
    """Render ``result`` as a PDF at ``out`` using ``preparer`` as the letterhead.

    The target is validated first by the same rules as the Markdown report writer:
    the parent must exist and be a directory, a symlink is refused, and a pre-existing
    non-regular file is refused. The check happens BEFORE any bytes are written so a
    planted symlink cannot redirect client material.

    No network access is performed during rendering. Core fonts only, no embedded TTF,
    no images, no remote URLs. Every string handed to fpdf2 passes through
    :func:`samanvaya.pdf_theme.latin1` so that Devanagari in the tool name or curly
    quotes in obligation summaries cannot crash the renderer or silently misencode.
    """
    _check_target(out)

    pdf = _SamanvayaPDF(preparer)
    pdf.add_page()
    _cover(pdf, result)

    # The running head and foot begin on the page AFTER the cover. A running head over
    # a cover title is the mark of a template nobody looked at.
    pdf._chrome = True
    _legend(pdf)

    tables = report_tables(result)
    for index, table in enumerate(tables, start=1):
        pdf.add_page()
        if table.kind == "regime":
            pdf.eyebrow(f"Jurisdiction {index} of {len(tables)}")
        else:
            pdf.eyebrow("Across jurisdictions")
        pdf.heading(table.title, size=17.0)
        if table.draft:
            pdf.set_font(SANS, "B", 8.0)
            pdf.ink(BRASS)
            pdf.cell(
                0,
                5.0,
                latin1("This pack is a draft. Check every row against the primary source."),
                new_x="LMARGIN",
                new_y="NEXT",
            )
        pdf.set_y(pdf.get_y() + 1.6)
        pdf.hairline(pdf.get_y(), colour=BRASS, width=0.6)
        pdf.set_y(pdf.get_y() + 4.6)

        if not table.rows:
            pdf.body(
                "No obligations were evaluated for this jurisdiction.",
                size=9.4,
                colour=INK_SOFT,
                style="I",
            )
            continue
        pdf.draw_table(table)

    out.write_bytes(pdf.output())
