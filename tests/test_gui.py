"""Acceptance tests for the desktop window.

Authored BEFORE the implementation. Tests are not delegated.

These test the window's LOGIC, never its pixels. Asserting on widget geometry would test
Tkinter; asserting on the request/validate/generate path tests the decisions this tool
makes. The module must therefore keep the two apart: a `GenerateRequest` describing what
the user asked for, a `validate` that refuses a bad request with a message, and a
`generate` that does the work — none of which needs a display to run.

The constraint that matters most here is not technical. This window is operated by an
adviser and its output goes to a client, so it must never state a compliance conclusion.
It may report that the engine produced six unresolved findings. It may not report that the
organisation is compliant, non-compliant, passing, failing or at risk. That is the
adviser's judgement and carries the adviser's liability; a window that pre-empts it has
turned a tool into advice.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
AS_AT = "2027-12-01"


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    d = tmp_path / "out"
    d.mkdir()
    return d


def _request(**overrides):
    from samanvaya.gui import GenerateRequest
    from samanvaya.pdf_report import Preparer

    base = dict(
        declaration_path=EXAMPLES / "01-india-saas-startup.json",
        as_at=AS_AT,
        out_dir=overrides.pop("_out"),
        stem="report",
        formats=("pdf",),
        preparer=Preparer(firm="Example & Co"),
    )
    base.update(overrides)
    return GenerateRequest(**base)


class TestTheRequestIsValidatedBeforeAnythingRuns:
    def test_a_good_request_validates_clean(self, out_dir: Path) -> None:
        from samanvaya.gui import validate

        assert validate(_request(_out=out_dir)) == []

    def test_a_missing_declaration_is_refused_by_name(self, out_dir: Path) -> None:
        from samanvaya.gui import validate

        errors = validate(_request(_out=out_dir, declaration_path=Path("/nope/x.json")))
        assert errors and any("declaration" in e.lower() for e in errors)

    def test_a_malformed_date_is_refused_and_never_reaches_the_engine(
        self, out_dir: Path
    ) -> None:
        """`--as-at` is the reproducibility anchor; a bad one must not be guessed at."""
        from samanvaya.gui import validate

        for bad in ("01-12-2027", "2027-13-01", "tomorrow", ""):
            errors = validate(_request(_out=out_dir, as_at=bad))
            assert errors, f"{bad!r} was accepted as a date"

    def test_no_format_selected_is_refused(self, out_dir: Path) -> None:
        from samanvaya.gui import validate

        assert validate(_request(_out=out_dir, formats=()))

    def test_a_missing_output_directory_is_refused(self, tmp_path: Path) -> None:
        from samanvaya.gui import validate

        assert validate(_request(_out=tmp_path / "does-not-exist"))

    def test_a_credential_in_the_letterhead_is_refused(self, out_dir: Path) -> None:
        from samanvaya.gui import validate
        from samanvaya.pdf_report import Preparer

        errors = validate(
            _request(_out=out_dir, preparer=Preparer(firm="postgresql://u:p@h:5432/d"))
        )
        assert errors and any("credential" in e.lower() for e in errors)


class TestGenerateProducesTheSameFilesAsTheCli:
    def test_pdf_only_writes_exactly_one_file(self, out_dir: Path) -> None:
        from samanvaya.gui import generate

        result = generate(_request(_out=out_dir))
        assert result.error is None, result.error
        assert [p.name for p in result.files_written] == ["report.pdf"]
        assert (out_dir / "report.pdf").read_bytes()[:5] == b"%PDF-"

    def test_all_three_formats_share_one_stem(self, out_dir: Path) -> None:
        from samanvaya.gui import generate

        result = generate(_request(_out=out_dir, formats=("pdf", "md", "jsonl")))
        assert result.error is None, result.error
        assert {p.name for p in result.files_written} == {
            "report.pdf", "report.md", "report.jsonl",
        }

    def test_it_reports_counts_by_verdict(self, out_dir: Path) -> None:
        from samanvaya.gui import generate

        result = generate(_request(_out=out_dir))
        assert result.counts, "no verdict counts were reported"
        assert sum(result.counts.values()) > 0

    def test_the_counts_use_plain_english_not_enum_tokens(self, out_dir: Path) -> None:
        """The same rule the PDF verdict column obeys. `not_applicable` is a field name."""
        from samanvaya.gui import generate

        result = generate(_request(_out=out_dir))
        for label in result.counts:
            assert "_" not in label, label

    def test_an_engine_failure_becomes_a_message_not_a_traceback(
        self, out_dir: Path, tmp_path: Path
    ) -> None:
        from samanvaya.gui import generate

        broken = tmp_path / "broken.json"
        broken.write_text("{ not json")
        result = generate(_request(_out=out_dir, declaration_path=broken))
        assert result.error, "a malformed declaration did not produce an error message"
        assert "Traceback" not in result.error
        assert result.files_written == []

    def test_generating_twice_overwrites_rather_than_accumulating(
        self, out_dir: Path
    ) -> None:
        from samanvaya.gui import generate

        generate(_request(_out=out_dir))
        generate(_request(_out=out_dir))
        assert len(list(out_dir.glob("report.*"))) == 1


class TestTheLetterheadIsSharedWithTheCli:
    def test_saving_from_the_window_is_loadable_by_the_cli(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """One profile, two surfaces. Two profiles would let them disagree."""
        from samanvaya.gui import save_preparer
        from samanvaya.pdf_report import Preparer

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        p = Preparer(firm="Example & Co", adviser="A. Adviser", email="a@example.com")
        save_preparer(p)

        saved = json.loads((tmp_path / "cfg" / "preparer.json").read_text())
        assert saved["firm"] == "Example & Co"

    def test_the_window_loads_what_the_cli_saved(self, tmp_path: Path, monkeypatch) -> None:
        from samanvaya.gui import load_preparer
        from samanvaya.pdf_report import Preparer

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        (tmp_path / "cfg").mkdir(parents=True)
        Preparer(firm="From The CLI").save(tmp_path / "cfg" / "preparer.json")
        assert load_preparer().firm == "From The CLI"

    def test_a_corrupt_profile_does_not_stop_the_window_opening(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from samanvaya.gui import load_preparer

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        (tmp_path / "cfg").mkdir(parents=True)
        (tmp_path / "cfg" / "preparer.json").write_text("{ not json")
        assert load_preparer().is_empty


class TestTheWindowNeverStatesAConclusion:
    """The single most important test in this file.

    A window that tells a client's adviser "compliant" has stopped being a file dialog and
    started being counsel. The engine is careful never to do this — `contested` exists so
    that "I cannot tell" is never rendered as "you are fine" — and the window must not
    undo that discipline in its summary line.
    """

    BANNED = (
        "compliant", "non-compliant", "noncompliant", "you are compliant",
        "pass", "fail", "at risk", "safe", "violation", "breach of law",
    )

    def test_no_banned_conclusion_word_appears_in_a_user_facing_string(self) -> None:
        """Docstrings may state the rule; strings the user can see may not break it.

        Docstring nodes are identified BY IDENTITY, not by comparing text. An earlier
        version of this test compared each string literal against `ast.get_docstring`
        output, which cleans and re-indents, so a raw docstring node never matched its own
        cleaned form and the module docstring — which explains this very rule, and so
        necessarily contains the words — failed the test it was documenting.
        """
        import ast
        import inspect

        from samanvaya import gui

        tree = ast.parse(inspect.getsource(gui))

        docstring_nodes: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstring_nodes.add(id(body[0].value))

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in docstring_nodes:
                continue
            text = node.value.lower()
            for banned in self.BANNED:
                assert banned not in text, (
                    f"conclusion word {banned!r} in a non-docstring string: {text!r}"
                )

    def test_the_disclaimer_is_carried(self) -> None:
        import inspect

        from samanvaya import gui

        assert "DISCLAIMER" in inspect.getsource(gui), (
            "the window does not carry types.DISCLAIMER"
        )


class TestOffline:
    def test_generating_opens_no_socket(self, out_dir: Path) -> None:
        from samanvaya.gui import generate
        from samanvaya.offline_check import install_tripwire, remove_tripwire

        install_tripwire()
        try:
            result = generate(_request(_out=out_dir))
        finally:
            remove_tripwire()
        assert result.error is None, result.error

    def test_importing_the_window_opens_no_socket(self) -> None:
        from samanvaya.offline_check import install_tripwire, remove_tripwire

        install_tripwire()
        try:
            import importlib

            import samanvaya.gui

            importlib.reload(samanvaya.gui)
        finally:
            remove_tripwire()


class TestTheWindowCanProduceAQuestionnaire:
    """The intake half of the product, reachable from the surface the adviser opens.

    The renderer existed and nothing in the window could call it, so an adviser using
    the application — which is the whole point of the application — could not produce
    the document they are meant to send before the meeting. Tested here the same way
    everything else in this module is tested: through the headless function, never
    through a widget.
    """

    def test_it_writes_a_questionnaire(self, out_dir: Path) -> None:
        from samanvaya.gui import write_questionnaire
        from samanvaya.pdf_theme import Preparer

        result = write_questionnaire(out_dir, Preparer(firm="Example & Co"))
        assert result.error is None
        assert len(result.files_written) == 1
        assert result.files_written[0].read_bytes()[:5] == b"%PDF-"

    def test_it_needs_no_declaration(self, out_dir: Path) -> None:
        """It is the document that PRECEDES a declaration. Requiring one is the bug."""
        from samanvaya.gui import write_questionnaire
        from samanvaya.pdf_theme import Preparer

        assert write_questionnaire(out_dir, Preparer()).error is None

    def test_it_refuses_a_credential_in_the_letterhead(self, out_dir: Path) -> None:
        from samanvaya.gui import write_questionnaire
        from samanvaya.pdf_theme import Preparer

        result = write_questionnaire(
            out_dir, Preparer(firm="postgresql://u:p@host:5432/db")
        )
        assert result.error is not None
        assert "credential" in result.error.lower()
        assert result.files_written == []

    def test_a_bad_folder_is_reported_and_not_raised(self, tmp_path: Path) -> None:
        from samanvaya.gui import write_questionnaire
        from samanvaya.pdf_theme import Preparer

        missing = tmp_path / "nope" / "deeper"
        result = write_questionnaire(missing, Preparer())
        assert result.error is not None
        assert result.files_written == []

    def test_it_states_no_conclusion_about_the_client(self, out_dir: Path) -> None:
        """The window's standing rule, applied to the new surface."""
        from tests.pdf_probe import drawn_text

        from samanvaya.gui import write_questionnaire
        from samanvaya.pdf_theme import Preparer

        result = write_questionnaire(out_dir, Preparer(firm="Example & Co"))
        text = drawn_text(result.files_written[0]).lower()
        for word in ("non-compliant", "at risk", "we recommend"):
            assert word not in text

    def test_the_menu_offers_it(self) -> None:
        """Reachable, not merely present. A function nobody can call is dead code."""
        from samanvaya.gui import _MENU_COMMANDS, MENU_SPEC

        commands = {
            item.command
            for menu in MENU_SPEC
            for item in menu.items
            if item.command and not item.command.startswith("_builtin:")
        }
        assert "save_questionnaire" in commands
        assert "save_questionnaire" in _MENU_COMMANDS


