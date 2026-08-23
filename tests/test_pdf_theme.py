"""Acceptance tests for the house style shared by the two client-facing documents.

Authored BEFORE the implementation.

The two PDFs this tool produces went out looking like a program's default output:
one core font, pure black on pure white, every cell boxed. That is not a stylistic
complaint. A conformance report is an annexure to legal advice and a questionnaire
goes out over an advocate's name; a deliverable that looks unconsidered invites the
reader to treat its contents the same way.

So there is now a house style, and it is a module rather than a habit, because a habit
drifts between two renderers and a module cannot. What the tests below hold it to:

1. It is not black and white, and it is legible — every colour that carries text meets
   a contrast standard against the paper rather than somebody's taste.
2. Colour NEVER carries meaning alone. The verdict word is always printed. A reader
   with a monochrome printer, or colour-blindness, loses decoration and no information.
3. The house style states nothing. Palette and chrome are shared by both documents;
   verdict vocabulary is not, and lives only where verdicts exist.

Point 3 is the load-bearing one. BMAD/08 said the two documents share "exactly one
thing: the preparer letterhead". Sharing the wordmark and the page furniture is what
makes them read as one firm's work, so they now share the house style too — but the
boundary that spec was protecting is unchanged and is asserted here directly: the
questionnaire cannot reach a verdict colour, because there are none to reach.
"""

from __future__ import annotations

import inspect
import re

import pytest


# WCAG 2.1 contrast minima. 4.5:1 for normal-size text, 3:1 for text at 14pt bold or
# larger and for non-text graphics. Used here as an objective floor, not an aspiration:
# a colour that fails is a colour a reader has to squint at on a printout.
AA_NORMAL = 4.5
AA_LARGE = 3.0


class TestThePaletteIsNotBlackAndWhite:
    def test_the_brand_colours_carry_actual_hue(self) -> None:
        """r == g == b is grey. The complaint was that everything was grey."""
        from samanvaya import pdf_theme

        for name in ("NAVY", "BRASS"):
            r, g, b = getattr(pdf_theme, name)
            assert len({r, g, b}) > 1, f"{name} is greyscale"

    def test_the_primary_and_the_accent_are_different_hues(self) -> None:
        """One colour is a tint. Two related colours are a palette."""
        from samanvaya.pdf_theme import BRASS, NAVY, hue_degrees

        separation = abs(hue_degrees(NAVY) - hue_degrees(BRASS))
        separation = min(separation, 360.0 - separation)
        assert separation > 60.0, "the accent is too close to the primary to read as one"

    def test_paper_is_not_the_only_background(self) -> None:
        """A tint for panels and table banding is what stops a page reading as a dump."""
        from samanvaya.pdf_theme import PAPER, TINT

        assert TINT != PAPER


class TestLegibility:
    def test_every_body_text_colour_meets_aa_on_paper(self) -> None:
        from samanvaya.pdf_theme import BODY_TEXT_COLOURS, PAPER, contrast_ratio

        assert BODY_TEXT_COLOURS, "no body text colours were registered"
        for name, colour in BODY_TEXT_COLOURS.items():
            ratio = contrast_ratio(colour, PAPER)
            assert ratio >= AA_NORMAL, f"{name} is {ratio:.2f}:1 on paper, below AA"

    def test_every_accent_colour_meets_large_text_contrast(self) -> None:
        from samanvaya.pdf_theme import ACCENT_COLOURS, PAPER, contrast_ratio

        assert ACCENT_COLOURS, "no accent colours were registered"
        for name, colour in ACCENT_COLOURS.items():
            ratio = contrast_ratio(colour, PAPER)
            assert ratio >= AA_LARGE, f"{name} is {ratio:.2f}:1 on paper"

    def test_reversed_text_on_the_header_band_is_legible(self) -> None:
        """White on the band, not mid-grey on the band."""
        from samanvaya.pdf_theme import NAVY, PAPER, contrast_ratio

        assert contrast_ratio(PAPER, NAVY) >= AA_NORMAL

    def test_a_hairline_is_lighter_than_body_text(self) -> None:
        """A rule that is as dark as the text competes with it."""
        from samanvaya.pdf_theme import INK, RULE, relative_luminance

        assert relative_luminance(RULE) > relative_luminance(INK)


