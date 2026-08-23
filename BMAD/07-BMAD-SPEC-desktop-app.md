# BMAD-SPEC — samanvaya desktop application

**Date:** 2026-08-20
**Owner:** the maintainer
**Discipline:** the maintainer owns every acceptance test and the verify.
**Domain agent (if any):** none
**Supersedes:** nothing. This is an ADDITIONAL surface over the existing engine; the CLI stays.

## B — BUILD

### Problem
The engine works and the CLI is correct, and neither is reachable by the person the tool was
built for. The user is an adviser, and the adviser is a lawyer. Asking a lawyer to open
Terminal, remember `--as-at`, `--out`, `--format` and four letterhead flags, and type a JSON
path is not a distribution problem that packaging can fix — a `.pkg` or a `.dmg` containing a
command-line binary still lands the user in a terminal. The observed failure is not that the
tool is hard to install. It is that after installing it the user does not know what to type.

### Solution shape
One window over the existing engine. The user picks a declaration file, fills a letterhead
once, picks an as-at date and an output folder, and presses one button. The window calls the
same `samanvaya.engine.run` and `samanvaya.pdf_report.render_pdf` the CLI calls, and shares
the same saved `Preparer` profile, so the two surfaces cannot disagree about what a report
says or whose name is on it.

### Inputs
- Declaration file: chosen through a native file dialog. JSON or YAML, as today.
- Letterhead: firm, adviser, email, phone. All optional. Persisted through the existing
  `Preparer.save` / `Preparer.load` at `${SAMANVAYA_CONFIG_DIR}/preparer.json`.
- As-at date: text field, ISO `YYYY-MM-DD`, defaulting to today with the same reproducibility
  warning the CLI prints.
- Output directory: chosen through a native directory dialog.
- Output formats: PDF and/or Markdown and/or JSON-lines, checkboxes, PDF ticked by default.

### Outputs
- The same report files the CLI writes, in the chosen directory, from the same code path.
- On-screen result: a short summary naming each file written, and the count of findings by
  verdict. NO verdict is rendered as a conclusion — the window shows counts and points at the
  file; it does not tell the user what their compliance position is.
- On failure: the same named, actionable message the CLI puts on STDERR, shown in the window.
  A traceback reaching the user is a defect.

### Components
- `src/samanvaya/gui.py` — the window. Tkinter, which is Python standard library.
- `entry_gui.py` — PyInstaller entry point, mirroring `entry.py`.
- `build-app.sh` — PyInstaller `--windowed` build producing `dist/samanvaya.app`, signed with
  the Developer ID Application certificate already on the maintainer's machine.
- `tests/test_gui.py` — acceptance tests over the window's LOGIC, not its pixels.

### Banned scope
1. **No new runtime dependency.** Tkinter is stdlib. A GUI toolkit fetched from PyPI would
   widen the supply chain of a tool whose entire claim is that it is offline and small.
2. **No network, no telemetry, no update check.** The offline tripwire must pass with the GUI
   imported.
3. **No verdict language in the window.** The window may say "13 findings: 3 satisfied,
   6 unresolved". It may never say "compliant", "non-compliant", "pass", "fail" or "at risk".
   The report is the adviser's work product; the window is a file dialog with a form.
4. **No editing of findings.** The window cannot alter what the engine produced.
5. **No declaration authoring.** `samanvaya interview` stays in the CLI for now; a
   83-question wizard is a separate build with its own spec.

### v1 ships (numbered)
1. File picker for the declaration, with the chosen path shown.
2. Letterhead form, four fields, prefilled from the saved profile, with a "remember" tick that
   calls `Preparer.save`.
3. As-at date field, defaulting to today, validated as ISO before the run.
4. Output directory picker, defaulting to the user's Desktop.
5. Format checkboxes: PDF (default on), Markdown, JSON-lines.
6. Generate button, which runs the engine off the UI thread so the window does not freeze.
7. Result panel: files written, and counts by verdict.
8. Error panel: the engine's own message, never a traceback.
9. A visible, non-dismissible line carrying `types.DISCLAIMER`.
10. `dist/samanvaya.app`, Developer ID signed, launching from Finder.

