"""The application checking itself, inside the artefact that ships.

Authored BEFORE the implementation. Tests are not delegated.

Every test in this repository runs against the SOURCE TREE. The thing a user opens is a
PyInstaller bundle, and the gap between those two has bitten this project twice:

  - 2026-08-20: the app died on launch with `AttributeError: module 'tkinter.ttk' has no
    attribute 'Menu'` while all 589 tests passed, because none of them built a widget.
  - the fix for that was a launch gate in `build-app.sh` — start the binary, wait six
    seconds, require it still running. That proves the app OPENS. It clicks nothing.

So "the app starts" and "the app works" are still different claims, and the intake form
is the largest surface ever added to it: nine pages of widgets reached through a menu
item, in a frozen bundle whose import graph is computed by static analysis. If
`form_view` failed to bundle, the launch gate would pass and the crash would arrive the
first time an adviser chose File > New Intake Form, in front of a client.

`samanvaya.selftest` closes that. It builds every surface, reports what worked, and
never raises. `build-app.sh` runs it against the SIGNED BUNDLE and fails the build if
any surface is broken — so the artefact tests itself before it is installed on anything.

It is not a substitute for a person using the product. It answers one question only:
does every surface in this binary construct and run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestTheSurfaceListIsHonest:
    def test_it_names_the_surfaces_that_have_actually_broken(self) -> None:
        """Not an arbitrary list — each of these has failed, or is new and untested.

        The menu bar killed the 2026-08-20 build. The intake form is the newest and
        largest. The two PDF renderers are what actually reaches a client.
        """
        from samanvaya.selftest import SURFACES

        for needed in (
            "main_window",
            "menu_bar",
            "intake_form",
            "questionnaire_pdf",
            "conformance_report_pdf",
        ):
            assert needed in SURFACES, f"{needed} is not self-tested"

    def test_the_surfaces_are_declared_not_discovered(self) -> None:
        """A discovered list proves nothing: it cannot notice a surface that is missing."""
        from samanvaya.selftest import SURFACES

        assert isinstance(SURFACES, tuple)
        assert len(SURFACES) >= 5


class TestItRuns:
    def test_a_clean_run_reports_every_surface_ok(self, tmp_path: Path) -> None:
        from samanvaya.selftest import SURFACES, run_selftest

        report = run_selftest(workdir=tmp_path)
        assert report["ok"] is True, report
        for surface in SURFACES:
            assert report["surfaces"][surface]["ok"] is True, (
                f"{surface}: {report['surfaces'][surface].get('error')}"
            )

    def test_it_writes_a_json_report_when_asked(self, tmp_path: Path) -> None:
        """The build script reads this file. It must be parseable, not scraped from stdout."""
        from samanvaya.selftest import run_selftest

        target = tmp_path / "report.json"
        run_selftest(workdir=tmp_path, report_path=target)
        parsed = json.loads(target.read_text())
        assert parsed["ok"] is True
        assert "surfaces" in parsed

    def test_it_records_the_build_it_tested(self, tmp_path: Path) -> None:
        """A green report that does not say which build it came from proves nothing."""
        from samanvaya import __build__, __version__
        from samanvaya.selftest import run_selftest

        report = run_selftest(workdir=tmp_path)
        assert report["version"] == __version__
        assert report["build"] == __build__

    def test_it_never_raises_when_a_surface_is_broken(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A self-test that dies cannot report. It must catch and record instead.

        This is the whole reason it is not just a script that calls things: a crash in
        surface two would hide surfaces three, four and five.
        """
        import samanvaya.selftest as selftest

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated surface failure")

        monkeypatch.setattr(selftest, "_check_intake_form", explode)
        report = selftest.run_selftest(workdir=tmp_path)
        assert report["ok"] is False
        assert report["surfaces"]["intake_form"]["ok"] is False
        assert "simulated surface failure" in report["surfaces"]["intake_form"]["error"]

    def test_one_broken_surface_does_not_hide_the_others(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import samanvaya.selftest as selftest

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(selftest, "_check_menu_bar", explode)
        report = selftest.run_selftest(workdir=tmp_path)
        assert report["surfaces"]["menu_bar"]["ok"] is False
        assert report["surfaces"]["questionnaire_pdf"]["ok"] is True, (
            "a later surface was skipped because an earlier one failed"
        )


class TestItIsReachableFromTheFrozenBinary:
    """The bundle is `--windowed`: no stdin, no arguments a user would pass.

    An environment variable is the one channel that reaches it, which is why the build
    script uses one. It must never fire in ordinary use.
    """

    def test_main_runs_the_selftest_when_the_variable_is_set(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # Imported first ON PURPOSE. Without the self-test branch, `main()` falls
        # through to `mainloop()` and the test suite hangs forever instead of failing
        # — which is how this file cost five minutes the first time it was run.
        import samanvaya.selftest  # noqa: F401
        from samanvaya.gui import main

        target = tmp_path / "report.json"
        monkeypatch.setenv("SAMANVAYA_SELFTEST", str(target))
        code = main()
        assert code == 0
        assert json.loads(target.read_text())["ok"] is True

    def test_it_exits_non_zero_when_a_surface_is_broken(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The build must fail, not warn."""
        import samanvaya.selftest as selftest
        from samanvaya.gui import main

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(selftest, "_check_intake_form", explode)
        monkeypatch.setenv("SAMANVAYA_SELFTEST", str(tmp_path / "r.json"))
        # A window must never open here; if the branch is missing this raises rather
        # than entering the mainloop.
        monkeypatch.setattr(
            "samanvaya.gui.App", lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("main() reached the window instead of the self-test")
            )
        )
        assert main() != 0

    def test_main_does_not_run_the_selftest_by_default(self, monkeypatch) -> None:
        """An adviser opening the app must get the app, not a test harness."""
        import samanvaya.gui as gui

        monkeypatch.delenv("SAMANVAYA_SELFTEST", raising=False)
        called: list[str] = []
        monkeypatch.setattr(
            gui, "_run_selftest_and_exit", lambda path: called.append(path)
        )

        # Stop before the mainloop: we are asserting what main does NOT do.
        class _Stop(Exception):
            pass

        def refuse(*args: object, **kwargs: object) -> None:
            raise _Stop

        monkeypatch.setattr(gui, "App", refuse)
        with pytest.raises(_Stop):
            gui.main()
        assert called == [], "the self-test ran during a normal launch"


class TestItLeavesNothingBehind:
    def test_it_writes_only_inside_the_workdir(self, tmp_path: Path) -> None:
        """It renders real PDFs. They belong in a scratch folder, not the user's Desktop."""
        from samanvaya.selftest import run_selftest

        workdir = tmp_path / "scratch"
        workdir.mkdir()
        run_selftest(workdir=workdir)
        produced = list(workdir.rglob("*"))
        assert produced, "the self-test rendered nothing at all"
        for path in produced:
            assert workdir in path.parents or path.parent == workdir