class TestTheHouseStyleStatesNothing:
    """Palette and chrome are shared. Verdicts are not, and must not leak in here."""

    BANNED = (
        "compliant", "non-compliant", "pass", "fail", "at risk", "safe",
        "violation", "breach of law", "you should", "we recommend",
        "satisfied", "gap", "unresolved",
    )

    def test_the_theme_carries_no_verdict_vocabulary(self) -> None:
        from samanvaya import pdf_theme

        source = inspect.getsource(pdf_theme).lower()
        # Strip comments and docstrings' explanatory prose is not the target: the target
        # is a NAME or a literal in the module's API. Checking identifiers and string
        # literals is enough and does not fight the module's own documentation.
        api = " ".join(n for n in dir(pdf_theme) if not n.startswith("_")).lower()
        literals = " ".join(re.findall(r'"([^"\n]*)"', source))
        surface = f"{api} {literals}".lower()
        for word in self.BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", surface), (
                f"{word!r} reached the shared house style"
            )

    def test_the_theme_does_not_import_either_renderer(self) -> None:
        """The house style is a dependency of both documents, never the reverse."""
        from samanvaya import pdf_theme

        source = inspect.getsource(pdf_theme)
        assert "from samanvaya.pdf_report" not in source
        assert "from samanvaya.questionnaire" not in source
        assert "import samanvaya.report" not in source


class TestTheSanitiser:
    """One sanitiser, not one per renderer.

    There were two, and they disagreed: the report mapped U+00B7 and the questionnaire
    did not, so the same middle dot survived one document and was replaced by a
    substitution mark in the other. A shared house style is the place that stops.
    """

    def test_it_maps_the_typographic_characters_legal_text_actually_contains(self) -> None:
        from samanvaya.pdf_theme import latin1

        for source, expected in (
            ("—", "-"), ("–", "-"),
            ("‘", "'"), ("’", "'"),
            ("“", '"'), ("”", '"'),
            ("·", "."), ("…", "..."),
            (" ", " "),
        ):
            assert latin1(source) == expected, f"U+{ord(source):04X} was not mapped"

    def test_it_never_raises_on_a_character_it_cannot_draw(self) -> None:
        """Devanagari is in this tool's own name. It must degrade, not explode."""
        from samanvaya.pdf_theme import latin1

        assert latin1("समन्वय") is not None
        assert latin1("") == ""

    def test_neither_renderer_keeps_a_private_second_sanitiser(self) -> None:
        from samanvaya import pdf_report, questionnaire

        for module in (pdf_report, questionnaire):
            source = inspect.getsource(module)
            assert "encode(\"latin-1\"" not in source and "encode('latin-1'" not in source, (
                f"{module.__name__} still sanitises on its own"
            )


class TestThePreparerIsTheOneSharedLetterhead:
    def test_the_report_exposes_the_shared_preparer(self) -> None:
        """Existing callers import Preparer from pdf_report. That must keep working."""
        from samanvaya import pdf_report, pdf_theme

        assert pdf_report.Preparer is pdf_theme.Preparer

    def test_the_questionnaire_uses_the_same_class(self) -> None:
        from samanvaya import pdf_theme, questionnaire

        assert questionnaire.Preparer is pdf_theme.Preparer

    def test_there_is_exactly_one_letterhead_store(self) -> None:
        """Two stores would let the two documents name different firms."""
        from samanvaya.pdf_theme import Preparer

        assert hasattr(Preparer, "save") and hasattr(Preparer, "load")


