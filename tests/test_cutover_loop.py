"""The whole loop, through the real window: intake -> save -> engine -> report.

BMAD/08 build order, step 5: *"The whole loop run once by hand."* This is as far as a
test can carry that. It builds the actual Tk widgets, types answers into them through
the same commit path a click takes, saves a declaration, runs the engine on it, and
renders the PDF a client would receive. Nothing is stubbed and no JSON is hand-written.

What it cannot do is BMAD/08's cut-over criterion, which is deliberately about a person:

    Intake is done when the maintainer produces a conformance report for a real
    engagement WITHOUT EVER OPENING A JSON FILE OR A TERMINAL.

A test runs in a terminal by definition, and "a real engagement" is not something a
fixture can be. So this file proves the machinery joins up end to end; it does not prove
the product is usable, and it must never be quoted as if it did. The criterion is met
the first time a human sits in front of the window with a client and comes out the other
side with a PDF — and until that has happened once, this is built and not proven.
"""

from __future__ import annotations

from datetime import date
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


class TestTheLoopJoinsUp:
    def test_intake_to_report_without_touching_a_json_file(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Every step through the surfaces a user actually operates."""
        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        root = _root()
        try:
            from samanvaya.declaration import load
            from samanvaya.engine import run
            from samanvaya.gui import App
            from samanvaya.pdf_report import render_pdf
            from samanvaya.pdf_theme import Preparer

            # 1. The adviser opens the application and points it at a folder.
            app = App(root)
            app.out_dir_var.set(str(tmp_path))

            # 2. Clicks "New intake form". A real window opens over a real model.
            app._on_intake_form()
            intake = app.intake_window
            assert intake is not None, "no intake window was opened"

            # 3. Types the client's answers, moving between sections out of order the
            #    way a real conversation does.
            intake.form.legal_name = "Nirvana Health Private Limited"
            intake.form.author = "A. Adviser"
            intake.form.add_jurisdiction("IN")
            for title in reversed(list(intake.section_names)):
                intake.show_section(title)
            answered = 0
            for question in QUESTIONS:
                if question.kind == "bool":
                    assert intake.write(question.path, "Yes") is None
                elif question.kind in ("int", "float"):
                    assert intake.write(question.path, "12") is None
                elif question.kind == "str":
                    assert intake.write(question.path, "stated") is None
                else:
                    assert intake.write(question.path, "one, two") is None
                answered += 1
            assert intake.form.total_progress().answered == answered

            # 4. The meeting is autosaved as it goes, and survives being reopened.
            assert (tmp_path / "intake-working.json").is_file()
            app._on_intake_form()
            assert app.intake_window is not None
            assert app.intake_window.form.total_progress().answered == answered, (
                "reopening lost the meeting"
            )

            # 5. Saves the declaration from the window.
            declaration_path = tmp_path / "declaration.json"
            assert intake.save_to(declaration_path) is None

            # 6. The engine reads it and produces findings.
            result = run(load(declaration_path), date(2027, 12, 1))
            assert result.all_findings, "the engine produced nothing"

            # 7. And the client gets a PDF.
            report = tmp_path / "report.pdf"
            render_pdf(result, report, Preparer(firm="Example & Co, Advocates"))
            assert report.read_bytes()[:5] == b"%PDF-"
        finally:
            root.destroy()

    def test_the_india_consent_rail_runs_on_a_form_built_declaration(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The rail that had never executed, exercised through the real surface.

        A fully answered consent block used to crash the engine with a bare TypeError,
        and no example or fixture ever reached it because nothing in the product could
        produce a complete declaration. The form can. This asserts the path stays open.
        """
        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        root = _root()
        try:
            from samanvaya.declaration import load
            from samanvaya.engine import run
            from samanvaya.form import IntakeForm
            from samanvaya.form_view import IntakeWindow

            form = IntakeForm(working_file=tmp_path / "working.json")
            form.legal_name = "Nirvana Health Private Limited"
            form.author = "A. Adviser"
            form.add_jurisdiction("IN")
            window = IntakeWindow(root, form)
            for question in QUESTIONS:
                if question.section.lower().startswith("consent"):
                    assert window.write(question.path, "Yes") is None

            out = tmp_path / "declaration.json"
            assert window.save_to(out) is None
            result = run(load(out), date(2027, 12, 1))

            consent = [
                f
                for f in result.all_findings
                if "Sec 6" in (f.obligation.citation_pointer or "")
            ]
            assert consent, "no DPDP s.6 consent finding was produced"
        finally:
            root.destroy()

    def test_a_half_answered_meeting_still_produces_a_report(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The ordinary case. A client does not know most of it, and that is fine.

        Everything unanswered stays Not established and is reported as unresolved
        rather than guessed at, which is the honest result and the reason the form
        refuses to default anything.
        """
        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        root = _root()
        try:
            from samanvaya.declaration import load
            from samanvaya.engine import run
            from samanvaya.form import IntakeForm
            from samanvaya.form_view import IntakeWindow
            from samanvaya.types import ObligationResult

            form = IntakeForm(working_file=tmp_path / "working.json")
            form.legal_name = "Example Ltd"
            form.author = "A. Adviser"
            form.add_jurisdiction("IN")
            window = IntakeWindow(root, form)
            window.write(QUESTIONS[0].path, "Yes" if QUESTIONS[0].kind == "bool" else "x")

            out = tmp_path / "declaration.json"
            assert window.save_to(out) is None
            result = run(load(out), date(2027, 12, 1))
            assert result.all_findings
            assert any(
                f.result is ObligationResult.CONTESTED for f in result.all_findings
            ), "an almost-empty declaration reported no unresolved findings at all"
        finally:
            root.destroy()
