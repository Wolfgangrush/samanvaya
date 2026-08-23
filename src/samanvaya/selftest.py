"""The application checking itself, inside the artefact that ships.

Every test in this repository runs against the SOURCE TREE. The thing a user opens is a
PyInstaller bundle, and the gap between those two has bitten this project twice: on
2026-08-20 the app died on launch with `AttributeError: module 'tkinter.ttk' has no
attribute 'Menu'` while all 589 tests passed, because none of them built a widget. The
fix was a launch gate in `build-app.sh`: start the binary, wait six seconds, require it
still alive. That proves the app OPENS. It clicks nothing.

The intake form is nine pages of widgets reached through a menu item, in a frozen bundle
whose import graph is computed by static analysis. If `form_view` failed to bundle the
launch gate would pass and the crash would arrive the first time an adviser chose
File > New Intake Form, in front of a client. This module closes that gap: it builds
every surface the user can reach, reports what worked, and never raises. `build-app.sh`
runs it against the SIGNED BUNDLE and fails the build if any surface is broken, so the
artefact tests itself before it is installed on anything.

It is not a substitute for a person using the product. It answers one question only:
does every surface in this binary construct and run.
"""

from __future__ import annotations

import json
import tkinter
from datetime import date
from pathlib import Path
from typing import Any, Callable

from samanvaya import __build__, __version__
from samanvaya import engine as engine_module
from samanvaya import pdf_report, schema
from samanvaya.pdf_theme import Preparer
from samanvaya.questionnaire import render_questionnaire
from samanvaya.types import Declaration


# Every surface a user can reach. Declared, not discovered, because a discovered list
# cannot notice a surface that is missing. Each name is one of the per-surface check
# functions below; the tests monkeypatch those functions by name.
SURFACES: tuple[str, ...] = (
    "main_window",
    "menu_bar",
    "intake_form",
    "questionnaire_pdf",
    "conformance_report_pdf",
)


# The minimum declaration that exercises every code path the engine can take inside a
# frozen bundle: an organisation, one jurisdiction the engine has a pack for, and one
# category of data. Hard-coded rather than read from `examples/` because the frozen
# bundle has no `examples/` directory beside it. Validated through the same schema the
# CLI uses, so a future schema tightening cannot silently desync the self-test.
_MINIMAL_DECLARATION: dict[str, Any] = {
    "schema_version": "1.0",
    "declaration_author": "Self-test, samanvaya internal",
    "declaration_date": "2027-01-15",
    "organisation": {
        "legal_name": "Samanvaya Self-Test Limited",
        "legal_form": "private company limited by shares",
        "employee_count": 25,
        "annual_revenue_usd": 1_500_000,
        "consumer_count": 10_000,
        "is_public_authority": False,
        "is_healthcare_provider": False,
        "is_financial_institution": False,
        "is_educational_institution": False,
        "offers_services_to_children": False,
        "conducts_large_scale_monitoring": False,
        "processes_special_category_data": False,
        "share_of_revenue_from_selling_personal_data": 0.0,
    },
    "jurisdictions": [
        {"country": "GB", "sub_units": [], "sub_units_complete": True},
    ],
    "data_categories": ["name", "email address"],
    "purposes": ["fulfilment of customer orders"],
    "recipients": ["payment processor"],
    "security_safeguards": [
        {"control": "encryption in transit", "value": "TLS 1.2 or higher"},
    ],
}


def _check_main_window(workdir: Path) -> None:
    """Confirm the main window constructs and tears down without raising.

    A real Tk root, withdrawn so no display is required, then `samanvaya.gui.App`.
    The construction is what the 2026-08-20 build died on, so the test that exercises
    it here is what proves the artefact is buildable rather than just importable.
    """

    root = tkinter.Tk()
    try:
        root.withdraw()
        from samanvaya.gui import App

        App(root)
    finally:
        root.destroy()


def _check_menu_bar(workdir: Path) -> None:
    """Confirm the App built a menubar and every command in MENU_SPEC resolves.

    Two distinct checks because they fail differently: a missing menubar is a missing
    widget, while an unresolved command is a menu item that does nothing when clicked.
    """

    from samanvaya.gui import MENU_SPEC, App, _MENU_COMMANDS

    root = tkinter.Tk()
    try:
        root.withdraw()
        App(root)
        if not root.cget("menu"):
            raise AssertionError("the App built no menubar")
        for menu_spec in MENU_SPEC:
            for item in menu_spec.items:
                name = item.command
                if name is None or name.startswith("_builtin:"):
                    continue
                if name not in _MENU_COMMANDS:
                    raise AssertionError(
                        f"menu command {name!r} is declared in MENU_SPEC but not "
                        "registered in _MENU_COMMANDS"
                    )
    finally:
        root.destroy()


