"""Acceptance tests for the sectioned intake form — BMAD/08 part B.

Authored BEFORE the implementation. Tests are not delegated.

Part A gave the adviser a questionnaire to hand a client. This is the other half: the
place the answers go once the client has written them down. Until it exists the window
can produce a form and cannot consume one, and the adviser is still back at a JSON file.

These test the form's LOGIC, never its pixels — the same split the rest of this suite
uses. A headless `IntakeForm` holds the answers, validates them, counts them, saves them
and reloads them; the Tk view is a thin skin over it. Everything that matters about
intake can therefore be asserted without a display.

THE RULE THAT OUTRANKS EVERY OTHER ONE HERE
-------------------------------------------
**"Not established" is a first-class answer and the default.** It is not a blank, not a
missing value, and never a "no". The engine treats an undeclared fact as `contested`,
which is the honest verdict; a form that coerces a guess into a field to look complete
destroys the gap/contested distinction, and that distinction is the single most
dangerous thing this tool could lose. Every default is NOT_ESTABLISHED and a question
is only answered when a human answered it.

BANNED, from BMAD/08 part B:
  - No new dependency. Tkinter and the standard library.
  - No inference. The form never fills one answer from another, never defaults a
    statutory fact to a convenient value, and never hides a question because an earlier
    answer made it look unlikely.
  - No verdicts. The form gathers; it does not assess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samanvaya.interview import QUESTIONS

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def form(tmp_path: Path):
    """A fresh form with a working file, which is how the window will always build one."""
    from samanvaya.form import IntakeForm

    return IntakeForm(working_file=tmp_path / "working.json")


def _first(kind: str):
    """Return the first question of a given kind, so tests name no path literally."""
    for question in QUESTIONS:
        if question.kind == kind:
            return question
    raise AssertionError(f"the question bank has no {kind!r} question")


class TestNotEstablishedIsTheDefault:
    """The rule the whole form is built around."""

    def test_every_question_starts_not_established(self, form) -> None:
        from samanvaya.form import NOT_ESTABLISHED

        for question in QUESTIONS:
            assert form.get(question.path) is NOT_ESTABLISHED, question.path

    def test_not_established_is_not_a_blank_and_not_a_no(self, form) -> None:
        """Three different things. Collapsing them is how a gap becomes an accusation."""
        from samanvaya.form import NOT_ESTABLISHED

        assert NOT_ESTABLISHED is not None
        assert NOT_ESTABLISHED is not False
        assert NOT_ESTABLISHED != ""
        assert NOT_ESTABLISHED != 0

    def test_an_unanswered_question_is_absent_from_the_declaration(self, form) -> None:
        """Absent is what makes the engine report `contested` rather than a gap."""
        form.legal_name = "Example Ltd"
        form.author = "A. Adviser"
        form.add_jurisdiction("IN")
        declaration = form.to_declaration()
        blob = json.dumps(declaration)
        assert "NOT_ESTABLISHED" not in blob
        assert "not established" not in blob.lower()

    def test_clearing_an_answer_returns_it_to_not_established(self, form) -> None:
        """An adviser who mistyped must be able to un-answer, not just overwrite."""
        from samanvaya.form import NOT_ESTABLISHED

        question = _first("bool")
        assert form.set(question.path, "Yes") is None
        assert form.get(question.path) is True
        form.clear(question.path)
        assert form.get(question.path) is NOT_ESTABLISHED

    def test_it_never_answers_a_question_the_user_did_not_answer(self, form) -> None:
        """No inference. One answer must not imply another."""
        from samanvaya.form import NOT_ESTABLISHED

        target = _first("bool")
        form.set(target.path, "Yes")
        others = [q for q in QUESTIONS if q.path != target.path]
        for question in others:
            assert form.get(question.path) is NOT_ESTABLISHED, (
                f"answering {target.path} also set {question.path}"
            )


class TestOneSource:
    def test_the_form_asks_exactly_the_question_bank(self, form) -> None:
        """Same rule as the questionnaire: nothing invented, nothing dropped."""
        assert [q.path for q in form.questions()] == [q.path for q in QUESTIONS]

    def test_sections_keep_the_interview_order(self, form) -> None:
        seen: list[str] = []
        for question in QUESTIONS:
            if question.section not in seen:
                seen.append(question.section)
        assert list(form.sections()) == seen

    def test_every_section_can_be_addressed_directly(self, form) -> None:
        """Jumpable in any order — a client answers out of order and the adviser circles back."""
        for section in form.sections():
            assert form.questions_in(section), f"{section} returned nothing"

    def test_a_section_holds_only_its_own_questions(self, form) -> None:
        for section in form.sections():
            for question in form.questions_in(section):
                assert question.section == section


class TestAnswersAreParsedAndRefusedByKind:
    def test_a_yes_no_question_takes_yes_and_no(self, form) -> None:
        question = _first("bool")
        assert form.set(question.path, "Yes") is None
        assert form.get(question.path) is True
        assert form.set(question.path, "No") is None
        assert form.get(question.path) is False

    def test_not_established_is_accepted_as_an_answer_everywhere(self, form) -> None:
        """It is a choice the user can make, not only a starting state."""
        from samanvaya.form import NOT_ESTABLISHED

        for kind in ("bool", "int", "float", "str", "list"):
            question = _first(kind)
            form.set(question.path, "Not established")
            assert form.get(question.path) is NOT_ESTABLISHED, kind

    def test_a_number_question_refuses_words_and_keeps_the_old_value(self, form) -> None:
        """A refusal must not also destroy what was there."""
        from samanvaya.form import NOT_ESTABLISHED

        question = _first("int")
        message = form.set(question.path, "quite a lot")
        assert message, "an unparseable number was accepted"
        assert form.get(question.path) is NOT_ESTABLISHED

    def test_a_number_question_takes_a_number(self, form) -> None:
        question = _first("int")
        assert form.set(question.path, "42") is None
        assert form.get(question.path) == 42

    def test_a_list_question_splits_on_commas(self, form) -> None:
        question = _first("list")
        assert form.set(question.path, "one, two ,three") is None
        assert form.get(question.path) == ["one", "two", "three"]

    def test_a_text_question_keeps_what_was_typed(self, form) -> None:
        question = _first("str")
        assert form.set(question.path, "Private limited company") is None
        assert form.get(question.path) == "Private limited company"

    def test_an_unknown_path_is_refused(self, form) -> None:
        """A typo in a path must not silently create a field the engine will never read."""
        with pytest.raises(KeyError):
            form.set("organisation.not_a_real_field", "x")


class TestTheCredentialFirewall:
    """The same firewall that guards the letterhead guards every free-text answer."""

    def test_a_connection_string_is_refused(self, form) -> None:
        from samanvaya.form import NOT_ESTABLISHED

        question = _first("str")
        message = form.set(question.path, "postgresql://u:p@host:5432/db")
        assert message and "credential" in message.lower()
        assert form.get(question.path) is NOT_ESTABLISHED

    def test_a_refused_answer_never_reaches_the_working_file(self, form, tmp_path: Path) -> None:
        """Refusing after writing is not refusing."""
        question = _first("str")
        form.set(question.path, "postgresql://u:p@host:5432/db")
        working = tmp_path / "working.json"
        if working.exists():
            assert "postgresql://" not in working.read_text()

    def test_a_credential_in_a_list_answer_is_refused(self, form) -> None:
        question = _first("list")
        message = form.set(question.path, "tls, postgresql://u:p@host:5432/db")
        assert message and "credential" in message.lower()

    def test_an_ordinary_answer_is_not_mistaken_for_a_credential(self, form) -> None:
        question = _first("str")
        assert form.set(question.path, "Private limited company") is None


class TestProgress:
    def test_a_fresh_section_reports_nothing_answered(self, form) -> None:
        for section in form.sections():
            progress = form.progress(section)
            assert progress.answered == 0
            assert progress.total == len(form.questions_in(section))

    def test_answering_advances_only_its_own_section(self, form) -> None:
        question = QUESTIONS[0]
        form.set(question.path, "Some legal form" if question.kind == "str" else "Yes")
        for section in form.sections():
            expected = 1 if section == question.section else 0
            assert form.progress(section).answered == expected, section

    def test_not_established_does_not_count_as_answered(self, form) -> None:
        """Otherwise a form full of unknowns reports itself complete."""
        question = QUESTIONS[0]
        form.set(question.path, "Not established")
        assert form.progress(question.section).answered == 0

    def test_the_total_is_the_sum_of_the_sections(self, form) -> None:
        total = form.total_progress()
        assert total.total == len(QUESTIONS)
        assert total.total == sum(form.progress(s).total for s in form.sections())

    def test_clearing_an_answer_decreases_the_count(self, form) -> None:
        question = _first("bool")
        form.set(question.path, "Yes")
        assert form.total_progress().answered == 1
        form.clear(question.path)
        assert form.total_progress().answered == 0


class TestAutosaveAndResume:
    """A two-hour client meeting must survive a crash, a battery, or a closed lid."""

    def test_the_working_file_is_written_after_a_single_answer(
        self, form, tmp_path: Path
    ) -> None:
        question = _first("bool")
        form.set(question.path, "Yes")
        working = tmp_path / "working.json"
        assert working.is_file(), "nothing was autosaved"

    def test_a_new_form_resumes_what_the_old_one_wrote(self, form, tmp_path: Path) -> None:
        """The crash test: the object is gone, the answers are not."""
        from samanvaya.form import IntakeForm

        question = _first("bool")
        form.legal_name = "Example Ltd"
        form.author = "A. Adviser"
        form.add_jurisdiction("IN")
        form.set(question.path, "Yes")

        resumed = IntakeForm.resume(tmp_path / "working.json")
        assert resumed.get(question.path) is True
        assert resumed.legal_name == "Example Ltd"
        assert resumed.author == "A. Adviser"
        assert [j["country"] for j in resumed.jurisdictions] == ["IN"]

    def test_resuming_leaves_unanswered_questions_unanswered(
        self, form, tmp_path: Path
    ) -> None:
        from samanvaya.form import NOT_ESTABLISHED, IntakeForm

        answered = _first("bool")
        form.set(answered.path, "Yes")
        resumed = IntakeForm.resume(tmp_path / "working.json")
        for question in QUESTIONS:
            if question.path == answered.path:
                continue
            assert resumed.get(question.path) is NOT_ESTABLISHED, question.path

    def test_resuming_a_saved_declaration_carries_the_answers_in(
        self, tmp_path: Path
    ) -> None:
        """Reopen a part-finished declaration written by the CLI interview and continue."""
        from samanvaya.form import IntakeForm

        source = json.loads((EXAMPLES / "01-india-saas-startup.json").read_text())
        target = tmp_path / "existing.json"
        target.write_text(json.dumps(source))

        resumed = IntakeForm.resume(target)
        assert resumed.total_progress().answered > 0, "a filled declaration resumed empty"
        assert resumed.legal_name == source["organisation"]["legal_name"]

    def test_a_form_with_no_working_file_still_works(self) -> None:
        """Autosave is a safety net, not a precondition."""
        from samanvaya.form import IntakeForm

        unsaved = IntakeForm()
        assert unsaved.set(_first("bool").path, "Yes") is None

    def test_a_corrupt_working_file_is_refused_not_silently_emptied(
        self, tmp_path: Path
    ) -> None:
        """Silently starting blank would look exactly like a lost meeting."""
        from samanvaya.form import IntakeForm

        broken = tmp_path / "broken.json"
        broken.write_text("{ this is not json")
        with pytest.raises(Exception):
            IntakeForm.resume(broken)


class TestJurisdictions:
    """`QUESTIONS` does not cover countries, and the declaration cannot be built without them."""

    def test_a_fresh_form_declares_no_jurisdiction(self, form) -> None:
        assert list(form.jurisdictions) == []

    def test_a_country_can_be_added_and_removed(self, form) -> None:
        form.add_jurisdiction("IN")
        form.add_jurisdiction("DE")
        assert [j["country"] for j in form.jurisdictions] == ["IN", "DE"]
        form.remove_jurisdiction("IN")
        assert [j["country"] for j in form.jurisdictions] == ["DE"]

    def test_the_same_country_is_not_added_twice(self, form) -> None:
        form.add_jurisdiction("IN")
        form.add_jurisdiction("IN")
        assert [j["country"] for j in form.jurisdictions] == ["IN"]

    def test_a_country_code_is_normalised(self, form) -> None:
        form.add_jurisdiction(" in ")
        assert [j["country"] for j in form.jurisdictions] == ["IN"]

    def test_sub_units_are_carried(self, form) -> None:
        """A Californian hospital sits under state and federal law; the state must survive."""
        form.add_jurisdiction("US", sub_units=["US-CA"])
        entry = form.jurisdictions[0]
        assert entry["country"] == "US"
        assert list(entry["sub_units"]) == ["US-CA"]


class TestItProducesADeclarationTheEngineAccepts:
    """The cut-over criterion, as far as a test can carry it."""

    def _filled(self, tmp_path: Path):
        from samanvaya.form import IntakeForm

        built = IntakeForm(working_file=tmp_path / "w.json")
        built.legal_name = "Example Ltd"
        built.author = "A. Adviser"
        built.add_jurisdiction("IN")
        for question in QUESTIONS:
            if question.kind == "bool":
                built.set(question.path, "Yes")
            elif question.kind in ("int", "float"):
                built.set(question.path, "10")
            elif question.kind == "str":
                built.set(question.path, "stated")
            elif question.kind == "list":
                built.set(question.path, "one, two")
        return built

    def test_the_declaration_validates(self, tmp_path: Path) -> None:
        from samanvaya.declaration import load

        built = self._filled(tmp_path)
        out = tmp_path / "declaration.json"
        built.save(out)
        declaration = load(out)
        assert declaration is not None

    def test_the_engine_runs_on_it(self, tmp_path: Path) -> None:
        from datetime import date

        from samanvaya.declaration import load
        from samanvaya.engine import run

        built = self._filled(tmp_path)
        out = tmp_path / "declaration.json"
        built.save(out)
        result = run(load(out), date(2027, 12, 1))
        assert result.all_findings, "the engine produced no findings at all"

    def test_a_mostly_empty_form_still_produces_a_valid_declaration(
        self, tmp_path: Path
    ) -> None:
        """An adviser who got three answers out of a client must still be able to run."""
        from datetime import date

        from samanvaya.declaration import load
        from samanvaya.engine import run
        from samanvaya.form import IntakeForm

        built = IntakeForm(working_file=tmp_path / "w.json")
        built.legal_name = "Example Ltd"
        built.author = "A. Adviser"
        built.add_jurisdiction("IN")
        out = tmp_path / "declaration.json"
        built.save(out)
        result = run(load(out), date(2027, 12, 1))
        assert result.all_findings

    def test_saving_without_an_organisation_name_is_refused(self, tmp_path: Path) -> None:
        """The schema requires it, and a refusal here beats a traceback at load time."""
        from samanvaya.form import IntakeForm

        built = IntakeForm(working_file=tmp_path / "w.json")
        built.author = "A. Adviser"
        built.add_jurisdiction("IN")
        with pytest.raises(Exception):
            built.save(tmp_path / "declaration.json")

    def test_saving_without_a_jurisdiction_is_refused(self, tmp_path: Path) -> None:
        from samanvaya.form import IntakeForm

        built = IntakeForm(working_file=tmp_path / "w.json")
        built.legal_name = "Example Ltd"
        built.author = "A. Adviser"
        with pytest.raises(Exception):
            built.save(tmp_path / "declaration.json")


class TestItGathersAndDoesNotAssess:
    BANNED = (
        "compliant", "non-compliant", "pass", "fail", "at risk", "safe",
        "violation", "breach of law", "you should", "we recommend",
        "satisfied", "gap", "unresolved",
    )

    def test_no_verdict_vocabulary_in_what_the_form_authors(self) -> None:
        import re

        from samanvaya.form import AUTHORED_TEXT

        assert AUTHORED_TEXT, "no authored strings were declared"
        surface = " ".join(AUTHORED_TEXT).lower()
        for word in self.BANNED:
            assert not re.search(rf"\b{re.escape(word)}\b", surface), (
                f"{word!r} appears in text the form authors"
            )

    def test_the_form_does_not_import_the_engine(self) -> None:
        """A form that can run the engine is a form that can show a verdict."""
        import inspect

        from samanvaya import form

        source = inspect.getsource(form)
        assert "from samanvaya.engine" not in source
        assert "import engine" not in source

    def test_it_reaches_no_verdict_colour(self) -> None:
        import inspect

        from samanvaya import form

        assert "_VERDICT" not in inspect.getsource(form)


class TestTheModuleFitsTheProductItIsPartOf:
    """Review findings, 2026-08-22. Green tests are necessary and not sufficient.

    Everything here passed its own acceptance test and was still wrong at the seam
    where this module meets the rest of the product. That seam is exactly what a test
    written against one module cannot see, so it is asserted here explicitly.
    """

    def test_it_raises_the_products_own_declaration_error(self, tmp_path: Path) -> None:
        """One `DeclarationError`, not two that share a name.

        `samanvaya.types.DeclarationError` is what `cli.main` catches by name to turn a
        bad declaration into `error: ...` and exit 2. A second class with the same name
        in this module is not caught by that clause, so the failure escapes as an
        unhandled traceback — in front of a client, at the moment the adviser tries to
        reopen a part-finished meeting.
        """
        from samanvaya.form import IntakeForm
        from samanvaya.types import DeclarationError

        broken = tmp_path / "broken.json"
        broken.write_text("{ this is not json")
        with pytest.raises(DeclarationError):
            IntakeForm.resume(broken)

    def test_there_is_only_one_declaration_error_class(self) -> None:
        from samanvaya import form, types

        local = getattr(form, "DeclarationError", None)
        if local is not None:
            assert local is types.DeclarationError, (
                "form.py defines its own DeclarationError, shadowing the product's"
            )

    def test_every_authored_message_is_reachable_by_name(self) -> None:
        """Messages referenced as `AUTHORED_TEXT[6]` are one insertion from being wrong.

        Positional lookup into a tuple of prose has no failure mode that a test notices:
        add a message at the top and every index below it silently shifts, so the user
        gets a fluent, confident, wrong sentence. Three entries in the first version of
        this tuple were already dead, which is the same rot one step earlier.
        """
        from samanvaya import form

        named = {
            value
            for key, value in vars(form).items()
            if key.isupper() and isinstance(value, str)
        }
        for message in form.AUTHORED_TEXT:
            assert message in named, (
                f"message reachable only by index, give it a name: {message!r}"
            )

    def test_no_authored_message_is_dead(self) -> None:
        """A message nobody can produce is either a missing branch or clutter."""
        import inspect

        from samanvaya import form

        source = inspect.getsource(form)
        for key, value in vars(form).items():
            if not (key.isupper() and isinstance(value, str)):
                continue
            if value not in form.AUTHORED_TEXT:
                continue
            assert source.count(key) > 1, f"{key} is defined and never used"

    def test_the_resume_failure_does_not_claim_to_be_a_save(
        self, tmp_path: Path
    ) -> None:
        """An adviser reopening a meeting must not be told the save failed.

        Wrong words in a legal tool are a correctness problem, not a polish one: the
        user acts on what the message says, and "cannot save" sends them looking for a
        disk problem when the file they opened is the thing that is broken.
        """
        from samanvaya.form import IntakeForm
        from samanvaya.types import DeclarationError

        broken = tmp_path / "broken.json"
        broken.write_text("{ this is not json")
        with pytest.raises(DeclarationError) as caught:
            IntakeForm.resume(broken)
        assert "save" not in str(caught.value).lower(), (
            f"a resume failure reported itself as a save failure: {caught.value}"
        )


class TestTheAutosaveCannotEatTheMeeting:
    """The crash-survival feature must not be the thing that loses the work.

    `autosave` ran `Path.write_text`, which truncates the file and then writes it. If
    the process dies in between — a closed lid, a battery, the exact crash this feature
    exists to survive — the working file is left half-written, and `resume` correctly
    refuses to open it. The feature would then have destroyed the two hours it was
    built to protect, and it would do it at the worst possible moment.

    A durable write is temp-file-then-rename: the rename is atomic, so the previous
    good file is either wholly replaced or wholly untouched. There is no state in which
    a reader sees half a declaration.
    """

    def _crash_midway(self, monkeypatch) -> None:
        """Make any file write truncate the target and then fail, as a real crash does."""
        from pathlib import Path as _Path

        original = _Path.write_text

        def truncating(self, data, *args, **kwargs):  # type: ignore[no-untyped-def]
            with open(self, "w", encoding="utf-8") as handle:
                handle.write(data[: len(data) // 2])
            raise OSError("simulated crash part-way through the write")

        monkeypatch.setattr(_Path, "write_text", truncating)
        return original

    def test_an_interrupted_autosave_leaves_the_previous_answers_intact(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from samanvaya.form import IntakeForm

        working = tmp_path / "working.json"
        form = IntakeForm(working_file=working)
        form.legal_name = "Example Ltd"
        form.author = "A. Adviser"
        form.add_jurisdiction("IN")

        first = _first("bool")
        form.set(first.path, "Yes")
        good = working.read_text()
        assert good, "nothing was autosaved to begin with"

        self._crash_midway(monkeypatch)
        second = _first("str")
        with pytest.raises(OSError):
            form.set(second.path, "stated")

        assert working.read_text() == good, (
            "an interrupted autosave overwrote the previous good working file"
        )

    def test_the_working_file_is_still_resumable_after_an_interrupted_write(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The property that actually matters: the adviser can still reopen it."""
        from samanvaya.form import IntakeForm

        working = tmp_path / "working.json"
        form = IntakeForm(working_file=working)
        form.legal_name = "Example Ltd"
        form.author = "A. Adviser"
        form.add_jurisdiction("IN")
        first = _first("bool")
        form.set(first.path, "Yes")

        self._crash_midway(monkeypatch)
        with pytest.raises(OSError):
            form.set(_first("str").path, "stated")
        monkeypatch.undo()

        recovered = IntakeForm.resume(working)
        assert recovered.get(first.path) is True
        assert recovered.legal_name == "Example Ltd"

    def test_no_partial_file_is_left_lying_beside_the_working_file(
        self, tmp_path: Path
    ) -> None:
        """A successful autosave leaves exactly one file, not a litter of temporaries."""
        from samanvaya.form import IntakeForm

        working = tmp_path / "working.json"
        form = IntakeForm(working_file=working)
        form.set(_first("bool").path, "Yes")
        form.set(_first("str").path, "stated")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["working.json"]


