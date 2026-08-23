"""Acceptance tests for the parts that make this an application rather than a form.

Authored BEFORE the implementation, after the maintainer opened the built app on
2026-08-20 and found:
no menu bar, Cmd-plus and Cmd-minus did nothing, no Preferences, no Help, no guide, no
licence shown anywhere, and no privacy statement — in a tool whose entire subject is
privacy.

He was right, and the spec was wrong rather than the code: `BMAD/07-BMAD-SPEC-desktop-app.md`
put all of this under "v1 deferred". A window that can only do one thing and tells the user
nothing about itself is a script with a form attached. These are not extras.

Everything here is tested as DATA or PURE FUNCTIONS — a menu specification, text constants,
a scale calculation, a preferences round-trip — so none of it needs a display. Whether the
menu is wired to the window is checked by the maintainer opening it, which is how the
gap was found.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


class TestTheMenuBarExists:
    def test_there_is_a_menu_specification(self) -> None:
        from samanvaya.gui import MENU_SPEC

        assert MENU_SPEC, "no menus are defined at all"

    def test_the_expected_menus_are_present(self) -> None:
        from samanvaya.gui import MENU_SPEC

        titles = {m.title.lower() for m in MENU_SPEC}
        for needed in ("edit", "view", "help"):
            assert needed in titles, f"no {needed} menu; titles were {titles}"

    def test_text_size_is_reachable_from_the_keyboard(self) -> None:
        """The complaint that started this: Cmd-plus and Cmd-minus did nothing."""
        from samanvaya.gui import MENU_SPEC

        accelerators = {
            (item.accelerator or "").lower()
            for menu in MENU_SPEC
            for item in menu.items
        }
        joined = " ".join(accelerators)
        assert "+" in joined and "-" in joined, (
            f"no grow/shrink accelerators found; accelerators were {accelerators}"
        )
        assert any("0" in a for a in accelerators), "no reset-text-size accelerator"

    def test_edit_menu_carries_the_clipboard_items(self) -> None:
        """Without these, a lawyer cannot paste a path or copy an error message."""
        from samanvaya.gui import MENU_SPEC

        edit = next(m for m in MENU_SPEC if m.title.lower() == "edit")
        labels = " ".join(i.label.lower() for i in edit.items)
        for needed in ("cut", "copy", "paste", "select all"):
            assert needed in labels, f"Edit menu has no {needed!r}"

    def test_help_menu_offers_guide_licence_and_privacy(self) -> None:
        from samanvaya.gui import MENU_SPEC

        help_menu = next(m for m in MENU_SPEC if m.title.lower() == "help")
        labels = " ".join(i.label.lower() for i in help_menu.items)
        for needed in ("guide", "licence", "privacy"):
            assert needed in labels, f"Help menu has no {needed!r} entry"

    def test_every_menu_item_names_a_command_that_exists(self) -> None:
        """A menu entry wired to nothing is worse than no menu entry."""
        from samanvaya import gui

        for menu in gui.MENU_SPEC:
            for item in menu.items:
                if item.command is None:
                    continue  # separators
                assert hasattr(gui, item.command) or item.command.startswith("_builtin:"), (
                    f"{menu.title} > {item.label} points at {item.command!r}, which does not exist"
                )


class TestTextSizeActuallyScales:
    def test_a_larger_scale_gives_a_larger_size(self) -> None:
        from samanvaya.gui import scaled_size

        assert scaled_size(13, 1.5) > scaled_size(13, 1.0)

    def test_a_smaller_scale_gives_a_smaller_size(self) -> None:
        from samanvaya.gui import scaled_size

        assert scaled_size(13, 0.8) < scaled_size(13, 1.0)

    def test_the_scale_is_clamped_so_the_window_stays_usable(self) -> None:
        """Unbounded shrink makes the app unreadable; unbounded grow makes it unusable."""
        from samanvaya.gui import MAX_FONT_SCALE, MIN_FONT_SCALE, clamp_scale

        assert clamp_scale(99.0) == MAX_FONT_SCALE
        assert clamp_scale(0.01) == MIN_FONT_SCALE
        assert MIN_FONT_SCALE < 1.0 < MAX_FONT_SCALE

    def test_a_step_actually_changes_the_scale(self) -> None:
        from samanvaya.gui import step_scale

        assert step_scale(1.0, +1) > 1.0
        assert step_scale(1.0, -1) < 1.0

    def test_the_size_is_always_a_usable_integer(self) -> None:
        from samanvaya.gui import MAX_FONT_SCALE, MIN_FONT_SCALE, scaled_size

        for scale in (MIN_FONT_SCALE, 1.0, MAX_FONT_SCALE):
            size = scaled_size(13, scale)
            assert isinstance(size, int) and size >= 8, size


class TestPreferencesPersist:
    def test_defaults_load_when_nothing_is_saved(self, tmp_path: Path, monkeypatch) -> None:
        from samanvaya.gui import load_preferences

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        prefs = load_preferences()
        assert prefs.font_scale == 1.0

    def test_a_saved_preference_round_trips(self, tmp_path: Path, monkeypatch) -> None:
        from samanvaya.gui import Preferences, load_preferences, save_preferences

        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(tmp_path / "cfg"))
        save_preferences(Preferences(font_scale=1.4))
        assert load_preferences().font_scale == pytest.approx(1.4)

    def test_a_corrupt_preferences_file_does_not_stop_the_app(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from samanvaya.gui import load_preferences

        cfg = tmp_path / "cfg"
        cfg.mkdir(parents=True)
        (cfg / "preferences.json").write_text("{ not json")
        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(cfg))
        assert load_preferences().font_scale == 1.0

    def test_preferences_are_separate_from_the_letterhead(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Two files. A bad preference must never cost the user their letterhead."""
        from samanvaya.gui import Preferences, save_preferences
        from samanvaya.pdf_report import Preparer

        cfg = tmp_path / "cfg"
        monkeypatch.setenv("SAMANVAYA_CONFIG_DIR", str(cfg))
        Preparer(firm="Example & Co").save(cfg / "preparer.json")
        save_preferences(Preferences(font_scale=1.2))
        assert json.loads((cfg / "preparer.json").read_text())["firm"] == "Example & Co"
        assert (cfg / "preferences.json").is_file()


