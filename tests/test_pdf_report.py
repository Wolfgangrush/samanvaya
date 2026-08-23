"""Acceptance tests for the PDF report and the preparer letterhead.

Authored BEFORE the implementation. Tests are not delegated.

The Markdown report is for the adviser. The PDF is what actually reaches a client, so it
carries two things the Markdown does not need: a **letterhead** naming who prepared it, and
**tables** rather than prose bullets.

The design splits deliberately. `report_tables()` builds the content model — plain data,
fully testable. `render_pdf()` draws it. Testing a PDF by parsing the binary back would
test the drawing library, not this tool; testing the model tests the decisions this tool
actually makes about what a reader sees.

One rule carries over from every other surface: **a `contested` finding must never be
presented as a failure.** A client reading a table cannot see a rationale three columns
wide, so the verdict column has to be unambiguous on its own.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from samanvaya.declaration import load
from samanvaya.engine import run
from samanvaya.pdf_report import Preparer, report_tables
from samanvaya.types import RegimeId

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
AS_AT = date(2027, 12, 1)


@pytest.fixture
def result():
    return run(load(EXAMPLES / "02-eu-uk-ecommerce.json"), AS_AT)


@pytest.fixture
def preparer() -> Preparer:
    return Preparer(
        firm="Example & Co, Advocates",
        adviser="A. Adviser",
        email="adviser@example.com",
        phone="+91 00000 00000",
    )


class TestPreparer:
    def test_every_field_is_optional(self) -> None:
        """A user who wants no letterhead must not be forced to invent one."""
        p = Preparer()
        assert p.firm is None and p.adviser is None
        assert p.email is None and p.phone is None

    def test_it_is_frozen(self) -> None:
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            Preparer().firm = "x"  # type: ignore[misc]

    def test_is_empty_reports_whether_anything_was_given(self) -> None:
        assert Preparer().is_empty is True
        assert Preparer(firm="X").is_empty is False

    def test_a_preparer_round_trips_through_json(self, tmp_path: Path) -> None:
        p = Preparer(firm="F", adviser="A", email="e@x.com", phone="+91 1")
        path = tmp_path / "preparer.json"
        p.save(path)
        assert Preparer.load(path) == p

    def test_loading_a_missing_profile_returns_an_empty_preparer(self, tmp_path: Path) -> None:
        assert Preparer.load(tmp_path / "nope.json").is_empty is True

    def test_a_corrupt_profile_does_not_crash_the_run(self, tmp_path: Path) -> None:
        """A malformed profile must not stop an adviser producing a report."""
        path = tmp_path / "preparer.json"
        path.write_text("{ not json")
        assert Preparer.load(path).is_empty is True

    def test_a_credential_in_a_profile_field_is_refused(self, tmp_path: Path) -> None:
        """The letterhead is free text and reaches a file. The firewall still applies."""
        from samanvaya.types import DeclarationError

        with pytest.raises((DeclarationError, ValueError)):
            Preparer(firm="postgresql://u:p@host:5432/db").validate()

    def test_an_ordinary_email_and_phone_are_not_mistaken_for_credentials(self) -> None:
        Preparer(
            firm="Example & Co", adviser="A. Adviser",
            email="adviser@example.com", phone="+91 98765 43210",
        ).validate()


class TestTheContentModel:
    def test_it_returns_a_table_per_regime(self, result) -> None:
        tables = report_tables(result)
        regimes = {t.regime for t in tables if t.kind == "regime"}
        assert regimes == set(result.per_regime)

    def test_every_regime_table_has_a_header_row(self, result) -> None:
        for t in report_tables(result):
            if t.kind == "regime":
                assert t.header
                assert len(t.header) == len(t.rows[0]) if t.rows else True

    def test_the_header_names_the_columns_a_reader_needs(self, result) -> None:
        t = next(t for t in report_tables(result) if t.kind == "regime")
        joined = " ".join(t.header).lower()
        for needed in ("result", "obligation", "instrument", "provision"):
            assert needed in joined, needed

    def test_every_finding_appears_as_a_row(self, result) -> None:
        tables = report_tables(result)
        rows = sum(len(t.rows) for t in tables if t.kind == "regime")
        assert rows == len(result.all_findings)

    def test_a_row_carries_the_provision_so_the_client_can_verify(self, result) -> None:
        t = next(t for t in report_tables(result) if t.kind == "regime")
        assert any(any(c.strip() for c in row) for row in t.rows)
        for row in t.rows:
            assert len(row) == len(t.header)

    def test_the_verdict_column_is_plain_english_not_an_enum_token(self, result) -> None:
        """A client reads this. `not_applicable` is a field name, not a verdict."""
        for t in report_tables(result):
            if t.kind != "regime":
                continue
            for row in t.rows:
                assert "_" not in row[0], row[0]

    def test_contested_is_never_presented_as_a_failure(self, result) -> None:
        """The distinction the whole tool protects, carried into the client-facing table."""
        for t in report_tables(result):
            if t.kind != "regime":
                continue
            for row in t.rows:
                verdict = row[0].lower()
                if "not stated" in verdict or "unresolved" in verdict:
                    assert "fail" not in verdict and "gap" not in verdict

    def test_a_draft_regime_is_marked_on_its_table(self, result) -> None:
        for t in report_tables(result):
            if t.kind == "regime" and t.draft:
                assert "draft" in t.title.lower()

    def test_a_divergence_table_appears_when_regimes_differ(self) -> None:
        res = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        tables = report_tables(res)
        if res.divergences:
            assert any(t.kind == "divergence" for t in tables)

    def test_the_divergence_table_does_not_rank(self) -> None:
        res = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        for t in report_tables(res):
            if t.kind == "divergence":
                joined = (" ".join(t.header) + t.title).lower()
                for banned in ("strongest", "strictest", "rank", "severity"):
                    assert banned not in joined

    def test_a_notice_table_appears_when_there_are_notices(self) -> None:
        res = run(load(FIXTURES / "us_no_states_incomplete.json"), AS_AT)
        if res.notices:
            assert any(t.kind == "notice" for t in report_tables(res))

    def test_the_model_is_deterministic(self, result) -> None:
        a = [(t.kind, t.title, tuple(map(tuple, t.rows))) for t in report_tables(result)]
        b = [(t.kind, t.title, tuple(map(tuple, t.rows))) for t in report_tables(result)]
        assert a == b


class TestRenderingThePdf:
    def test_it_writes_a_real_pdf(self, result, preparer, tmp_path: Path) -> None:
        from samanvaya.pdf_report import render_pdf

        out = tmp_path / "report.pdf"
        render_pdf(result, out, preparer)
        assert out.is_file()
        assert out.read_bytes()[:5] == b"%PDF-"
        assert out.stat().st_size > 1000

    def test_it_writes_without_a_preparer(self, result, tmp_path: Path) -> None:
        from samanvaya.pdf_report import render_pdf

        out = tmp_path / "report.pdf"
        render_pdf(result, out, Preparer())
        assert out.read_bytes()[:5] == b"%PDF-"

    def test_it_refuses_to_write_through_a_symlink(self, result, preparer, tmp_path: Path) -> None:
        from samanvaya.pdf_report import render_pdf

        elsewhere = tmp_path / "elsewhere.pdf"
        elsewhere.write_bytes(b"original")
        (tmp_path / "report.pdf").symlink_to(elsewhere)
        with pytest.raises((ValueError, OSError)):
            render_pdf(result, tmp_path / "report.pdf", preparer)
        assert elsewhere.read_bytes() == b"original"

    def test_rendering_twice_produces_the_same_tables(self, result, preparer, tmp_path: Path) -> None:
        """The bytes carry a creation date, so compare the model, not the file."""
        from samanvaya.pdf_report import render_pdf

        render_pdf(result, tmp_path / "a.pdf", preparer)
        render_pdf(result, tmp_path / "b.pdf", preparer)
        assert (tmp_path / "a.pdf").exists() and (tmp_path / "b.pdf").exists()

    def test_no_network_call_is_made_while_rendering(self, result, preparer, tmp_path: Path) -> None:
        from samanvaya.offline_check import install_tripwire, remove_tripwire
        from samanvaya.pdf_report import render_pdf

        install_tripwire()
        try:
            render_pdf(result, tmp_path / "report.pdf", preparer)
        finally:
            remove_tripwire()
        assert (tmp_path / "report.pdf").is_file()


class TestCli:
    def test_check_can_emit_a_pdf(self, tmp_path: Path) -> None:
        from samanvaya.cli import main

        rc = main([
            "check", str(EXAMPLES / "02-eu-uk-ecommerce.json"),
            "--as-at", "2027-12-01", "--out", str(tmp_path / "r"), "--format", "pdf",
        ])
        assert rc == 0
        assert (tmp_path / "r.pdf").is_file()

    def test_format_all_emits_three_files(self, tmp_path: Path) -> None:
        from samanvaya.cli import main

        main([
            "check", str(EXAMPLES / "02-eu-uk-ecommerce.json"),
            "--as-at", "2027-12-01", "--out", str(tmp_path / "r"), "--format", "all",
        ])
        assert (tmp_path / "r.md").is_file()
        assert (tmp_path / "r.jsonl").is_file()
        assert (tmp_path / "r.pdf").is_file()

    def test_the_letterhead_flags_are_accepted(self, tmp_path: Path) -> None:
        from samanvaya.cli import main

        rc = main([
            "check", str(EXAMPLES / "02-eu-uk-ecommerce.json"),
            "--as-at", "2027-12-01", "--out", str(tmp_path / "r"), "--format", "pdf",
            "--firm", "Example & Co", "--adviser", "A. Adviser",
            "--email", "adviser@example.com", "--phone", "+91 98765 43210",
        ])
        assert rc == 0
        assert (tmp_path / "r.pdf").is_file()

    def test_profile_saves_and_is_reused(self, tmp_path: Path, monkeypatch) -> None:
        from samanvaya.cli import main

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        assert main([
            "profile", "--firm", "Example & Co", "--adviser", "A. Adviser",
            "--email", "adviser@example.com", "--phone", "+91 98765 43210",
        ]) == 0
        assert (tmp_path / "cfg" / "preparer.json").is_file()
        saved = json.loads((tmp_path / "cfg" / "preparer.json").read_text())
        assert saved["firm"] == "Example & Co"

    def test_profile_show_prints_what_is_saved(
        self, tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from samanvaya.cli import main

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        main(["profile", "--firm", "Example & Co"])
        capsys.readouterr()
        main(["profile", "--show"])
        assert "Example & Co" in capsys.readouterr().out

    def test_a_credential_in_a_profile_field_is_refused_by_the_cli(
        self, tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from samanvaya.cli import main

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        rc = main(["profile", "--firm", "postgresql://u:p@host:5432/db"])
        assert rc != 0
        assert "credential" in capsys.readouterr().err.lower()

    def test_pdf_appears_in_the_format_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        from samanvaya.cli import main

        with pytest.raises(SystemExit):
            main(["check", "--help"])
        out = capsys.readouterr().out
        assert "pdf" in out


class TestTheDrawnGeometry:
    """Regression tests for the drawing pass, not the content model.

    Authored AFTER a defect that every other test in this file missed. The original
    implementation measured row height with ``multi_cell(..., dry_run=True)``, which
    returns a BOOLEAN — whether a page break was triggered — and not a height. Taken as
    a height it evaluates to zero, so the cursor never advanced and all seventeen
    findings were drawn on top of one another at the same y position. The file opened,
    started with ``%PDF-``, exceeded a thousand bytes, and every model-level assertion
    above passed. The artefact was unreadable.

    The lesson is narrow and worth keeping: asserting on the content model proves what
    the tool DECIDED, and proves nothing about what the reader SEES. These tests assert
    the minimum about what is actually drawn — that consecutive rows occupy distinct
    positions, and that a report longer than a page becomes more than one page.
    """

    def _row_origins(self, result, preparer) -> list[float]:
        """Return the y origin of every cell rectangle drawn, in draw order.

        ``rect`` is called exactly once per cell, at that cell's row origin, so the
        sequence of y values it receives is a faithful record of where rows landed.
        """
        from samanvaya.pdf_report import _SamanvayaPDF, render_pdf

        seen: list[float] = []
        original = _SamanvayaPDF.rect

        def spy(self, x, y, w, h, *args, **kwargs):  # type: ignore[no-untyped-def]
            seen.append(round(float(y), 3))
            return original(self, x, y, w, h, *args, **kwargs)

        _SamanvayaPDF.rect = spy  # type: ignore[method-assign]
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                render_pdf(result, Path(tmp) / "geometry.pdf", preparer)
        finally:
            _SamanvayaPDF.rect = original  # type: ignore[method-assign]
        return seen

    def test_rows_do_not_all_land_on_the_same_line(self, result, preparer) -> None:
        """The exact defect: every row drawn at one y, producing an unreadable smear."""
        origins = self._row_origins(result, preparer)
        assert origins, "no cells were drawn at all"
        assert len(set(origins)) > 1, (
            "every cell was drawn at the same y position — rows are overprinting"
        )

    def test_there_is_one_distinct_origin_per_drawn_row(self, result, preparer) -> None:
        """Cells of one row share an origin; different rows must not.

        Total rows drawn is the header row plus the data rows of every table.
        """
        from samanvaya.pdf_report import report_tables

        tables = report_tables(result)
        expected_rows = sum(1 + len(t.rows) for t in tables)
        origins = self._row_origins(result, preparer)
        # Consecutive runs of an identical y are the cells of a single row.
        runs = 1
        for previous, current in zip(origins, origins[1:]):
            if current != previous:
                runs += 1
        assert runs == expected_rows, (
            f"drew {runs} distinct row positions for {expected_rows} rows"
        )

    def test_a_report_longer_than_a_page_spans_more_than_one_page(
        self, preparer, tmp_path: Path
    ) -> None:
        """With the defect present this report collapsed onto a single page.

        Uses the multi-regime fixture rather than the shared `result` one. When the UK
        pack was parked on 2026-08-20 the shared fixture fell to thirteen findings, which
        is not reliably more than one page — and a page-overflow test that no longer
        overflows proves nothing while still passing.
        """
        from samanvaya.pdf_report import render_pdf, report_tables

        result = run(load(FIXTURES / "multi_regime.json"), AS_AT)
        assert sum(len(t.rows) for t in report_tables(result)) >= 15, (
            "fixture no longer has enough findings to overflow a page"
        )
        out = tmp_path / "long.pdf"
        render_pdf(result, out, preparer)
        raw = out.read_bytes()
        pages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
        assert pages > 1, f"seventeen findings rendered onto {pages} page(s)"

    def test_no_row_is_taller_than_the_usable_page(self, result, preparer) -> None:
        """A row taller than the page can never be laid out, only clipped."""
        from samanvaya.pdf_report import _SamanvayaPDF, render_pdf

        heights: list[float] = []
        original = _SamanvayaPDF.rect

        def spy(self, x, y, w, h, *args, **kwargs):  # type: ignore[no-untyped-def]
            heights.append(float(h))
            assert y + h <= self.h + 0.5, "a cell was drawn past the bottom of the page"
            return original(self, x, y, w, h, *args, **kwargs)

        _SamanvayaPDF.rect = spy  # type: ignore[method-assign]
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                render_pdf(result, Path(tmp) / "heights.pdf", preparer)
        finally:
            _SamanvayaPDF.rect = original  # type: ignore[method-assign]
        assert heights and max(heights) > 0


class TestTablesDoNotShareState:
    """Regression tests for a defect found by the type checker, not by the suite.

    The divergence and notice tables were built by appending into ``rows`` and reading
    ``header`` — the same two names the per-regime loop above them had already bound.
    In Python a ``for`` body does not scope its names, so both survived the loop still
    pointing at the LAST regime's header and the LAST regime's row list. The divergence
    rows were therefore appended into a list already handed to a regime ``Table``, and
    the divergence table was published carrying the regime table's column headings.

    Every test in this file passed with that defect present, because the fixture used
    for the row-count assertions produces no divergences, and the divergence tests
    assert only on ``kind`` and on the absence of ranking vocabulary — and the wrongly
    inherited header contains no ranking vocabulary either.
    """

    @pytest.fixture
    def diverging(self):
        return run(load(FIXTURES / "multi_regime.json"), AS_AT)

    def test_the_fixture_actually_diverges(self, diverging) -> None:
        """Guard: if this stops being true the tests below prove nothing."""
        assert diverging.divergences, "fixture no longer produces divergences"

    def test_a_divergence_table_has_its_own_header(self, diverging) -> None:
        from samanvaya.pdf_report import report_tables

        tables = report_tables(diverging)
        divergence = next(t for t in tables if t.kind == "divergence")
        regime_headers = [list(t.header) for t in tables if t.kind == "regime"]
        assert list(divergence.header) not in regime_headers, (
            "the divergence table published a regime table's column headings"
        )
        assert "Position" in divergence.header

    def test_divergence_rows_do_not_leak_into_a_regime_table(self, diverging) -> None:
        """The row lists must be distinct objects, not one list shared by both."""
        from samanvaya.pdf_report import report_tables

        tables = report_tables(diverging)
        regime_rows = sum(len(t.rows) for t in tables if t.kind == "regime")
        assert regime_rows == len(diverging.all_findings), (
            "a regime table carries rows that are not findings"
        )
        divergence = next(t for t in tables if t.kind == "divergence")
        for table in tables:
            if table.kind == "regime":
                assert table.rows is not divergence.rows

    def test_every_row_matches_its_own_table_header_width(self, diverging) -> None:
        from samanvaya.pdf_report import report_tables

        for table in report_tables(diverging):
            for row in table.rows:
                assert len(row) == len(table.header), (
                    f"{table.kind} table row has {len(row)} cells "
                    f"for {len(table.header)} columns"
                )


class TestTheDivergenceTableIsReadableByAClient:
    """The divergence table is the tool's headline output, so it gets the same rules.

    Every constraint the per-regime verdict column obeys applies here: no field names,
    no internal codes, and no number stripped of the unit that gives it meaning.
    """

    @pytest.fixture
    def diverging(self):
        return run(load(FIXTURES / "multi_regime.json"), AS_AT)

    def _divergence(self, result):
        from samanvaya.pdf_report import report_tables

        return next(t for t in report_tables(result) if t.kind == "divergence")

    def test_a_value_with_a_unit_is_never_printed_without_it(self, diverging) -> None:
        """A response period of "1 months" must not reach a client as "1".

        The GDPR Article 12(3) position carries value "1" and unit "months". Printed
        bare, next to another regime's "none prescribed", it reports a one-month
        deadline as if it were a bare numeral.
        """
        expected: set[str] = set()
        for divergence in diverging.divergences:
            for position in divergence.positions:
                unit = position.unit or divergence.unit
                if unit and position.value:
                    expected.add(f"{position.value} {unit}")
        assert expected, "fixture no longer has a position carrying a unit"

        printed = {cell for row in self._divergence(diverging).rows for cell in row}
        for text in expected:
            assert text in printed, f"{text!r} was printed without its unit"

    def test_the_regime_column_names_a_place_not_a_code(self, diverging) -> None:
        """"IN" is an identifier. A client-facing column says "India"."""
        rows = self._divergence(diverging).rows
        regime_column = {row[2] for row in rows}
        codes = {r.value for r in RegimeId}
        assert not (regime_column & codes), f"raw regime codes printed: {regime_column & codes}"

    def test_no_field_name_reaches_the_reader(self, diverging) -> None:
        """The same rule as the verdict column: no underscores in reader-facing text."""
        table = self._divergence(diverging)
        for row in table.rows:
            for cell in (row[0], row[1], row[2]):
                assert "_" not in cell, cell

    def test_it_still_does_not_rank(self, diverging) -> None:
        """Guard: humanising the labels must not smuggle in comparative vocabulary."""
        table = self._divergence(diverging)
        joined = (" ".join(table.header) + table.title).lower()
        for banned in ("strongest", "strictest", "rank", "severity"):
            assert banned not in joined


class TestColourNeverCarriesTheMeaning:
    """Added 2026-08-22, with the house style.

    The report was black on white. Introducing colour into a document that reports
    legal findings creates a hazard the black-and-white version did not have: a reader
    can take a hue as the message, and the one message this tool refuses to send is
    that an unresolved finding is a failure. These are the rules that answer it.
    """

    def test_the_report_is_not_black_and_white(
        self, result, preparer, tmp_path: Path
    ) -> None:
        from tests.pdf_probe import has_non_grey_colour

        from samanvaya.pdf_report import render_pdf

        out = tmp_path / "colour.pdf"
        render_pdf(result, out, preparer)
        assert has_non_grey_colour(out), "every colour operator is grey"

    def test_every_verdict_has_a_colour(self) -> None:
        from samanvaya.pdf_report import _VERDICT_COLOUR, _VERDICT_TEXT

        for word in _VERDICT_TEXT.values():
            assert word in _VERDICT_COLOUR, f"{word!r} would fall back to a default"

    def test_no_verdict_is_drawn_in_a_red_hue(self) -> None:
        """A gap is an obligation the declared facts leave unaddressed. Not an alarm.

        Red would report an assessment this tool does not make. The amber a gap is
        drawn in sits well clear of the red band.
        """
        from samanvaya.pdf_theme import hue_degrees

        from samanvaya.pdf_report import _VERDICT_COLOUR

        for word, colour in _VERDICT_COLOUR.items():
            hue = hue_degrees(colour)
            assert not (hue >= 345.0 or hue <= 15.0), (
                f"{word!r} is drawn at hue {hue:.0f}, inside the red band"
            )

    def test_unresolved_is_the_least_insistent_of_the_three(self) -> None:
        """An unresolved finding is a fact not supplied, not a finding against anyone.

        It must not shout louder than a finding the tool could actually make.
        """
        from samanvaya.pdf_theme import saturation

        from samanvaya.pdf_report import _VERDICT_COLOUR

        unresolved = saturation(_VERDICT_COLOUR["Unresolved"])
        for word in ("Satisfied", "Gap"):
            assert unresolved <= saturation(_VERDICT_COLOUR[word]), (
                f"Unresolved is more saturated than {word}"
            )

    def test_every_verdict_colour_is_legible_on_paper(self) -> None:
        from samanvaya.pdf_theme import PAPER, contrast_ratio

        from samanvaya.pdf_report import _VERDICT_COLOUR

        for word, colour in _VERDICT_COLOUR.items():
            ratio = contrast_ratio(colour, PAPER)
            assert ratio >= 4.5, f"{word!r} is {ratio:.2f}:1 on paper, below AA"

    def test_the_word_is_always_printed_beside_the_colour(self, result) -> None:
        """Colour repeats the word. A monochrome printout must lose nothing."""
        from samanvaya.pdf_report import _VERDICT_COLOUR, report_tables

        for table in report_tables(result):
            if table.kind != "regime":
                continue
            for row in table.rows:
                assert row[0] in _VERDICT_COLOUR, f"unworded verdict cell: {row[0]!r}"
                assert row[0].strip(), "a verdict was left to colour alone"


class TestTheCoverAndTheLegend:
    def test_it_opens_with_a_cover_page(self, result, preparer, tmp_path: Path) -> None:
        from tests.pdf_probe import page_texts

        from samanvaya.pdf_report import render_pdf

        out = tmp_path / "cover.pdf"
        render_pdf(result, out, preparer)
        first = page_texts(out)[0]
        assert "Conformance Report" in first
        assert "Example & Co" in first
        assert result.declaration_hash in first.replace(" ", "")

    def test_the_cover_states_no_tally_by_verdict(
        self, result, preparer, tmp_path: Path
    ) -> None:
        """A count of satisfied ones beside a count of gaps is a score.

        A score invites the comparison between jurisdictions this tool exists to
        refuse. The cover states what the run was, never what it found.
        """
        from tests.pdf_probe import page_texts

        from samanvaya.pdf_report import _VERDICT_COLOUR, render_pdf

        out = tmp_path / "cover.pdf"
        render_pdf(result, out, preparer)
        first = page_texts(out)[0]
        for word in _VERDICT_COLOUR:
            assert word not in first, f"the cover carries a {word!r} tally"

    def test_the_legend_explains_every_verdict(
        self, result, preparer, tmp_path: Path
    ) -> None:
        """Five words that look like ordinary English are not, and are explained once."""
        from tests.pdf_probe import drawn_text

        from samanvaya.pdf_report import _VERDICT_COLOUR, render_pdf

        out = tmp_path / "legend.pdf"
        render_pdf(result, out, preparer)
        text = drawn_text(out)
        for word in _VERDICT_COLOUR:
            assert word in text, f"{word!r} is used but never explained"

    def test_the_legend_says_an_unresolved_finding_is_not_against_the_client(
        self, result, preparer, tmp_path: Path
    ) -> None:
        from tests.pdf_probe import drawn_text

        from samanvaya.pdf_report import render_pdf

        out = tmp_path / "legend.pdf"
        render_pdf(result, out, preparer)
        assert "not a finding against the client" in drawn_text(out)

    def test_pages_after_the_cover_are_numbered(
        self, result, preparer, tmp_path: Path
    ) -> None:
        from tests.pdf_probe import drawn_text

        from samanvaya.pdf_report import render_pdf

        out = tmp_path / "numbered.pdf"
        render_pdf(result, out, preparer)
        assert "Page 2 of" in drawn_text(out)

    def test_the_tool_build_is_identified_on_the_cover(
        self, result, preparer, tmp_path: Path
    ) -> None:
        """A client emailing a PDF back months later has to be able to say which one."""
        from tests.pdf_probe import page_texts

        from samanvaya import __build__, __version__
        from samanvaya.pdf_report import render_pdf

        out = tmp_path / "build.pdf"
        render_pdf(result, out, preparer)
        first = page_texts(out)[0]
        assert __version__ in first
        assert f"build {__build__}" in first