class TestClearingAFieldUnAnswersIt:
    """The screen and the model may never disagree about what the client said.

    Backspacing a number field to empty returned "That is not a whole number." and KEPT
    the previous value. The control on screen was blank, the model still held 7, and the
    declaration shipped the 7 — a declared fact that nobody declared, which is the exact
    failure this whole tool is built to prevent. Text and list answers already treated
    blank as "cleared"; numbers and yes/no did not.

    Blank means the user removed their answer. That is Not established, and it is not an
    error.
    """

    @pytest.mark.parametrize("kind", ["bool", "int", "float", "str", "list"])
    def test_clearing_returns_the_question_to_not_established(
        self, form, kind: str
    ) -> None:
        from samanvaya.form import NOT_ESTABLISHED

        question = _first(kind)
        seed = "7" if kind in ("int", "float") else ("Yes" if kind == "bool" else "x")
        assert form.set(question.path, seed) is None, f"could not seed a {kind}"
        assert form.set(question.path, "") is None, (
            f"clearing a {kind} field was reported as an error"
        )
        assert form.get(question.path) is NOT_ESTABLISHED, (
            f"a cleared {kind} field kept its old value"
        )

    def test_whitespace_only_is_also_cleared(self, form) -> None:
        """A field the user selected and typed a space into is a cleared field."""
        from samanvaya.form import NOT_ESTABLISHED

        question = _first("int")
        form.set(question.path, "7")
        assert form.set(question.path, "   ") is None
        assert form.get(question.path) is NOT_ESTABLISHED

    def test_a_cleared_answer_leaves_the_declaration(self, form) -> None:
        """Not just the in-memory value — the thing the engine reads."""
        form.legal_name = "Example Ltd"
        form.author = "A. Adviser"
        form.add_jurisdiction("IN")
        question = _first("int")
        form.set(question.path, "4242")
        assert "4242" in json.dumps(form.to_declaration())
        form.set(question.path, "")
        assert "4242" not in json.dumps(form.to_declaration()), (
            "a cleared answer was still in the declaration"
        )

    def test_clearing_still_decrements_the_count(self, form) -> None:
        question = _first("int")
        form.set(question.path, "7")
        assert form.total_progress().answered == 1
        form.set(question.path, "")
        assert form.total_progress().answered == 0

    def test_a_genuinely_bad_answer_is_still_refused(self, form) -> None:
        """Clearing is not a licence to accept nonsense — words are still not numbers."""
        from samanvaya.form import NOT_ESTABLISHED

        question = _first("int")
        assert form.set(question.path, "quite a lot") is not None
        assert form.get(question.path) is NOT_ESTABLISHED