class TestTheWordmark:
    def test_the_wordmark_is_the_product_name(self) -> None:
        from samanvaya.pdf_theme import WORDMARK

        assert "samanvaya" in WORDMARK.replace(" ", "").lower()

    def test_the_wordmark_is_drawable_with_a_core_font(self) -> None:
        """The Devanagari form cannot be drawn without an embedded font, and this
        build ships core fonts only. If the wordmark ever needs the script, it needs
        a font first — silently substituting question marks is not the compromise."""
        from samanvaya.pdf_theme import WORDMARK, latin1

        assert latin1(WORDMARK) == WORDMARK


class TestNothingIsDrawnPastTheMargin:
    """Added after a defect the content-model tests could not see.

    Every step of the questionnaire's "what to do with this form" list was drawn 6mm
    further right than the one above it, because ``multi_cell`` returns the cursor to
    the left edge of the CELL and not to the left margin, and each iteration then
    measured its width from there. The third step ran off the right edge of the paper.

    Every test in the suite passed. The PDF opened. The text was in the extracted
    content. Only a bounding box told the truth — which is the same lesson the row
    geometry tests learned, arriving through a different door.

    So: spy on the two calls that place text, and assert that none of them is asked to
    draw outside the page. This is cheap, needs no external tool, and would have caught
    the defect on the first run.
    """

    def _widest_overrun(self, render) -> float:
        """Return how far past the right margin the worst draw call reached, in mm."""
        from fpdf import FPDF

        worst = 0.0
        original_cell = FPDF.cell
        original_multi = FPDF.multi_cell

        def check(pdf: FPDF, width: float) -> None:
            nonlocal worst
            # `0` is fpdf2's "extend to the right margin" and can never overrun.
            if width <= 0:
                return
            overrun = (pdf.get_x() + width) - (pdf.w - pdf.r_margin)
            worst = max(worst, overrun)

        def spy_cell(self, w=0, *args, **kwargs):  # type: ignore[no-untyped-def]
            check(self, float(w or 0))
            return original_cell(self, w, *args, **kwargs)

        def spy_multi(self, w=0, *args, **kwargs):  # type: ignore[no-untyped-def]
            if not kwargs.get("dry_run"):
                check(self, float(w or 0))
            return original_multi(self, w, *args, **kwargs)

        FPDF.cell = spy_cell  # type: ignore[method-assign]
        FPDF.multi_cell = spy_multi  # type: ignore[method-assign]
        try:
            render()
        finally:
            FPDF.cell = original_cell  # type: ignore[method-assign]
            FPDF.multi_cell = original_multi  # type: ignore[method-assign]
        return worst

    def test_the_questionnaire_stays_inside_the_page(self, tmp_path) -> None:
        from samanvaya.pdf_theme import Preparer
        from samanvaya.questionnaire import render_questionnaire

        preparer = Preparer(firm="Example & Co, Advocates", adviser="A. Adviser")
        worst = self._widest_overrun(
            lambda: render_questionnaire(tmp_path / "q.pdf", preparer)
        )
        assert worst <= 0.5, f"a draw call reached {worst:.1f}mm past the right margin"

    def test_the_report_stays_inside_the_page(self, tmp_path) -> None:
        from datetime import date
        from pathlib import Path

        from samanvaya.declaration import load
        from samanvaya.engine import run
        from samanvaya.pdf_report import render_pdf
        from samanvaya.pdf_theme import Preparer

        examples = Path(__file__).resolve().parents[1] / "examples"
        result = run(load(examples / "02-eu-uk-ecommerce.json"), date(2027, 12, 1))
        preparer = Preparer(firm="Example & Co, Advocates", adviser="A. Adviser")
        worst = self._widest_overrun(
            lambda: render_pdf(result, tmp_path / "r.pdf", preparer)
        )
        assert worst <= 0.5, f"a draw call reached {worst:.1f}mm past the right margin"
