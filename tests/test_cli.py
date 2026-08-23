"""Acceptance tests for the command-line interface.

Authored BEFORE the implementation. Tests are not delegated.

The CLI is the whole product surface: one adviser, one terminal, one declaration file. Two
behaviours are load-bearing rather than cosmetic.

**Nothing is written unless asked.** Findings go to a file the adviser names. `--stdout` is
opt-in. The tool does not email, upload, post or file anything, and it keeps no history —
the adviser decides what, if anything, leaves the machine.

**Failures are legible.** A missing file, a bad date, an unknown regime and a declaration
carrying a credential must each produce a named message and a non-zero exit, never a
traceback. An adviser mid-engagement cannot debug a stack trace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samanvaya.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
CANONICAL = str(FIXTURES / "canonical_declaration.json")


class TestVersion:
    def test_version_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["version"]) == 0

    def test_version_prints_the_tool_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        from samanvaya import __version__

        main(["version"])
        assert __version__ in capsys.readouterr().out


class TestValidate:
    def test_a_good_declaration_validates(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["validate", CANONICAL]) == 0

    def test_validate_reports_the_declaration_hash(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["validate", CANONICAL])
        assert len([t for t in capsys.readouterr().out.split() if len(t) == 64]) >= 1

    def test_an_unknown_key_fails_with_a_named_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["validate", str(FIXTURES / "declaration_unknown_key.json")])
        assert rc != 0
        assert "sub_national_units" in capsys.readouterr().err

    def test_a_credential_fails_and_says_credential(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["validate", str(FIXTURES / "declaration_with_credential.json")])
        assert rc != 0
        assert "credential" in capsys.readouterr().err.lower()

    def test_the_credential_error_does_not_echo_the_secret(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["validate", str(FIXTURES / "declaration_with_credential.json")])
        out = capsys.readouterr()
        assert "hunter2" not in (out.out + out.err)

    def test_a_missing_file_fails_with_a_named_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["validate", str(FIXTURES / "nope.json")])
        assert rc != 0
        assert "nope.json" in capsys.readouterr().err


class TestCheck:
    def test_check_writes_a_report(self, tmp_path: Path) -> None:
        rc = main(["check", CANONICAL, "--out", str(tmp_path / "r"), "--as-at", "2026-08-19"])
        assert rc == 0
        assert (tmp_path / "r.md").is_file()
        assert (tmp_path / "r.jsonl").is_file()

    def test_check_writes_nothing_to_stdout_by_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Findings are client material. They go to the named file, not the scrollback."""
        main(["check", CANONICAL, "--out", str(tmp_path / "r"), "--as-at", "2026-08-19"])
        out = capsys.readouterr().out
        assert "satisfied" not in out.lower() or len(out) < 400

    def test_stdout_is_opt_in(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main([
            "check", CANONICAL, "--out", str(tmp_path / "r"),
            "--as-at", "2026-08-19", "--stdout",
        ])
        assert len(capsys.readouterr().out) > 400

    def test_format_md_writes_only_markdown(self, tmp_path: Path) -> None:
        main([
            "check", CANONICAL, "--out", str(tmp_path / "r"),
            "--as-at", "2026-08-19", "--format", "md",
        ])
        assert (tmp_path / "r.md").is_file()
        assert not (tmp_path / "r.jsonl").exists()

    def test_the_report_carries_the_disclaimer(self, tmp_path: Path) -> None:
        main(["check", CANONICAL, "--out", str(tmp_path / "r"), "--as-at", "2026-08-19"])
        assert "not legal advice" in (tmp_path / "r.md").read_text(encoding="utf-8").lower()

    def test_regime_can_be_restricted_and_repeated(self, tmp_path: Path) -> None:
        rc = main([
            "check", str(FIXTURES / "multi_regime.json"), "--out", str(tmp_path / "r"),
            "--as-at", "2026-08-19", "--regime", "IN", "--regime", "EU",
        ])
        assert rc == 0
        header = json.loads((tmp_path / "r.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert header["type"] == "header"

    def test_an_unknown_regime_fails_with_a_named_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main([
            "check", CANONICAL, "--out", str(tmp_path / "r"),
            "--as-at", "2026-08-19", "--regime", "ZZ",
        ])
        assert rc != 0
        assert "ZZ" in capsys.readouterr().err

    def test_a_malformed_as_at_fails_with_a_named_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main([
            "check", CANONICAL, "--out", str(tmp_path / "r"), "--as-at", "19-08-2026",
        ])
        assert rc != 0
        assert "19-08-2026" in capsys.readouterr().err

    def test_two_runs_produce_identical_reports(self, tmp_path: Path) -> None:
        """Determinism is what lets an adviser re-run and stand behind the same answer."""
        main(["check", CANONICAL, "--out", str(tmp_path / "a"), "--as-at", "2026-08-19"])
        main(["check", CANONICAL, "--out", str(tmp_path / "b"), "--as-at", "2026-08-19"])
        assert (tmp_path / "a.md").read_text() == (tmp_path / "b.md").read_text()


class TestInit:
    def test_init_writes_a_declaration_skeleton(self, tmp_path: Path) -> None:
        rc = main(["init", "--out", str(tmp_path / "declaration.json")])
        assert rc == 0
        assert (tmp_path / "declaration.json").is_file()

    def test_the_skeleton_it_writes_validates(self, tmp_path: Path) -> None:
        main(["init", "--out", str(tmp_path / "declaration.json")])
        assert main(["validate", str(tmp_path / "declaration.json")]) == 0

    def test_init_refuses_to_overwrite_without_force(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "declaration.json"
        main(["init", "--out", str(target)])
        rc = main(["init", "--out", str(target)])
        assert rc != 0
        assert "exists" in capsys.readouterr().err.lower()

    def test_the_skeleton_contains_no_credential_shaped_placeholder(
        self, tmp_path: Path
    ) -> None:
        main(["init", "--out", str(tmp_path / "declaration.json")])
        text = (tmp_path / "declaration.json").read_text(encoding="utf-8").lower()
        for shape in ("password", "://", "api_key", "secret"):
            assert shape not in text


class TestCite:
    def test_cite_lists_the_packs_and_their_instruments(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["cite"]) == 0
        out = capsys.readouterr().out
        assert "Regulation (EU) 2016/679" in out
        assert "Digital Personal Data Protection Act 2023" in out

    def test_cite_marks_which_packs_are_draft(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["cite"])
        assert "draft" in capsys.readouterr().out.lower()

    def test_cite_names_no_nonexistent_instrument(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["cite"])
        out = capsys.readouterr().out.lower()
        for banned in ("us gdpr", "singapore gdpr", "canada gdpr"):
            assert banned not in out


class TestErrorsAreNotTracebacks:
    @pytest.mark.parametrize(
        "argv",
        [
            ["validate", "/nonexistent/decl.json"],
            ["check", "/nonexistent/decl.json", "--out", "/tmp/x"],
        ],
    )
    def test_no_command_raises_out_of_main(self, argv: list[str]) -> None:
        assert main(argv) != 0

    def test_no_subcommand_exits_non_zero(self) -> None:
        with pytest.raises(SystemExit):
            main([])


class TestTheQuestionnaireIsReachable:
    """Added 2026-08-22.

    The questionnaire renderer shipped with no caller. Not a hidden feature — dead
    code: no CLI subcommand, no menu item, no button. The only way to produce the
    document the adviser is supposed to send a client a week before the meeting was to
    import the module and call it from a Python prompt.

    That is the same defect BMAD/08 was written to correct, one layer down. The window
    shipped as a file picker for a file nothing could create; the questionnaire shipped
    as a renderer nothing could reach. An item may be deferred only if it is possible
    to name who does that job in the meantime, and for both of these the answer was
    nobody.
    """

    def test_the_command_writes_a_pdf(self, tmp_path: Path) -> None:
        from samanvaya.cli import main

        out = tmp_path / "questionnaire.pdf"
        assert main(["questionnaire", "--out", str(out)]) == 0
        assert out.read_bytes()[:5] == b"%PDF-"

    def test_it_takes_a_letterhead_from_the_flags(self, tmp_path: Path) -> None:
        from tests.pdf_probe import drawn_text

        from samanvaya.cli import main

        out = tmp_path / "q.pdf"
        assert main([
            "questionnaire", "--out", str(out),
            "--firm", "Example & Co", "--adviser", "A. Adviser",
        ]) == 0
        assert "Example & Co" in drawn_text(out)

    def test_it_falls_back_to_the_saved_profile(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """One letterhead store. The questionnaire and the report cannot disagree."""
        from tests.pdf_probe import drawn_text

        from samanvaya.cli import main

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        assert main(["profile", "--firm", "Saved & Co"]) == 0
        out = tmp_path / "q.pdf"
        assert main(["questionnaire", "--out", str(out)]) == 0
        assert "Saved & Co" in drawn_text(out)

    def test_a_credential_in_a_letterhead_flag_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The letterhead reaches a file that leaves the office. Same firewall."""
        from samanvaya.cli import main

        out = tmp_path / "q.pdf"
        rc = main([
            "questionnaire", "--out", str(out),
            "--firm", "postgresql://u:p@host:5432/db",
        ])
        assert rc != 0
        assert "credential" in capsys.readouterr().err.lower()
        assert not out.exists(), "a refused run still wrote the file"

    def test_it_appears_in_the_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        from samanvaya.cli import main

        with pytest.raises(SystemExit):
            main(["--help"])
        assert "questionnaire" in capsys.readouterr().out
