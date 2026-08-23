"""The main window may GROW. It may not be mangled.

Authored 2026-08-22, when the intake form was about to be added.

Every feature so far has landed by putting something new on the one window an adviser
opens: the letterhead block, the format checkboxes, the questionnaire button. Each was
right on its own, and the failure mode of that pattern is well known — controls quietly
move, get renamed, get displaced by the newcomer, and one day the thing the user reached
for last week is gone. Nobody decides to do that; it happens one reasonable commit at a
time.

So this file pins the surface. It is a SUPERSET check, deliberately:

  - adding a control is allowed and always will be,
  - removing or renaming one fails the build and has to be argued for.

That is the exact shape of the rule: features get added, the UI does not get mangled.

The baseline below was MEASURED from the running window on 2026-08-22 (build 2), not
written from memory. If you are here because this test failed, the question to answer is
not "how do I update the baseline" — it is "did I mean to take that control away from
the user, and does the person who uses this agree". Update it deliberately, in the same
commit as the change, with the reason in the message.
"""

from __future__ import annotations

import pytest


#: Labelled chrome that existed before the intake form was added. Class plus visible
#: text, because that pair is what a user actually navigates by. Entry widgets are
#: excluded — their `text` is a Tk variable name, not a label — and are counted instead.
BASELINE_CONTROLS: frozenset[tuple[str, str]] = frozenset(
    {
        ("TButton", "Blank questionnaire (PDF)"),
        ("TButton", "Browse"),
        ("TButton", "Generate"),
        ("TCheckbutton", "JSON lines"),
        ("TCheckbutton", "Markdown"),
        ("TCheckbutton", "PDF"),
        ("TCheckbutton", "Remember this letterhead"),
        ("TLabel", "Adviser"),
        ("TLabel", "As-at"),
        ("TLabel", "Declaration"),
        ("TLabel", "Email"),
        ("TLabel", "Firm"),
        ("TLabel", "Output folder"),
        ("TLabel", "Phone"),
        ("TLabelframe", "Letterhead"),
        ("TLabelframe", "Output formats"),
    }
)

#: Seven text fields: declaration path, as-at, output folder, and the four letterhead
#: fields. A minimum rather than an exact count, so a new field is allowed and a lost
#: one is not.
BASELINE_ENTRY_COUNT: int = 7

#: Menu items that existed before. Same superset rule, per menu.
BASELINE_MENUS: dict[str, frozenset[str]] = {
    "File": frozenset({"Blank Questionnaire (PDF)"}),
    "Edit": frozenset({"Cut", "Copy", "Paste", "Select All"}),
    "View": frozenset(
        {"Increase Text Size", "Decrease Text Size", "Reset Text Size", "Preferences…"}
    ),
    "Help": frozenset(
        {"User Guide", "Licence", "Privacy Statement", "About Samanvaya"}
    ),
}


def _root():
    tkinter = pytest.importorskip("tkinter")
    try:
        root = tkinter.Tk()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable display: {exc}")
    root.withdraw()
    return root