### v1 deferred
- The interview wizard. Windows and Linux builds. Drag-and-drop. Recent-files list.
- Notarisation, which needs App Store Connect credentials the maintainer has not created.

### CORRECTION, 2026-08-20 — this list was wrong

The first version of this spec deferred the menu bar, Help, About, the licence, the privacy
statement, Preferences and keyboard text-sizing. The maintainer opened the built application
and found, correctly, that there was nothing there: Cmd-plus did nothing, there was no menu,
no guide, no licence, and no privacy statement in a tool whose entire subject is privacy.

The error was in the spec, not the code. Those items are not features to be added later; they
are what distinguishes an application from a script with a form attached, and a user who
cannot find out what the software is, what it stores, or how to make the text bigger has been
handed something unfinished regardless of how well the engine behind it works.

They are therefore **v1**, covered by `tests/test_gui_chrome.py`:

11. A real menu bar: Edit (clipboard), View (text size), Help (Guide, Licence, Privacy).
12. Keyboard text scaling — Cmd-plus, Cmd-minus, Cmd-0 — applied through the named Tk fonts
    so every widget follows, clamped so the window stays usable, and persisted.
13. Preferences, stored in `preferences.json`, kept SEPARATE from the letterhead profile so a
    bad preference can never cost the user their letterhead.
14. Guide, Licence and Privacy windows carrying real text. The licence shown is the repository
    `LICENSE` verbatim, not a paraphrase.
15. An About box naming the version, the author, and the disclaimer.

The privacy statement earns its own note: it states what the application does and does not do
— no network of any kind, no telemetry, no update check, nothing leaving the machine, and the
two files it writes, named with their path — and it deliberately does NOT promise anything
about the security of the user's own machine, because that is not the application's to
promise.

### Build order (each step MUST precede the next)
1. Acceptance tests for the window's logic, authored by the maintainer, failing.
2. `gui.py` implementing them.
3. Full suite green, `mypy --strict` no worse than baseline.
4. `entry_gui.py` + `build-app.sh`; `.app` builds.
5. Launch the `.app` from Finder and produce a real PDF through it. Not "it built" — it ran.

### Test strategy per component (what each test must PROVE)
- **Preparer round-trip:** the letterhead the window saves is the letterhead the CLI loads.
  The two surfaces must not keep separate profiles.
- **Date validation:** a malformed as-at is refused with a message, and never reaches `run`.
- **Format selection:** ticking PDF alone writes exactly one file; ticking all three writes
  three, with the same stem.
- **No verdict vocabulary:** a source-level test greps the module for "compliant",
  "non-compliant", "pass", "fail", "at risk" and fails if any appears in a user-facing string.
  This is the same shape as the existing ranking-vocabulary test, and for the same reason.
- **Offline:** the tripwire is installed, the window's generate path is driven, and no socket
  is opened.
- **Errors surface:** a declaration containing a credential is refused, and the window shows
  the firewall's message rather than raising.
- **Threading:** generate runs off the UI thread and the result lands back on it.

## M — MEASURE
- The suite. The `.app` launching from Finder on a machine that has no Python installed.
- Real usage: the maintainer runs one real engagement end to end through the window rather
  than the CLI, and records whether he reached for the terminal at any point. If he does, the
  window has failed its purpose and the spec is wrong, not the code.

## D — DECIDE
### Falsifiers
1. If the window cannot produce, from a cold start by a person who has never seen it, the same
   PDF the CLI produces, it has not replaced the CLI for its intended user.
2. If any user-facing string states a compliance conclusion, the window has crossed from tool
   into advice and must be cut back.
3. If Tkinter cannot render the form acceptably on macOS, the no-new-dependency constraint is
   wrong and must be re-decided explicitly, not worked around.

### Cut-over criterion
The window replaces the CLI as the documented route for advisers when the maintainer has run
**one real engagement** through it without opening Terminal. Until then the README documents
both and recommends neither.
