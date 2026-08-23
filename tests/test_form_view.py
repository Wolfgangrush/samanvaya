"""Acceptance tests for the sectioned intake window — BMAD/08 part B, the view.

Authored BEFORE the implementation. Tests are not delegated.

`tests/test_form.py` holds the model to account. This file holds the WINDOW to account,
and it builds real widgets to do it — which is a deliberate departure from the rest of
this suite and needs its reason stated.

On 2026-08-20 a build shipped that died on launch with `AttributeError: module
'tkinter.ttk' has no attribute 'Menu'` while all 589 tests passed, because not one of
them constructed a widget. The launch gate added in response proves the window OPENS and
never touches a control. This form is the surface an adviser will sit in front of for two
hours with a client in the room; "it opened" is not the standard. So these tests build
the window, drive the controls through the same commit path a click goes through, and
assert what lands in the model.

They skip rather than fail where there is no display, because a headless machine cannot
answer the question either way.

WHAT THE WINDOW MAY NOT DO — BMAD/08 part B
  - No forced linear wizard. Sections are jumpable in any order, because a client answers
    out of order and the adviser circles back.
  - No inference. It never fills one answer from another and never hides a question
    because an earlier answer made it look unlikely.
  - No verdicts. It gathers; it does not assess.
  - "Not established" is a visible, selectable answer on every question, and the default.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samanvaya.interview import QUESTIONS


def _root():
    tkinter = pytest.importorskip("tkinter")
    try:
        root = tkinter.Tk()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable display: {exc}")
    root.withdraw()
    return root


@pytest.fixture
def window(tmp_path: Path):
    """A real window over a real form, torn down after each test."""
    from samanvaya.form import IntakeForm
    from samanvaya.form_view import IntakeWindow

    root = _root()
    form = IntakeForm(working_file=tmp_path / "working.json")
    form.legal_name = "Example Ltd"
    form.author = "A. Adviser"
    form.add_jurisdiction("IN")
    view = IntakeWindow(root, form)
    try:
        yield view
    finally:
        root.destroy()


def _first(kind: str):
    for question in QUESTIONS:
        if question.kind == kind:
            return question
    raise AssertionError(f"the question bank has no {kind!r} question")


class TestItBuildsAtAll:
    def test_the_window_constructs(self, window) -> None:
        """The 2026-08-20 lesson: constructing is itself a thing that can fail."""
        assert window is not None

    def test_there_is_one_page_per_section(self, window) -> None:
        from samanvaya.form import IntakeForm

        expected = IntakeForm().sections()
        assert tuple(window.section_names) == tuple(expected)

    def test_every_question_has_a_control(self, window) -> None:
        """A question with no control is a question the adviser cannot answer."""
        for question in QUESTIONS:
            assert window.widget_for(question.path) is not None, question.path


class TestSectionsAreJumpableInAnyOrder:
    """A client answers out of order. A wizard that forces a path is the wrong shape."""

    def test_any_section_can_be_opened_directly(self, window) -> None:
        for title in window.section_names:
            window.show_section(title)
            assert window.current_section == title

    def test_sections_can_be_opened_backwards(self, window) -> None:
        for title in reversed(list(window.section_names)):
            window.show_section(title)
            assert window.current_section == title

    def test_opening_a_section_does_not_disturb_answers(self, window) -> None:
        question = _first("bool")
        window.write(question.path, "Yes")
        for title in window.section_names:
            window.show_section(title)
        assert window.form.get(question.path) is True

    def test_an_unknown_section_is_refused(self, window) -> None:
        with pytest.raises((KeyError, ValueError)):
            window.show_section("Not A Section")


class TestNotEstablishedIsOnScreenAndIsTheDefault:
    def test_a_yes_no_question_offers_three_answers(self, window) -> None:
        """Two boxes make the honest answer unavailable, so a client picks one of two."""
        question = _first("bool")
        assert tuple(window.choices_for(question.path)) == (
            "Yes",
            "No",
            "Not established",
        )

    def test_every_control_starts_at_not_established(self, window) -> None:
        from samanvaya.form import NOT_ESTABLISHED

        for question in QUESTIONS:
            assert window.form.get(question.path) is NOT_ESTABLISHED, question.path

    def test_it_can_be_chosen_back_after_an_answer(self, window) -> None:
        """An adviser who mis-clicked must be able to return to not-established."""
        from samanvaya.form import NOT_ESTABLISHED

        question = _first("bool")
        window.write(question.path, "Yes")
        assert window.form.get(question.path) is True
        window.write(question.path, "Not established")
        assert window.form.get(question.path) is NOT_ESTABLISHED


class TestTheControlsWriteThroughToTheModel:
    def test_a_yes_no_answer_reaches_the_model(self, window) -> None:
        question = _first("bool")
        assert window.write(question.path, "Yes") is None
        assert window.form.get(question.path) is True

    def test_a_number_answer_reaches_the_model(self, window) -> None:
        question = _first("int")
        assert window.write(question.path, "42") is None
        assert window.form.get(question.path) == 42

    def test_a_list_answer_reaches_the_model(self, window) -> None:
        question = _first("list")
        assert window.write(question.path, "one, two") is None
        assert window.form.get(question.path) == ["one", "two"]

    def test_a_bad_number_is_reported_and_not_stored(self, window) -> None:
        from samanvaya.form import NOT_ESTABLISHED

        question = _first("int")
        message = window.write(question.path, "quite a lot")
        assert message, "the window accepted a word as a number"
        assert window.form.get(question.path) is NOT_ESTABLISHED

    def test_a_credential_is_refused_at_the_window(self, window) -> None:
        """The firewall must fire before the answer is on screen as accepted."""
        question = _first("str")
        message = window.write(question.path, "postgresql://u:p@host:5432/db")
        assert message and "credential" in message.lower()


class TestProgressIsVisible:
    def test_a_fresh_section_reports_none_answered(self, window) -> None:
        for title in window.section_names:
            assert "0" in window.progress_text(title)

    def test_answering_moves_the_count(self, window) -> None:
        question = QUESTIONS[0]
        before = window.progress_text(question.section)
        window.write(question.path, "Yes" if question.kind == "bool" else "stated")
        after = window.progress_text(question.section)
        assert after != before, "the section count did not move"

    def test_the_total_is_shown(self, window) -> None:
        assert str(len(QUESTIONS)) in window.total_text()

    def test_not_established_does_not_advance_the_count(self, window) -> None:
        question = QUESTIONS[0]
        before = window.progress_text(question.section)
        window.write(question.path, "Not established")
        assert window.progress_text(question.section) == before


class TestAutosaveAndSave:
    def test_a_single_answer_is_autosaved(self, window, tmp_path: Path) -> None:
        """A two-hour meeting must survive a closed lid."""
        window.write(_first("bool").path, "Yes")
        assert (tmp_path / "working.json").is_file()

    def test_save_writes_a_declaration_the_engine_reads(
        self, window, tmp_path: Path
    ) -> None:
        from datetime import date

        from samanvaya.declaration import load
        from samanvaya.engine import run

        window.write(_first("bool").path, "Yes")
        out = tmp_path / "declaration.json"
        assert window.save_to(out) is None
        result = run(load(out), date(2027, 12, 1))
        assert result.all_findings

    def test_save_reports_a_missing_organisation_name_rather_than_raising(
        self, window, tmp_path: Path
    ) -> None:
        """A traceback in front of a client is not an error message."""
        window.form.legal_name = ""
        message = window.save_to(tmp_path / "declaration.json")
        assert message, "the window saved a declaration the schema will reject"


class TestItGathersAndDoesNotAssess:
    BANNED = (
        "compliant", "non-compliant", "pass", "fail", "at risk", "safe",
        "violation", "breach of law", "you should", "we recommend",
        "satisfied", "gap", "unresolved",
    )

    def test_no_verdict_vocabulary_in_what_the_window_authors(self) -> None:
        import re

        from samanvaya.form_view import AUTHORED_TEXT

        assert AUTHORED_TEXT, "no authored strings were declared"
        surface = " ".join(AUTHORED_TEXT).lower()
        for word in self.BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", surface), word

    def test_the_window_does_not_import_the_engine(self) -> None:
        """A window that can run the engine is a window that can show a verdict."""
        import inspect

        from samanvaya import form_view

        source = inspect.getsource(form_view)
        assert "from samanvaya.engine" not in source
        assert "_VERDICT" not in source

    def test_no_question_is_hidden(self, window) -> None:
        """No inference: an earlier answer must not remove a later question."""
        question = _first("bool")
        window.write(question.path, "No")
        for other in QUESTIONS:
            assert window.widget_for(other.path) is not None, (
                f"{other.path} disappeared after an unrelated answer"
            )


class TestTheQuestionTextIsTheBankText:
    def test_prompts_are_shown_verbatim(self, window) -> None:
        """ONE SOURCE, as everywhere else: the adviser reads the bank's words aloud."""
        for question in QUESTIONS:
            assert window.prompt_for(question.path) == question.prompt

    def test_the_reason_is_available(self, window) -> None:
        """The `why` is what lets an adviser answer 'why are you asking me that'."""
        for question in QUESTIONS:
            assert window.why_for(question.path) == question.why