def _check_intake_form(workdir: Path) -> None:
    """Confirm the intake form opens through the menu handler and answers reach the model.

    The App is pointed at ``workdir`` so the working file the form autosaves lands
    inside the scratch folder rather than the user Desktop. ``_on_intake_form`` is
    the same call path the File > New Intake Form menu item takes, so a successful
    click on the menu is what this check proves.
    """

    from samanvaya.form_view import IntakeWindow
    from samanvaya.gui import App
    from samanvaya.interview import QUESTIONS

    root = tkinter.Tk()
    try:
        root.withdraw()
        app = App(root)
        app.out_dir_var.set(str(workdir))
        app._on_intake_form()
        if app.intake_window is None:
            raise AssertionError("_on_intake_form did not set app.intake_window")
        if not isinstance(app.intake_window, IntakeWindow):
            raise AssertionError(
                f"app.intake_window is {type(app.intake_window).__name__}, "
                "expected IntakeWindow"
            )
        bool_question = next(q for q in QUESTIONS if q.kind == "bool")
        message = app.intake_window.write(bool_question.path, "Yes")
        if message is not None:
            raise AssertionError(f"intake window refused a valid answer: {message}")
        stored = app.intake_window.form.get(bool_question.path)
        if stored is True:
            return
        raise AssertionError(
            f"writing through the intake window did not reach the model: "
            f"form.get({bool_question.path!r}) returned {stored!r}"
        )
    finally:
        root.destroy()


def _check_questionnaire_pdf(workdir: Path) -> None:
    """Confirm the blank questionnaire renders into workdir as a real PDF."""

    target = workdir / "questionnaire.pdf"
    render_questionnaire(target, Preparer())
    head = target.read_bytes()[:5]
    if head != b"%PDF-":
        raise AssertionError(
            f"questionnaire render wrote {head!r}, not the PDF magic header"
        )


def _check_conformance_report_pdf(workdir: Path) -> None:
    """Confirm the conformance report runs the engine and renders to PDF in workdir.

    The declaration is built in code, never loaded from disk: the frozen bundle has
    no `examples/` directory beside it.
    """

    declaration: Declaration = schema.validate(_MINIMAL_DECLARATION)
    as_at = date(2027, 12, 1)
    engine_result = engine_module.run(declaration, as_at)

    target = workdir / "report.pdf"
    pdf_report.render_pdf(engine_result, target, Preparer())
    head = target.read_bytes()[:5]
    if head != b"%PDF-":
        raise AssertionError(
            f"report render wrote {head!r}, not the PDF magic header"
        )


# Lookup built at call time so a test that does ``monkeypatch.setattr(selftest,
# "_check_intake_form", ...)`` is observed by the next run_selftest call.
_CHECKERS: dict[str, str] = {
    "main_window": "_check_main_window",
    "menu_bar": "_check_menu_bar",
    "intake_form": "_check_intake_form",
    "questionnaire_pdf": "_check_questionnaire_pdf",
    "conformance_report_pdf": "_check_conformance_report_pdf",
}


def run_selftest(
    *,
    workdir: Path,
    report_path: Path | None = None,
) -> dict[str, object]:
    """Run every surface check, return the structured report, never raise.

    Every surface is wrapped; a failure in surface two cannot hide surface three,
    four or five.
    """

    surfaces: dict[str, dict[str, object]] = {}
    overall_ok = True

    for surface in SURFACES:
        checker_name = _CHECKERS[surface]
        checker: Callable[[Path], None] = globals()[checker_name]
        entry: dict[str, object] = {"ok": False, "error": None}
        try:
            checker(workdir)
            entry["ok"] = True
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
            overall_ok = False
        surfaces[surface] = entry

    report: dict[str, object] = {
        "ok": overall_ok,
        "version": __version__,
        "build": __build__,
        "surfaces": surfaces,
    }

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))

    return report


__all__ = ["SURFACES", "run_selftest"]