class TestReopeningLosesNothing:
    """The working file is the FORM's state, not a declaration.

    It was built with `answers_to_declaration`, which is lossy by design: an answer
    whose path has no field on a block dataclass is dropped. Ten questions are in that
    position today, so reopening a meeting silently discarded eleven of eighty-three
    answers — the client had said them, the adviser had typed them, and they were gone.

    That was a specification error in the brief this module was built to, not a
    misreading of it. A declaration is what you PRODUCE at the end; it is the wrong
    container for work in progress, because it can only hold what the engine can
    consume. The working file now carries the form's own answers verbatim, and `resume`
    still opens a plain declaration written by the CLI interview, because an adviser
    who started in the terminal must be able to finish in the window.
    """

    def _answer_everything(self, form) -> int:
        form.legal_name = "Example Ltd"
        form.author = "A. Adviser"
        form.add_jurisdiction("IN")
        for question in QUESTIONS:
            raw = {
                "bool": "Yes",
                "int": "12",
                "float": "12",
                "str": "stated",
                "list": "one, two",
            }[question.kind]
            assert form.set(question.path, raw) is None, question.path
        return form.total_progress().answered

    def test_every_answer_survives_a_reopen(self, form, tmp_path: Path) -> None:
        from samanvaya.form import IntakeForm

        answered = self._answer_everything(form)
        assert answered == len(QUESTIONS)

        resumed = IntakeForm.resume(tmp_path / "working.json")
        assert resumed.total_progress().answered == answered, (
            f"reopening lost {answered - resumed.total_progress().answered} answers"
        )

    def test_each_individual_answer_comes_back_unchanged(
        self, form, tmp_path: Path
    ) -> None:
        """Not just the count — the values themselves."""
        from samanvaya.form import IntakeForm

        self._answer_everything(form)
        resumed = IntakeForm.resume(tmp_path / "working.json")
        for question in QUESTIONS:
            assert resumed.get(question.path) == form.get(question.path), question.path

    def test_an_orphan_question_survives_too(self, form, tmp_path: Path) -> None:
        """The ten questions the declaration cannot hold are still the client's answers.

        Whatever the maintainer decides about the schema, the form must not be the thing
        that loses them.
        """
        from samanvaya.form import IntakeForm
        from tests.test_question_homes import KNOWN_ORPHANS

        self._answer_everything(form)
        resumed = IntakeForm.resume(tmp_path / "working.json")
        for path in sorted(KNOWN_ORPHANS):
            assert resumed.get(path) == form.get(path), path

    def test_the_identity_fields_survive(self, form, tmp_path: Path) -> None:
        from samanvaya.form import IntakeForm

        self._answer_everything(form)
        resumed = IntakeForm.resume(tmp_path / "working.json")
        assert resumed.legal_name == "Example Ltd"
        assert resumed.author == "A. Adviser"
        assert [j["country"] for j in resumed.jurisdictions] == ["IN"]

    def test_a_declaration_written_by_the_cli_still_opens(
        self, tmp_path: Path
    ) -> None:
        """An adviser who started in the terminal must be able to finish in the window."""
        from samanvaya.form import IntakeForm

        source = json.loads((EXAMPLES / "01-india-saas-startup.json").read_text())
        target = tmp_path / "from_cli.json"
        target.write_text(json.dumps(source))

        resumed = IntakeForm.resume(target)
        assert resumed.total_progress().answered > 0
        assert resumed.legal_name == source["organisation"]["legal_name"]
