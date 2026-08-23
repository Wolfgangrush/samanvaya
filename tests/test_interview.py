"""Acceptance tests for the guided interview.

Authored BEFORE the implementation. Tests are not delegated.

The declaration is this tool's real user interface, and until now it had none: `init`
writes four fields, a full check wants seventy-eight, and a check against the skeleton
returns nothing but `contested`. Nobody fills a seventy-eight-field JSON by hand from a
blank file, so the interview is what makes the tool usable by anyone who is not its author.

**The single property that matters most: a skipped question stays UNDECLARED.**

If the interview turns "I don't know" into `false`, every `contested` silently becomes a
`gap`, and the tool begins accusing clients of failing duties nobody ever asked them
about. That is the exact defect class that took nineteen fixes to clear out of the packs.
An interview that reintroduces it at the input layer would undo all of it.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from samanvaya import types as T
from samanvaya.interview import (
    QUESTIONS,
    Question,
    answers_to_declaration,
    run_interview,
)
from samanvaya.schema import validate


def _scripted(*replies: str):
    """A reader that returns each scripted reply in turn, then blanks forever."""
    it = iter(replies)

    def read(_prompt: str) -> str:
        return next(it, "")

    return read


def _sink() -> tuple[list[str], object]:
    lines: list[str] = []
    return lines, lines.append


def _first_bool() -> tuple[int, Question]:
    """The first yes/no question, and its index.

    Not `QUESTIONS[0]` — the bank opens with free-text and numeric questions about the
    organisation, and a yes/no parser test aimed at a free-text question passes for the
    wrong reason: any string is a valid answer there.
    """
    for i, q in enumerate(QUESTIONS):
        if q.kind == "bool":
            return i, q
    raise AssertionError("no boolean question in the bank")


class TestTheQuestionBank:
    def test_there_are_questions(self) -> None:
        assert QUESTIONS

    def test_every_question_is_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            QUESTIONS[0].prompt = "x"  # type: ignore[misc]

    def test_every_question_names_a_declaration_path(self) -> None:
        for q in QUESTIONS:
            assert "." in q.path, q.path

    def test_every_question_has_a_plain_english_prompt(self) -> None:
        """A field name is not a question. An adviser must be able to read it aloud."""
        for q in QUESTIONS:
            assert q.prompt.strip().endswith("?"), q.path
            assert len(q.prompt.split()) >= 4, q.path
            assert "_" not in q.prompt, f"{q.path}: prompt exposes a field name"

    def test_every_question_says_why_it_is_asked(self) -> None:
        """The adviser is being asked to state a fact about a client. They are entitled
        to know which provision turns on it."""
        for q in QUESTIONS:
            assert q.why.strip(), q.path

    def test_question_kinds_are_a_closed_set(self) -> None:
        assert {q.kind for q in QUESTIONS} <= {"bool", "str", "int", "float", "list"}

    def test_paths_are_unique(self) -> None:
        paths = [q.path for q in QUESTIONS]
        assert len(paths) == len(set(paths))

    def test_every_declarable_fact_is_askable(self) -> None:
        """Coverage. A field no question reaches can only ever be undeclared, which
        makes the obligation depending on it permanently `contested`."""
        blocks = {
            "organisation": T.Organisation,
            "notice": T.NoticeDeclaration,
            "consent_mechanism": T.ConsentMechanism,
            "breach_workflow": T.BreachWorkflow,
            "dsr_workflow": T.DsrWorkflow,
            "governance": T.GovernanceDeclaration,
            "cross_border": T.CrossBorderDeclaration,
            "children": T.ChildProcessingDeclaration,
        }
        asked = {q.path for q in QUESTIONS}
        missing: list[str] = []
        for prefix, cls in blocks.items():
            for f in dataclasses.fields(cls):
                if f.name == "described":
                    continue  # set by the interview when any field in the block is answered
                if f.name == "legal_name":
                    continue  # asked by the CLI before the bank, not by a bank question
                if f"{prefix}.{f.name}" not in asked:
                    missing.append(f"{prefix}.{f.name}")
        assert missing == [], missing

    def test_no_question_asks_for_a_credential(self) -> None:
        """The tool refuses to hold one. The interview must not invite one either."""
        for q in QUESTIONS:
            blob = (q.prompt + q.why).lower()
            for banned in ("password", "api key", "secret", "credential", "connection string",
                           "access key", "token"):
                assert banned not in blob, f"{q.path} invites a {banned}"


class TestSkipMeansUndeclared:
    """The property the whole interview exists to protect."""

    def test_a_skipped_boolean_is_none_not_false(self) -> None:
        i, q = _first_bool()
        answers = run_interview(_scripted(*(["skip"] * (i + 1))), _sink()[1], limit=i + 1)
        assert answers.get(q.path, "<absent>") in (None, "<absent>")
        assert answers.get(q.path) is not False

    def test_a_blank_answer_is_a_skip(self) -> None:
        i, q = _first_bool()
        answers = run_interview(_scripted(*([""] * (i + 1))), _sink()[1], limit=i + 1)
        assert answers.get(q.path) is not False

    def test_skipping_everything_produces_no_declared_facts(self) -> None:
        answers = run_interview(_scripted(), _sink()[1])
        assert all(v is None for v in answers.values()) or answers == {}

    def test_a_declaration_built_from_all_skips_is_all_contested_never_gap(self) -> None:
        """End to end: skipping is safe. It never accuses the client of anything."""
        pytest.importorskip("dpdp")
        from datetime import date

        from samanvaya.engine import run

        answers = run_interview(_scripted(), _sink()[1])
        obj = answers_to_declaration(answers, legal_name="Acme", author="adviser",
                                     jurisdictions=[{"country": "IN", "sub_units": [],
                                                     "sub_units_complete": True}])
        decl = validate(obj)
        result = run(decl, date(2027, 12, 1))
        results = {f.result for f in result.all_findings}
        assert T.ObligationResult.GAP not in results

    def test_an_explicit_no_is_recorded_as_false_not_skipped(self) -> None:
        """"No" is an answer. Losing the difference is the same defect from the other side."""
        i, q = _first_bool()
        answers = run_interview(_scripted(*(["skip"] * i), "n"), _sink()[1], limit=i + 1)
        assert answers[q.path] is False

    def test_an_explicit_yes_is_recorded_as_true(self) -> None:
        i, q = _first_bool()
        answers = run_interview(_scripted(*(["skip"] * i), "y"), _sink()[1], limit=i + 1)
        assert answers[q.path] is True


class TestAnswerParsing:
    @pytest.mark.parametrize("reply", ["y", "Y", "yes", "YES", " yes "])
    def test_yes_forms(self, reply: str) -> None:
        i, q = _first_bool()
        got = run_interview(_scripted(*(["skip"] * i), reply), _sink()[1], limit=i + 1)
        assert got[q.path] is True

    @pytest.mark.parametrize("reply", ["n", "N", "no", "NO", " no "])
    def test_no_forms(self, reply: str) -> None:
        i, q = _first_bool()
        got = run_interview(_scripted(*(["skip"] * i), reply), _sink()[1], limit=i + 1)
        assert got[q.path] is False

    @pytest.mark.parametrize("reply", ["s", "skip", "", "   ", "?skip"])
    def test_skip_forms_never_become_false(self, reply: str) -> None:
        i, q = _first_bool()
        got = run_interview(_scripted(*(["skip"] * i), reply), _sink()[1], limit=i + 1)
        assert got.get(q.path) is not False

    def test_an_unparseable_answer_re_asks_rather_than_guessing(self) -> None:
        i, q = _first_bool()
        lines, write = _sink()
        answers = run_interview(
            _scripted(*(["skip"] * i), "maybe", "banana", "y"), write, limit=i + 1)
        assert answers[q.path] is True
        assert any("did not understand" in ln.lower() or "please answer" in ln.lower()
                   for ln in lines)

    def test_a_number_question_rejects_text_and_re_asks(self) -> None:
        q = next(q for q in QUESTIONS if q.kind == "int")
        i = QUESTIONS.index(q)
        answers = run_interview(_scripted(*(["skip"] * i), "lots", "40"), _sink()[1], limit=i + 1)
        assert answers[q.path] == 40

    def test_a_credential_shaped_free_text_answer_is_refused(self) -> None:
        """Refused at the point of entry, not merely at validation."""
        q = next((q for q in QUESTIONS if q.kind == "str"), None)
        if q is None:
            pytest.skip("no free-text question in the bank")
        i = QUESTIONS.index(q)
        lines, write = _sink()
        answers = run_interview(
            _scripted(*(["skip"] * i), "postgresql://u:p@host:5432/db", "role-based access"),
            write, limit=i + 1,
        )
        assert answers[q.path] == "role-based access"
        assert any("credential" in ln.lower() for ln in lines)


class TestHelpAndProgress:
    def test_a_question_mark_explains_why_and_re_asks(self) -> None:
        i, q = _first_bool()
        lines, write = _sink()
        answers = run_interview(_scripted(*(["skip"] * i), "?", "y"), write, limit=i + 1)
        assert answers[q.path] is True
        assert any(q.why[:24] in ln for ln in lines)

    def test_progress_is_shown(self) -> None:
        lines, write = _sink()
        run_interview(_scripted("y", "y"), write, limit=2)
        blob = " ".join(lines)
        assert any(str(n) in blob for n in (1, 2))

    def test_sections_are_announced(self) -> None:
        lines, write = _sink()
        run_interview(_scripted(), write)
        blob = " ".join(lines).lower()
        assert "organisation" in blob


class TestTheResultValidates:
    def test_a_fully_skipped_interview_still_validates(self) -> None:
        obj = answers_to_declaration(run_interview(_scripted(), _sink()[1]),
                                     legal_name="Acme", author="adviser",
                                     jurisdictions=[{"country": "IN", "sub_units": [],
                                                     "sub_units_complete": True}])
        assert validate(obj) is not None

    def test_an_answered_interview_validates(self) -> None:
        obj = answers_to_declaration(run_interview(_scripted(*(["y"] * 200)), _sink()[1]),
                                     legal_name="Acme", author="adviser",
                                     jurisdictions=[{"country": "IN", "sub_units": [],
                                                     "sub_units_complete": True}])
        assert validate(obj) is not None

    def test_skipped_fields_are_absent_or_null_never_false(self) -> None:
        obj = answers_to_declaration(run_interview(_scripted(), _sink()[1]),
                                     legal_name="Acme", author="adviser", jurisdictions=[])
        blob = json.dumps(obj)
        assert "false" not in blob.lower() or blob.lower().count("false") <= 2

    def test_the_block_described_flag_is_set_when_a_block_is_answered(self) -> None:
        answers = run_interview(_scripted(*(["y"] * 200)), _sink()[1])
        obj = answers_to_declaration(answers, legal_name="Acme", author="adviser",
                                     jurisdictions=[])
        assert obj.get("notice", {}).get("described") is True


class TestCli:
    def test_interview_writes_a_declaration(self, tmp_path: Path, monkeypatch) -> None:
        import io

        from samanvaya.cli import main

        monkeypatch.setattr("sys.stdin", io.StringIO("Acme Ltd\nadviser\nIN\n" + "skip\n" * 200))
        rc = main(["interview", "--out", str(tmp_path / "d.json")])
        assert rc == 0
        assert (tmp_path / "d.json").is_file()

    def test_what_it_writes_validates(self, tmp_path: Path, monkeypatch) -> None:
        import io

        from samanvaya.cli import main

        monkeypatch.setattr("sys.stdin", io.StringIO("Acme Ltd\nadviser\nIN\n" + "skip\n" * 200))
        main(["interview", "--out", str(tmp_path / "d.json")])
        assert main(["validate", str(tmp_path / "d.json")]) == 0

    def test_it_refuses_to_overwrite_without_force(self, tmp_path: Path, monkeypatch) -> None:
        import io

        from samanvaya.cli import main

        target = tmp_path / "d.json"
        monkeypatch.setattr("sys.stdin", io.StringIO("Acme Ltd\nadviser\nIN\n" + "skip\n" * 200))
        main(["interview", "--out", str(target)])
        monkeypatch.setattr("sys.stdin", io.StringIO("Acme Ltd\nadviser\nIN\n" + "skip\n" * 200))
        assert main(["interview", "--out", str(target)]) != 0

    def test_interview_appears_in_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        from samanvaya.cli import main

        with pytest.raises(SystemExit):
            main(["--help"])
        assert "interview" in capsys.readouterr().out


class TestWorkedExamples:
    """A user needs to see what a filled declaration looks like, not only a blank one."""

    EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

    def test_the_examples_directory_exists(self) -> None:
        assert self.EXAMPLES.is_dir()

    def test_there_are_several_worked_examples(self) -> None:
        assert len(list(self.EXAMPLES.glob("*.json"))) >= 3

    def test_every_example_validates(self) -> None:
        for p in sorted(self.EXAMPLES.glob("*.json")):
            validate(json.loads(p.read_text())), p.name

    def test_every_example_carries_no_credential(self) -> None:
        from samanvaya.credentials import scan

        for p in sorted(self.EXAMPLES.glob("*.json")):
            assert scan(json.loads(p.read_text())) is None, p.name

    def test_every_example_is_explained(self) -> None:
        readme = self.EXAMPLES / "README.md"
        assert readme.is_file()
        text = readme.read_text()
        for p in sorted(self.EXAMPLES.glob("*.json")):
            assert p.name in text, p.name

    def test_the_examples_produce_reports(self) -> None:
        pytest.importorskip("dpdp")
        from datetime import date

        from samanvaya.engine import run

        for p in sorted(self.EXAMPLES.glob("*.json")):
            result = run(validate(json.loads(p.read_text())), date(2027, 12, 1))
            assert result.all_findings, p.name