def _inventory(widget, found: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Collect (class, visible text) for everything labelled in the MAIN window.

    The walk stops at a ``Toplevel``. In Tk a second window is still a CHILD of the
    root in the widget tree, so a naive crawl reports the User Guide's contents as
    though they had appeared on the main form. That would make this file assert the
    opposite of what it is for — it would fail every time a separate window opened
    correctly, and pass a change that grafted controls into the main grid as long as
    it also opened something. Stopping at the window boundary is what makes "the main
    window is unchanged" mean anything.
    """
    for child in widget.winfo_children():
        cls = child.winfo_class()
        if cls == "Toplevel":
            continue
        try:
            text = str(child.cget("text")).strip()
        except Exception:
            text = ""
        if text and cls != "TEntry":
            found.add((cls, text))
        _inventory(child, found)
    return found


def _count(widget, cls_name: str) -> int:
    """Count widgets of a class in the main window only — see :func:`_inventory`."""
    total = 0
    for child in widget.winfo_children():
        if child.winfo_class() == "Toplevel":
            continue
        if child.winfo_class() == cls_name:
            total += 1
        total += _count(child, cls_name)
    return total


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
    root = _root()
    from samanvaya.gui import App

    built = App(root)
    try:
        yield built
    finally:
        root.destroy()


class TestTheSurfaceOnlyGrows:
    def test_every_control_that_existed_still_exists(self, app) -> None:
        """Superset check: add freely, remove deliberately."""
        current = _inventory(app.root, set())
        missing = BASELINE_CONTROLS - current
        assert not missing, (
            "controls disappeared from the main window: "
            + ", ".join(sorted(f"{cls} {text!r}" for cls, text in missing))
        )

    def test_no_text_field_was_lost(self, app) -> None:
        found = _count(app.root, "TEntry")
        assert found >= BASELINE_ENTRY_COUNT, (
            f"only {found} text fields remain; there were {BASELINE_ENTRY_COUNT}"
        )

    def test_the_disclaimer_is_still_on_the_surface(self, app) -> None:
        """It is the contract between this tool and the adviser, and it is permanent.

        Called out separately from the inventory because it is the one control whose
        removal would be a doctrine failure rather than a usability one.
        """
        from samanvaya.types import DISCLAIMER

        texts = {text for _cls, text in _inventory(app.root, set())}
        assert any(DISCLAIMER[:40] in text for text in texts), (
            "the disclaimer is no longer displayed"
        )

    def test_every_menu_that_existed_still_exists(self) -> None:
        from samanvaya.gui import MENU_SPEC

        present = {menu.title: {item.label for item in menu.items} for menu in MENU_SPEC}
        for title, expected in BASELINE_MENUS.items():
            assert title in present, f"the {title} menu is gone"
            missing = expected - present[title]
            assert not missing, f"{title} menu lost: {sorted(missing)}"

    def test_the_generate_button_is_still_the_obvious_action(self, app) -> None:
        """Whatever else lands on this window, running the engine stays reachable."""
        assert app.generate_button.winfo_exists()
        assert str(app.generate_button.cget("text")) == "Generate"


class TestNewWindowsDoNotReachIntoTheMainOne:
    def test_the_main_window_is_unchanged_by_opening_another(self, app) -> None:
        """A second surface must be its own Toplevel, never grafted onto this grid.

        This is what stops "we added a feature" from meaning "the form you knew moved".
        """
        before = _inventory(app.root, set())
        app._open_text_window("User Guide", "some text")
        after = _inventory(app.root, set())
        assert after == before, (
            "opening a second window altered the main window's controls"
        )


class TestTheIntakeFormLandsWithoutDisturbingAnything:
    """BMAD/08 part B arriving on the main window, held to the rule above.

    The form is 83 questions over nine scrolling pages. It is the largest thing this
    product has ever put in front of a user, and the whole point of this file is that
    the window an adviser already knows does not change shape because of it.
    """

    def test_the_menu_offers_the_intake_form(self) -> None:
        from samanvaya.gui import _MENU_COMMANDS, MENU_SPEC

        commands = {
            item.command
            for menu in MENU_SPEC
            for item in menu.items
            if item.command and not item.command.startswith("_builtin:")
        }
        assert "open_intake_form" in commands
        assert "open_intake_form" in _MENU_COMMANDS

    def test_opening_it_does_not_alter_the_main_window(self, app, tmp_path) -> None:
        """The rule, applied to the biggest feature yet: it is its own window."""
        app.out_dir_var.set(str(tmp_path))
        before = _inventory(app.root, set())
        app._on_intake_form()
        after = _inventory(app.root, set())
        assert after == before, "the intake form changed the main window's controls"

    def test_it_opens_as_a_separate_window(self, app, tmp_path) -> None:
        app.out_dir_var.set(str(tmp_path))
        before = sum(
            1 for c in app.root.winfo_children() if c.winfo_class() == "Toplevel"
        )
        app._on_intake_form()
        after = sum(
            1 for c in app.root.winfo_children() if c.winfo_class() == "Toplevel"
        )
        assert after == before + 1, "no separate window was opened"

    def test_a_bad_output_folder_is_reported_not_raised(self, app, tmp_path) -> None:
        """A traceback in front of a client is not an error message."""
        app.out_dir_var.set(str(tmp_path / "does" / "not" / "exist"))
        app._on_intake_form()  # must not raise

    def test_it_resumes_a_part_finished_meeting(self, app, tmp_path) -> None:
        """Reopening must continue the meeting, not silently start a new one.

        This is the requirement that makes the autosave worth having. Without it the
        crash-safe working file is written and never read.
        """
        from samanvaya.form import IntakeForm
        from samanvaya.interview import QUESTIONS

        question = next(q for q in QUESTIONS if q.kind == "bool")
        seeded = IntakeForm(working_file=tmp_path / "intake-working.json")
        seeded.legal_name = "Example Ltd"
        seeded.author = "A. Adviser"
        seeded.add_jurisdiction("IN")
        seeded.set(question.path, "Yes")

        app.out_dir_var.set(str(tmp_path))
        app._on_intake_form()
        assert app.intake_window is not None
        assert app.intake_window.form.get(question.path) is True, (
            "reopening started a blank form over a part-finished meeting"
        )

    def test_the_secondary_actions_share_one_row(self, app) -> None:
        """One primary action, the rest grouped — not a growing stack of wide bars.

        Three full-width buttons stacked is how a form stops having a shape. Generate
        stays the obvious click; everything else sits together beside it.
        """
        assert app.questionnaire_button.winfo_parent() == (
            app.intake_button.winfo_parent()
        ), "the secondary buttons are not grouped together"
        assert app.generate_button.winfo_parent() != (
            app.questionnaire_button.winfo_parent()
        ), "the primary action was demoted into the secondary row"