class TestTheWidgetsActuallyWork:
    """The one test in this file that builds real widgets, and why.

    Everything else here tests the window's logic and never touches Tk, which is right:
    asserting on widget geometry tests Tkinter. But on 2026-08-20 a build shipped that
    died on launch with `AttributeError: module 'tkinter.ttk' has no attribute 'Menu'`
    while all 589 tests passed, because not one of them constructed a widget. The build
    script grew a launch gate in response — but a launch gate only proves the window
    OPENS. It never clicks anything, so a handler that raises stays invisible until an
    adviser finds it.

    So: construct the window, click the new button, and require a file on disk. This
    exercises `App.__init__`, the menu bar, and the handler in one pass. It skips rather
    than fails where no display exists, because a headless machine cannot answer this
    question either way and a test that fails there teaches the wrong lesson.
    """

    def _root(self):
        tkinter = pytest.importorskip("tkinter")
        try:
            root = tkinter.Tk()
        except Exception as exc:  # pragma: no cover - depends on the machine
            pytest.skip(f"no usable display: {exc}")
        root.withdraw()
        return root

    def test_the_questionnaire_button_writes_a_file(
        self, out_dir: Path, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        root = self._root()
        try:
            from samanvaya.gui import App

            app = App(root)
            app.out_dir_var.set(str(out_dir))
            app.firm_var.set("Example & Co, Advocates")
            app.questionnaire_button.invoke()
            written = out_dir / "questionnaire.pdf"
            assert written.is_file(), "the button ran and produced nothing"
            assert written.read_bytes()[:5] == b"%PDF-"
        finally:
            root.destroy()

    def test_every_menu_item_resolves_to_a_callable(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The 2026-08-20 crash was in menu construction. Build the menu for real."""
        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        root = self._root()
        try:
            from samanvaya.gui import App

            App(root)
        finally:
            root.destroy()