class TestTheAppExplainsItself:
    def test_the_licence_text_is_the_real_licence(self) -> None:
        """Not a paraphrase. The file on disk is what the user is shown."""
        from samanvaya.gui import LICENCE_TEXT

        on_disk = (REPO / "LICENSE").read_text()
        assert "MIT" in LICENCE_TEXT
        assert "WITHOUT WARRANTY OF ANY KIND" in LICENCE_TEXT.upper()
        distinctive = "Permission is hereby granted, free of charge"
        assert distinctive in on_disk and distinctive in LICENCE_TEXT

    def test_there_is_a_privacy_statement(self) -> None:
        """A privacy tool with no privacy statement is the joke that writes itself."""
        from samanvaya.gui import PRIVACY_TEXT

        assert len(PRIVACY_TEXT) > 200, "the privacy statement is a stub"

    def test_the_privacy_statement_names_what_is_stored_and_where(self) -> None:
        from samanvaya.gui import PRIVACY_TEXT

        lowered = PRIVACY_TEXT.lower()
        assert "preparer.json" in lowered or "letterhead" in lowered, (
            "the privacy statement does not say what the app stores"
        )
        for claim in ("network", "no telemetry", "your machine"):
            assert claim.split()[0] in lowered, f"privacy statement never mentions {claim!r}"

    def test_the_privacy_statement_does_not_overclaim(self) -> None:
        """It may say the APP sends nothing. It may not promise the user's own machine."""
        from samanvaya.gui import PRIVACY_TEXT

        for overclaim in ("guarantee", "completely secure", "cannot be breached"):
            assert overclaim not in PRIVACY_TEXT.lower(), overclaim

    def test_there_is_a_guide_that_explains_the_workflow(self) -> None:
        from samanvaya.gui import HELP_TEXT

        assert len(HELP_TEXT) > 400, "the guide is a stub"
        lowered = HELP_TEXT.lower()
        for topic in ("declaration", "letterhead"):
            assert topic in lowered, f"the guide never mentions {topic}"

    def test_the_guide_explains_what_unresolved_means(self) -> None:
        """The verdict a client will ask about, and the one most easily misread."""
        from samanvaya.gui import HELP_TEXT

        assert "unresolved" in HELP_TEXT.lower()

    def test_about_names_the_version_and_the_author(self) -> None:
        from samanvaya import __version__
        from samanvaya.gui import about_text

        text = about_text()
        assert __version__ in text
        assert "mahajan" in text.lower(), "the About box does not say who wrote it"

    def test_the_disclaimer_appears_in_the_about_box(self) -> None:
        from samanvaya.gui import about_text
        from samanvaya.types import DISCLAIMER

        assert DISCLAIMER[:40] in about_text()

    def test_none_of_the_explanatory_text_states_a_conclusion(self) -> None:
        """The same rule the window obeys, applied to the prose it now ships."""
        from samanvaya.gui import HELP_TEXT, PRIVACY_TEXT, about_text

        banned = ("you are compliant", "non-compliant", "guarantees compliance")
        for name, text in (
            ("HELP_TEXT", HELP_TEXT),
            ("PRIVACY_TEXT", PRIVACY_TEXT),
            ("about_text()", about_text()),
        ):
            for word in banned:
                assert word not in text.lower(), f"{word!r} in {name}"


class TestTheAboutBoxNamesItsAuthorAndItsBuild:
    """Who made it, and which copy of it this is.

    Both halves matter for different reasons. The attribution is the author's, stated
    the way an advocate signs work. The BUILD is what answers "which one is this?" when
    a client emails a PDF back three months later — which is the entire reason
    ``__build__`` exists separately from ``__version__``, and it was missing from the
    one screen a user would look at to find it.
    """

    def test_it_states_the_author(self) -> None:
        from samanvaya.gui import about_text

        assert "Rushikesh R. Mahajan" in about_text()

    def test_it_states_who_coded_verified_and_upgraded_it(self) -> None:
        from samanvaya.gui import about_text

        text = about_text().lower()
        for word in ("coded", "verified", "upgraded"):
            assert word in text, f"the About box does not say {word!r}"

    def test_it_carries_the_place(self) -> None:
        from samanvaya.gui import about_text

        assert "Nagpur" in about_text()

    def test_it_states_the_build_not_only_the_version(self) -> None:
        """A version string is carried by every rebuild. A build number identifies one."""
        from samanvaya import __build__, __version__
        from samanvaya.gui import about_text

        text = about_text()
        assert __version__ in text
        assert f"build {__build__}" in text, (
            "the About box names a version but not the build, so a user cannot say "
            "which artefact they are holding"
        )
