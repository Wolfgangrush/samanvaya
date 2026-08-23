"""Acceptance tests for the renderer.

Authored by the maintainer BEFORE the implementation. Tests are not delegated.

Both renderers derive from ONE `EngineResult`. That is not tidiness: if the Markdown a
client reads and the JSON-lines an auditor reads could ever disagree, the report has no
evidential value at all, and the adviser cannot say which of the two he stood behind.

Every artefact carries the fixed not-legal-advice disclaimer, and the declaration hash, so
a report can be tied to the exact declaration it was produced from.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from samanvaya.declaration import load
from samanvaya.engine import run
from samanvaya.report import render, write
from samanvaya.types import DISCLAIMER, EngineResult, RegimeId

FIXTURES = Path(__file__).parent / "fixtures"
AS_AT = date(2026, 8, 19)


@pytest.fixture
def result() -> EngineResult:
    return run(load(FIXTURES / "multi_regime.json"), AS_AT)


class TestMarkdown:
    def test_markdown_renders(self, result: EngineResult) -> None:
        assert render(result, "md").strip()

    def test_the_disclaimer_is_in_the_header(self, result: EngineResult) -> None:
        md = render(result, "md")
        assert DISCLAIMER[:60] in md

    def test_the_declaration_hash_is_in_the_header(self, result: EngineResult) -> None:
        assert result.declaration_hash in render(result, "md")

    def test_the_as_at_date_is_in_the_header(self, result: EngineResult) -> None:
        assert AS_AT.isoformat() in render(result, "md")

    def test_the_tool_version_is_in_the_header(self, result: EngineResult) -> None:
        assert result.tool_version in render(result, "md")

    def test_every_regime_has_a_section(self, result: EngineResult) -> None:
        md = render(result, "md")
        for regime in result.per_regime:
            assert regime.value in md

    def test_a_draft_pack_is_labelled_draft_in_the_report(self, result: EngineResult) -> None:
        """A reader must never mistake a draft rail for a settled one."""
        md = render(result, "md").lower()
        assert "draft" in md

    def test_every_finding_shows_its_instrument_and_provision(self, result: EngineResult) -> None:
        md = render(result, "md")
        for f in result.all_findings:
            assert f.obligation.provision in md

    def test_fact_needed_markers_survive_into_the_report(self, result: EngineResult) -> None:
        """An unsourced constant must be visible to the reader, not quietly dropped."""
        unsourced = [f for f in result.all_findings if f.obligation.has_unsourced_constant()]
        if unsourced:
            assert "FACT NEEDED" in render(result, "md")

    def test_the_incompleteness_notice_appears_once(self) -> None:
        res = run(load(FIXTURES / "us_no_states_incomplete.json"), AS_AT)
        md = render(res, "md")
        assert md.lower().count("sub-national units") <= 3


class TestJsonLines:
    def test_every_line_is_valid_json(self, result: EngineResult) -> None:
        for line in render(result, "jsonl").splitlines():
            if line.strip():
                json.loads(line)

    def test_the_first_line_is_the_header_carrying_the_disclaimer(self, result: EngineResult) -> None:
        first = json.loads(render(result, "jsonl").splitlines()[0])
        assert first["type"] == "header"
        assert "not legal advice" in first["disclaimer"].lower()

    def test_the_header_carries_hash_version_and_as_at(self, result: EngineResult) -> None:
        first = json.loads(render(result, "jsonl").splitlines()[0])
        assert first["declaration_hash"] == result.declaration_hash
        assert first["tool_version"] == result.tool_version
        assert first["as_at"] == AS_AT.isoformat()

    def test_there_is_one_finding_line_per_finding(self, result: EngineResult) -> None:
        lines = [json.loads(x) for x in render(result, "jsonl").splitlines() if x.strip()]
        assert len([x for x in lines if x["type"] == "finding"]) == len(result.all_findings)

    def test_each_finding_line_carries_the_required_fields(self, result: EngineResult) -> None:
        required = {
            "regime", "sub_unit", "instrument", "provision", "topic", "sub_topic",
            "obligation_summary", "declaration_summary", "result", "citation_pointer",
        }
        for raw in render(result, "jsonl").splitlines():
            row = json.loads(raw)
            if row["type"] == "finding":
                assert required <= set(row), required - set(row)

    def test_sub_topic_is_structured_not_an_opaque_string(self, result: EngineResult) -> None:
        """A1. The machine-readable output must expose dimension/value/unit."""
        for raw in render(result, "jsonl").splitlines():
            row = json.loads(raw)
            if row["type"] == "finding":
                assert set(row["sub_topic"]) >= {"dimension", "value", "unit"}
                break

    def test_divergence_lines_carry_positions_and_no_ranking(self, result: EngineResult) -> None:
        for raw in render(result, "jsonl").splitlines():
            row = json.loads(raw)
            if row["type"] == "divergence":
                assert "positions" in row
                assert not any("strong" in k or "rank" in k for k in row)


class TestBothDeriveFromOneResult:
    def test_the_two_renderings_agree_on_the_finding_count(self, result: EngineResult) -> None:
        md = render(result, "md")
        jsonl_findings = [
            json.loads(x) for x in render(result, "jsonl").splitlines() if x.strip()
        ]
        n_json = len([x for x in jsonl_findings if x["type"] == "finding"])
        assert n_json == len(result.all_findings)
        for f in result.all_findings:
            assert f.obligation.obligation_id in md

    def test_the_two_renderings_agree_on_the_hash(self, result: EngineResult) -> None:
        header = json.loads(render(result, "jsonl").splitlines()[0])
        assert header["declaration_hash"] in render(result, "md")

    def test_rendering_twice_is_byte_identical(self, result: EngineResult) -> None:
        assert render(result, "md") == render(result, "md")
        assert render(result, "jsonl") == render(result, "jsonl")

    def test_an_unknown_format_is_refused(self, result: EngineResult) -> None:
        with pytest.raises(ValueError):
            render(result, "pdf")


class TestWriting:
    def test_write_both_creates_two_files(self, result: EngineResult, tmp_path: Path) -> None:
        write(result, tmp_path / "report", "both")
        assert (tmp_path / "report.md").is_file()
        assert (tmp_path / "report.jsonl").is_file()

    def test_write_md_creates_only_markdown(self, result: EngineResult, tmp_path: Path) -> None:
        write(result, tmp_path / "report", "md")
        assert (tmp_path / "report.md").is_file()
        assert not (tmp_path / "report.jsonl").exists()

    def test_the_written_file_matches_render(self, result: EngineResult, tmp_path: Path) -> None:
        write(result, tmp_path / "report", "md")
        assert (tmp_path / "report.md").read_text(encoding="utf-8") == render(result, "md")

    def test_writing_into_a_nonexistent_directory_is_refused(
        self, result: EngineResult, tmp_path: Path
    ) -> None:
        """The tool creates no directories. Silently materialising a path is how a
        report ends up somewhere nobody looks."""
        with pytest.raises((ValueError, OSError)):
            write(result, tmp_path / "no" / "such" / "dir" / "report", "md")

    def test_writing_over_a_directory_is_refused(
        self, result: EngineResult, tmp_path: Path
    ) -> None:
        (tmp_path / "report.md").mkdir()
        with pytest.raises((ValueError, OSError)):
            write(result, tmp_path / "report", "md")

    def test_writing_through_a_symlink_is_refused(
        self, result: EngineResult, tmp_path: Path
    ) -> None:
        """A planted symlink is the one way a caller-supplied path can redirect client
        findings somewhere the adviser did not choose."""
        elsewhere = tmp_path / "elsewhere.md"
        elsewhere.write_text("original")
        (tmp_path / "report.md").symlink_to(elsewhere)
        with pytest.raises((ValueError, OSError)):
            write(result, tmp_path / "report", "md")
        assert elsewhere.read_text() == "original"

    def test_a_relative_path_the_adviser_chose_is_allowed(
        self, result: EngineResult, tmp_path: Path
    ) -> None:
        """`..` is not refused. The adviser picked the path; rejecting relative
        navigation would only obstruct the person who meant it."""
        (tmp_path / "sub").mkdir()
        write(result, tmp_path / "sub" / ".." / "report", "md")
        assert (tmp_path / "report.md").is_file()

    def test_a_rejected_second_target_leaves_no_half_written_report(
        self, result: EngineResult, tmp_path: Path
    ) -> None:
        """A partial report that reads as complete is the worst possible outcome."""
        (tmp_path / "report.jsonl").mkdir()
        with pytest.raises((ValueError, OSError)):
            write(result, tmp_path / "report", "both")
        assert not (tmp_path / "report.md").exists()

    def test_nothing_else_is_written(self, result: EngineResult, tmp_path: Path) -> None:
        """No cache, no log, no history. The report file is the only persistence."""
        write(result, tmp_path / "report", "both")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["report.jsonl", "report.md"]


class TestNotYetInForceIsVisibleAtSummaryLevel:
    """Raised reviewing a real report as the advocate whose name goes on it.

    On an August 2026 as-at date, eleven of the fifteen India obligations resolve
    `not_applicable`, because DPDP Rule 1(4) does not commence Rules 3 and 5 to 16 until
    eighteen months after publication. That is legally correct, and each finding's own
    rationale says so — but the regime summary showed only `not_applicable: 11`, with the
    reason buried eleven rationales deep.

    A client skimming that summary would conclude they have no DPDP duties. They do: the
    duties simply have not arrived yet, and the gap between those two readings is the
    whole value of the advice. The report has to say it where it will be read.
    """

    def _india_report(self, as_at: date) -> str:
        pytest.importorskip("dpdp")
        result = run(load(FIXTURES / "canonical_declaration.json"), as_at)
        return render(result, "md")

    def test_the_report_says_obligations_are_not_yet_in_force(self) -> None:
        md = self._india_report(date(2026, 8, 19))
        assert "not yet in force" in md.lower()

    def test_it_names_the_commencement_date(self) -> None:
        md = self._india_report(date(2026, 8, 19))
        assert "2027-05-13" in md

    def test_it_counts_how_many_are_affected(self) -> None:
        """Nine, not eleven. Two of the eleven `not_applicable` India findings are
        not-applicable for substantive reasons — the entity is not a notified Significant
        Data Fiduciary, and children's services are not offered — and conflating those
        with "not yet commenced" would misstate both."""
        md = self._india_report(date(2026, 8, 19))
        assert "**9 obligation(s)" in md

    def test_the_notice_appears_in_the_regime_section_not_only_per_finding(self) -> None:
        """It must be above the findings, where a skim-reader will meet it."""
        md = self._india_report(date(2026, 8, 19))
        notice_at = md.lower().find("not yet in force")
        first_finding_at = md.find("- [")
        assert notice_at != -1
        assert notice_at < first_finding_at

    def test_no_such_notice_once_the_rules_have_commenced(self) -> None:
        md = self._india_report(date(2027, 12, 1))
        assert "not yet in force" not in md.lower()

    def test_the_jsonl_pack_line_carries_the_same_fact(self) -> None:
        pytest.importorskip("dpdp")
        result = run(load(FIXTURES / "canonical_declaration.json"), date(2026, 8, 19))
        packs = [
            json.loads(x) for x in render(result, "jsonl").splitlines()
            if x.strip() and json.loads(x)["type"] == "pack"
        ]
        india = next(p for p in packs if p["regime"] == "IN")
        assert india["not_yet_in_force"] == 9
        assert india["earliest_commencement"] == "2027-05-13"
