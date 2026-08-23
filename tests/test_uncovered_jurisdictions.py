"""A declared jurisdiction the tool does not cover must be told to the reader.

Authored BEFORE the implementation.

``JurisdictionResolution.unknown_countries`` has existed since the first version and
carries the docstring *"Country tokens that could not be mapped; never silently
dropped."* Nothing read it. Not the engine, not the Markdown renderer, not the JSON-lines
renderer, not the PDF. The field was computed and thrown away, so the promise in its own
docstring was false: a declaration naming Brazil produced a report that said nothing
whatsoever about Brazil.

Why that is the worst possible failure for this particular tool. An adviser reads a
conformance report to find out where an organisation stands. A regime that is ABSENT from
the report is indistinguishable, to the eye, from a regime with nothing to report. Silence
reads as a clean bill. The tool's entire discipline is that it refuses to guess and says
so out loud — ``contested`` exists precisely so that "I cannot tell" is never rendered as
"you are fine". An uncovered jurisdiction is the same problem one level up, and it was the
one place the discipline was not applied.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from samanvaya.declaration import load
from samanvaya.engine import run
from samanvaya.types import Declaration, JurisdictionRef, Organisation

FIXTURES = Path(__file__).parent / "fixtures"
AS_AT = date(2027, 12, 1)


def _declaration(*countries: str) -> Declaration:
    return Declaration(
        schema_version="1.0",
        organisation=Organisation(legal_name="Example Organisation Ltd"),
        jurisdictions=tuple(
            JurisdictionRef(country=c, sub_units=(), sub_units_complete=True)
            for c in countries
        ),
        declaration_author="A. Adviser",
    )


class TestAnUncoveredCountryIsReported:
    def test_a_country_with_no_pack_produces_a_notice(self) -> None:
        """Brazil is a real place with a real privacy statute and no pack here."""
        result = run(_declaration("BR"), AS_AT)
        countries = {n.country for n in result.notices}
        assert any("BR" in c or "Brazil" in c for c in countries), (
            f"no notice named the uncovered country; notices were {countries}"
        )

    def test_the_notice_says_the_jurisdiction_was_not_assessed(self) -> None:
        result = run(_declaration("BR"), AS_AT)
        text = " ".join(n.message for n in result.notices).lower()
        assert "not assessed" in text or "no coverage" in text or "not covered" in text, (
            "the notice does not tell the reader the jurisdiction went unassessed"
        )

    def test_an_unrecognisable_token_is_also_reported(self) -> None:
        """A typo must not vanish. 'Wakanda' stands in for 'Untied Kingdom'."""
        result = run(_declaration("Wakanda"), AS_AT)
        assert result.notices, "an unmappable country token produced no notice at all"

    def test_a_covered_country_produces_no_such_notice(self) -> None:
        """Guard: the notice must fire on uncovered countries, not on every run."""
        result = run(_declaration("IN"), AS_AT)
        text = " ".join(n.message for n in result.notices).lower()
        assert "not assessed" not in text and "no coverage" not in text

    def test_a_mixed_declaration_still_assesses_the_covered_country(self) -> None:
        """An uncovered country must not suppress the rest of the report."""
        result = run(_declaration("IN", "BR"), AS_AT)
        assert result.per_regime, "declaring an uncovered country killed the whole run"
        text = " ".join(n.message for n in result.notices).lower()
        assert "not assessed" in text or "no coverage" in text or "not covered" in text

    def test_every_uncovered_country_is_named_not_just_the_first(self) -> None:
        result = run(_declaration("BR", "JP"), AS_AT)
        joined = " ".join(f"{n.country} {n.message}" for n in result.notices)
        for token in ("BR", "JP"):
            assert token in joined, f"{token} was dropped"

    def test_the_notices_are_deterministic(self) -> None:
        a = [(n.country, n.message) for n in run(_declaration("BR", "JP"), AS_AT).notices]
        b = [(n.country, n.message) for n in run(_declaration("BR", "JP"), AS_AT).notices]
        assert a == b


class TestTheNoticeReachesEverySurface:
    def test_it_reaches_the_markdown_report(self, tmp_path: Path) -> None:
        from samanvaya.report import render

        text = render(run(_declaration("IN", "BR"), AS_AT), "md").lower()
        assert "br" in text
        assert "not assessed" in text or "no coverage" in text or "not covered" in text

    def test_it_reaches_the_jsonl_report(self) -> None:
        from samanvaya.report import render

        lines = [
            json.loads(line)
            for line in render(run(_declaration("IN", "BR"), AS_AT), "jsonl").splitlines()
            if line.strip()
        ]
        assert any(
            "BR" in json.dumps(obj) and obj.get("type", "") == "notice" for obj in lines
        ), "no notice record for the uncovered country in the JSON-lines output"

    def test_it_reaches_the_pdf_notice_table(self) -> None:
        from samanvaya.pdf_report import report_tables

        tables = report_tables(run(_declaration("IN", "BR"), AS_AT))
        notice = [t for t in tables if t.kind == "notice"]
        assert notice, "the PDF carries no notice table for an uncovered jurisdiction"
        joined = " ".join(cell for t in notice for row in t.rows for cell in row)
        assert "BR" in joined
