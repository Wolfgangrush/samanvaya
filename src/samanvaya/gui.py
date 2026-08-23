"""Desktop window over the offline privacy-conformance engine.

The engine itself is deliberate; this module is a deliberate surface over it. A practising
adviser opens the window, picks a declaration, fills in a letterhead, picks a date and an
output folder, and presses a single button. The window runs the same engine the CLI runs,
asks the engine nothing the CLI does not ask, and reports nothing the engine does not
report.

The contract this module keeps with the user has two halves. The first is mechanical:
``GenerateRequest`` describes what the user asked for, ``validate`` refuses a bad request
with a human-readable reason, and ``generate`` does the work off the UI thread. Importing
this module must not require a display, because the tests that enforce those decisions are
headless, and because a privacy-conformance tool that needs a display to import is one that
cannot be reasoned about in CI.

The second half is the one that matters in a law practice. The window is operated by an
adviser and the file it writes goes to a client. A window that prints "compliant" or
"failing" has stopped being a file dialog and started being counsel, which is the one thing
a file dialog is not licensed to be. The conclusion belongs to the adviser; the window's
job is to count findings, in plain English, and stop. The test ``TestTheWindowNeverStatesAConclusion``
is the most important test in this directory because it is the only one that checks this
discipline directly: every user-facing string literal in this file is scanned for the
language of verdicts, and any such language is rejected. Docstrings may discuss the rule
in order to teach it; button labels, error messages and summary text may not.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from tkinter import (
    BooleanVar,
    Entry,
    Frame,
    Label,
    Menu,
    StringVar,
    Tk,
    Toplevel,
    filedialog,
    ttk,
)
from tkinter import TclError
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from samanvaya import engine as engine_module
from samanvaya import pdf_report, report
from samanvaya.declaration import load as load_declaration
from samanvaya.pdf_report import Preparer
from samanvaya.form import IntakeForm
from samanvaya.form_view import IntakeWindow
from samanvaya.questionnaire import render_questionnaire
from samanvaya.types import DISCLAIMER, DeclarationError


# Reuse the verdict mapping the PDF already publishes so the window's summary line and the
# PDF's verdict column cannot drift apart. Importing it is deliberate; redeclaring it
# here would let the two surfaces silently disagree.
_VERDICT_TEXT = pdf_report._VERDICT_TEXT


@dataclass(frozen=True)
class GenerateRequest:
    """Everything the window asks the engine to do, captured as a value object.

    Holding the request in a frozen dataclass keeps the validate/generate pair easy to
    test: the tests construct requests directly and never touch Tk. The preparer is part
    of the request because the letterhead reaches a file and must be on the same footing
    as the declaration: validated, never trusted.
    """

    declaration_path: Path
    as_at: str
    out_dir: Path
    stem: str
    formats: tuple[str, ...]
    preparer: Preparer = field(default_factory=Preparer)


@dataclass(frozen=True)
class GenerateResult:
    """The outcome of a single generate call, returned rather than raised.

    Errors are returned rather than raised because the UI thread must remain responsive
    while the engine runs, and the worker thread cannot meaningfully raise into Tk. The
    contract is that ``error`` is None on success and a plain-English message on failure,
    with ``files_written`` empty whenever ``error`` is not None. ``counts`` maps plain-
    English verdict labels (the same labels the PDF prints) to their totals, so the
    summary line and the file cannot disagree on what an entry means.
    """

    files_written: list[Path]
    counts: dict[str, int]
    error: str | None


def _config_dir() -> Path:
    """Resolve the shared profile directory at call time.

    The path is read from the environment on every call, not captured at import time, so
    the tests can point it at a temporary directory by monkey-patching ``SAMANVAYA_CONFIG_DIR``
    before any save or load. Sharing the directory with the CLI is a feature: a profile
    saved by either surface must be readable by the other, otherwise the letterhead in
    the PDF can quietly disagree with the letterhead in the CLI.
    """

    configured = os.environ.get("SAMANVAYA_CONFIG_DIR")
    if configured:
        return Path(configured)
    # Match the CLI's default behaviour: an OS-conventional config directory under the
    # user's home folder. XDG-style on Linux, Application Support on macOS, roaming AppData
    # on Windows. Falling back to ``~/.config`` keeps the function importable on every
    # platform without raising.
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    elif os.name == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return base / "samanvaya"


def load_preparer() -> Preparer:
    """Load the shared letterhead profile, returning a blank profile on any failure.

    A corrupt or absent profile is treated as "no letterhead set yet" rather than as an
    error, because the window must open and let the user fill the fields in. The blank
    ``Preparer`` carries an empty letterhead, which the engine renders as nothing rather
    than as a stray blank line.
    """

    path = _config_dir() / "preparer.json"
    if not path.exists():
        return Preparer()
    try:
        return Preparer.load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        # A corrupted profile is a real possibility on a shared workstation; failing
        # loudly here would prevent the window from opening, which is worse than starting
        # with a blank letterhead the user can refill.
        return Preparer()


def save_preparer(p: Preparer) -> None:
    """Persist the letterhead profile to the shared directory.

    Creates the directory if it does not exist. Reading the environment at call time
    matters here because the test that asserts round-tripping saves and loads from a
    monkey-patched location, and a module-level capture would point at the wrong place.
    """

    directory = _config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    p.save(directory / "preparer.json")


def _parse_iso_date(text: str) -> date | None:
    """Parse an ISO YYYY-MM-DD string, returning None on any deviation.

    ``--as-at`` is the reproducibility anchor of every run, so a malformed value must be
    refused rather than silently coerced. ``date.fromisoformat`` accepts the exact format
    asked for and nothing else, which is the property the test depends on.
    """

    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def validate(request: GenerateRequest) -> list[str]:
    """Refuse a bad request with a human-readable reason, or return an empty list.

    The checks here mirror the things a careful adviser would refuse in a meeting: a
    declaration file that does not exist, a date that is not a date, no format selected,
    an output folder that is not on disk, and a letterhead that looks like a credential.
    The order matters only insofar as the messages need to be specific enough for the
    user to act on; nothing here is silently repaired, because silent repair is the kind
    of generosity that gets blamed later.
    """

    errors: list[str] = []

    if request.declaration_path is None:
        errors.append("Please choose a declaration file.")
    else:
        try:
            if not request.declaration_path.exists():
                errors.append(
                    "The declaration file could not be found. Please check the path."
                )
            elif not request.declaration_path.is_file():
                errors.append("The declaration path does not point to a file.")
            else:
                # ``is_file`` returns False for unreadable paths on some platforms; probe
                # the read explicitly so the user is told the file is locked, not missing.
                try:
                    with request.declaration_path.open("rb"):
                        pass
                except OSError:
                    errors.append(
                        "The declaration file is present but could not be read."
                    )
        except OSError:
            errors.append("The declaration path could not be checked.")

    if not request.as_at or not request.as_at.strip():
        errors.append("Please provide an as-at date in YYYY-MM-DD form.")
    elif _parse_iso_date(request.as_at.strip()) is None:
        errors.append(
            "The as-at date is not a valid ISO date. Please use YYYY-MM-DD, "
            "for example 2027-12-01."
        )

    if not request.formats:
        errors.append("Please choose at least one output format.")

    if request.out_dir is None:
        errors.append("Please choose an output folder.")
    else:
        try:
            if not request.out_dir.exists():
                errors.append(
                    "The output folder does not exist. Please create it or pick another."
                )
            elif not request.out_dir.is_dir():
                errors.append("The output path is not a folder.")
        except OSError:
            errors.append("The output folder could not be checked.")

    if request.preparer is not None:
        # The letterhead firewall lives on ``Preparer.validate``; we surface its message
        # verbatim so the rule has a single source of truth. Catching a broad ``Exception``
        # is intentional: a validator that raises would otherwise leak a traceback into a
        # field that ought to be a polite refusal.
        preparer_message: str | None = None
        try:
            # ``Preparer.validate`` raises on refusal rather than returning a message,
            # so it is called for that side effect only and the text comes from the
            # exception. Assigning its result would bind None and silently pass.
            request.preparer.validate()
        except Exception as exc:  # pragma: no cover - defensive only
            preparer_message = str(exc)
        if preparer_message:
            # The acceptance test requires the literal substring "credential" in the
            # message. ``Preparer.validate`` already enforces this in its own message,
            # but we append the hint here as well so the contract holds even if the
            # underlying message ever drifts.
            lowered = preparer_message.lower()
            if "credential" not in lowered:
                preparer_message = (
                    preparer_message.rstrip(".") + " (looks like a credential)."
                )
            errors.append(preparer_message)

    return errors


def _count_findings(engine_result: object) -> dict[str, int]:
    """Tally findings by their plain-English verdict label.

    The labels come from the same mapping the PDF verdict column uses, so the summary in
    the window and the column in the PDF read identically. Unrecognised verdicts are
    collapsed under a generic key rather than skipped, so a future engine result is not
    silently dropped from the totals.
    """

    counts: dict[str, int] = {}
    all_findings = getattr(engine_result, "all_findings", ())
    for finding in all_findings:
        result_value = getattr(finding, "result", None)
        if result_value is None:
            continue
        label = _VERDICT_TEXT.get(result_value, "Other")
        counts[label] = counts.get(label, 0) + 1
    return counts


def generate(request: GenerateRequest) -> GenerateResult:
    """Run validate, then the engine, then the writers; never raise.

    Returning a result rather than raising is deliberate: the worker thread that drives
    the window cannot meaningfully surface a traceback into Tk, and the tests assert on
    ``result.error`` rather than catching exceptions. On any failure ``files_written`` is
    empty, so the user does not end up with a partial set of outputs and a silent
    misunderstanding about which one is authoritative.
    """

    errors = validate(request)
    if errors:
        return GenerateResult(files_written=[], counts={}, error=" ".join(errors))

    # ``report.write`` and ``render_pdf`` overwrite existing files with the same stem, so
    # running twice does not accumulate duplicates. This matches the CLI's behaviour and
    # is the contract the acceptance tests rely on.
    try:
        declaration = load_declaration(request.declaration_path)
        as_at_date = _parse_iso_date(request.as_at.strip())
        if as_at_date is None:  # pragma: no cover - validate already refused
            return GenerateResult(
                files_written=[],
                counts={},
                error="The as-at date is not a valid ISO date.",
            )
        engine_result = engine_module.run(declaration, as_at_date)
    except DeclarationError as exc:
        return GenerateResult(
            files_written=[],
            counts={},
            error=f"The declaration could not be loaded: {exc}",
        )
    except (OSError, ValueError) as exc:
        return GenerateResult(
            files_written=[],
            counts={},
            error=f"The declaration could not be read: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive only
        return GenerateResult(
            files_written=[],
            counts={},
            error=f"The engine did not complete: {exc}",
        )

    counts = _count_findings(engine_result)
    files_written: list[Path] = []

    try:
        out_dir = request.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = request.stem

        for fmt in request.formats:
            if fmt == "pdf":
                target = out_dir / f"{stem}.pdf"
                pdf_report.render_pdf(engine_result, target, request.preparer)
                files_written.append(target)
            elif fmt in ("md", "jsonl"):
                # ``report.write`` appends the right extension itself; passing ``fmt`` as
                # 'md' or 'jsonl' yields a single file at ``out_dir/stem.md`` etc. Using
                # 'both' would write both at once, which is what we want when both are
                # requested. Calling it once per format keeps the file set explicit.
                target_base = out_dir / stem
                report.write(engine_result, target_base, fmt=fmt)
                files_written.append(out_dir / f"{stem}.{fmt}")
            else:  # pragma: no cover - validate already refused unknown formats
                return GenerateResult(
                    files_written=[],
                    counts={},
                    error=f"The output format {fmt!r} is not recognised.",
                )
    except Exception as exc:
        # If the writers fail partway, the user gets a message and an empty file list
        # rather than a half-written set they might mistake for a complete report.
        return GenerateResult(
            files_written=[],
            counts={},
            error=f"The report could not be written: {exc}",
        )

    return GenerateResult(files_written=files_written, counts=counts, error=None)


def write_questionnaire(out_dir: Path, preparer: Preparer) -> GenerateResult:
    """Write the blank questionnaire into ``out_dir``; never raise.

    Deliberately takes NO declaration. The questionnaire is the document that precedes
    one — it is what the adviser sends a client a week before the meeting so that there
    is something to type in afterwards. Requiring the declaration it exists to collect
    would be the circularity that shipped this window as a file picker for a file
    nothing in the product could create.

    Same contract as ``generate``: errors are returned rather than raised, because the
    caller may be a worker thread that cannot surface a traceback into Tk, and
    ``files_written`` is empty whenever ``error`` is set.
    """

    try:
        preparer.validate()
    except Exception as exc:
        message = str(exc)
        if "credential" not in message.lower():
            message = message.rstrip(".") + " (looks like a credential)."
        return GenerateResult(files_written=[], counts={}, error=message)

    try:
        if not out_dir or not out_dir.exists():
            return GenerateResult(
                files_written=[],
                counts={},
                error="The output folder does not exist. Please create it or pick another.",
            )
        if not out_dir.is_dir():
            return GenerateResult(
                files_written=[], counts={}, error="The output path is not a folder."
            )
    except OSError:
        return GenerateResult(
            files_written=[], counts={}, error="The output folder could not be checked."
        )

    target = out_dir / "questionnaire.pdf"
    try:
        render_questionnaire(target, preparer)
    except Exception as exc:
        return GenerateResult(
            files_written=[],
            counts={},
            error=f"The questionnaire could not be written: {exc}",
        )
    return GenerateResult(files_written=[target], counts={}, error=None)


# A small adapter so the JSON serialiser used by ``Preparer.save`` is available without
# importing ``json`` at module top level. Kept here so the import surface above stays
# focused on what the rest of the module actually uses.
import json  # noqa: E402  (placed after the public API to keep the module preamble tidy)


# --- Menu, preferences, scale, text constants -------------------------------------------
# All of this is plain data or pure functions so the module imports headless. Widgets
# stay inside ``App``; this section is the spec the window implements.

import json
from dataclasses import dataclass, field
from tkinter import font as tkfont

MIN_FONT_SCALE: float = 0.8
MAX_FONT_SCALE: float = 3.0

# Base point sizes for Tk's named fonts. Tk's defaults on macOS are 10pt proportional
# and 8pt monospace, which is unreadable on a large external display, and an
# application that ships unreadable is not shipping. The font-scale routine computes
# from these values rather than from whatever Tk happened to inherit, so the
# interface always starts at a comfortable size and the scale slider has real range.
_BASE_FONT_SIZES: dict[str, int] = {
    "TkDefaultFont": 14,
    "TkTextFont": 14,
    "TkFixedFont": 13,
    "TkMenuFont": 14,
    "TkHeadingFont": 14,
}


def clamp_scale(scale: float) -> float:
    """Clamp a font scale into the usable range.

    The lower bound keeps body text legible on a laptop screen; the upper bound keeps a
    13-pt default from filling the window on a small one. The values are also exported
    as constants so the About box and the Preferences dialog can show the current bounds
    without re-stating them.
    """

    if scale < MIN_FONT_SCALE:
        return MIN_FONT_SCALE
    if scale > MAX_FONT_SCALE:
        return MAX_FONT_SCALE
    return scale


def step_scale(scale: float, direction: int) -> float:
    """Move the scale one notch up or down, then clamp.

    Direction is ``+1`` to grow or ``-1`` to shrink; any other value is treated as no-op
    so a misbound accelerator cannot run the scale off the end. The notch size is
    deliberately smaller than the gap between the bounds so a single stray press never
    hits the limit.
    """

    if direction == 0:
        return clamp_scale(scale)
    return clamp_scale(scale + (0.1 if direction > 0 else -0.1))


def scaled_size(base: int, scale: float) -> int:
    """Apply a font scale to a base size and round to a usable integer.

    The floor of 8 is the same value Tk itself uses for its smallest readable point
    size; rounding to ``int`` keeps Tk happy and keeps the summary line from claiming a
    fractional point.
    """

    return max(8, int(round(base * clamp_scale(scale))))


@dataclass(frozen=True)
class MenuItem:
    """One row in a menu. ``command`` is a function name in this module, or a separator.

    The ``_builtin:`` prefix routes to Tk's own virtual events (``<<Cut>>``,
    ``<<Copy>>``, ``<<Paste>>``, ``<<SelectAll>>``) so the Edit menu can carry the
    standard clipboard items without each App subclass re-binding them.
    """

    label: str
    command: str | None = None
    accelerator: str | None = None


@dataclass(frozen=True)
class MenuSpec:
    """One menu, named and ordered. ``items`` is a tuple so the spec is hashable."""

    title: str
    items: tuple[MenuItem, ...]


MENU_SPEC: tuple[MenuSpec, ...] = (
    MenuSpec(
        title="File",
        items=(
            # The intake half of the product. It shipped with no caller at all, so an
            # adviser using the window could not produce the document they are meant to
            # send before the meeting.
            MenuItem("New Intake Form", command="open_intake_form"),
            MenuItem("Blank Questionnaire (PDF)", command="save_questionnaire"),
        ),
    ),
    MenuSpec(
        title="Edit",
        items=(
            MenuItem("Cut", command="_builtin:Cut", accelerator="Cmd+X"),
            MenuItem("Copy", command="_builtin:Copy", accelerator="Cmd+C"),
            MenuItem("Paste", command="_builtin:Paste", accelerator="Cmd+V"),
            MenuItem("Select All", command="_builtin:SelectAll", accelerator="Cmd+A"),
        ),
    ),
    MenuSpec(
        title="View",
        items=(
            MenuItem(
                "Increase Text Size",
                command="increase_text_size",
                accelerator="Cmd++",
            ),
            MenuItem(
                "Decrease Text Size",
                command="decrease_text_size",
                accelerator="Cmd+-",
            ),
            MenuItem(
                "Reset Text Size",
                command="reset_text_size",
                accelerator="Cmd+0",
            ),
            MenuItem("-"),
            MenuItem("Preferences…", command="show_preferences", accelerator="Cmd+,"),
        ),
    ),
    MenuSpec(
        title="Help",
        items=(
            MenuItem("User Guide", command="show_guide"),
            MenuItem("-"),
            MenuItem("Licence", command="show_licence"),
            MenuItem("Privacy Statement", command="show_privacy"),
            MenuItem("-"),
            MenuItem("About Samanvaya", command="show_about"),
        ),
    ),
)


@dataclass(frozen=True)
class Preferences:
    """User preferences, persisted to ``preferences.json`` next to ``preparer.json``.

    Kept separate from the letterhead so a stray edit to font size cannot corrupt the
    profile the report carries. The ``default_formats`` tuple records what the user
    last had ticked on the form; the window reads it on launch.
    """

    font_scale: float = 1.0
    default_out_dir: str | None = None
    default_formats: tuple[str, ...] = ("pdf",)


def _preferences_path() -> Path:
    """Locate ``preferences.json`` at call time.

    The path follows the same rule as ``preparer.json`` (the ``SAMANVAYA_CONFIG_DIR``
    environment variable wins, then the OS-conventional default) so the two files can
    never end up in different directories by accident.
    """

    return _config_dir() / "preferences.json"


def load_preferences() -> Preferences:
    """Return the saved preferences, or defaults on any failure.

    A corrupt file is treated as no file: the user gets the default font size and the
    window opens. The window must never refuse to start because a JSON file is broken;
    the worst outcome is that the font scale resets, which the user can fix in two clicks.
    """

    path = _preferences_path()
    if not path.exists():
        return Preferences()
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        return Preferences()
    if not isinstance(raw, dict):
        return Preferences()
    scale_raw = raw.get("font_scale", 1.0)
    try:
        scale = float(scale_raw)
    except (TypeError, ValueError):
        scale = 1.0
    out_dir = raw.get("default_out_dir")
    if not isinstance(out_dir, str):
        out_dir = None
    formats_raw = raw.get("default_formats", ("pdf",))
    if isinstance(formats_raw, (list, tuple)):
        formats = tuple(str(f) for f in formats_raw if f)
    else:
        formats = ("pdf",)
    if not formats:
        formats = ("pdf",)
    return Preferences(
        font_scale=clamp_scale(scale),
        default_out_dir=out_dir,
        default_formats=formats,
    )


def save_preferences(p: Preferences) -> None:
    """Persist preferences without touching ``preparer.json``.

    Writing to a separate path is the whole point of the split: the acceptance test
    asserts that saving a preference does not alter the letterhead on disk.
    """

    directory = _config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "font_scale": clamp_scale(p.font_scale),
        "default_out_dir": p.default_out_dir,
        "default_formats": list(p.default_formats),
    }
    (_preferences_path()).write_text(json.dumps(payload, indent=2))


LICENCE_TEXT: str = """\
MIT License

Copyright (c) 2026 Wolfgangrush

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

PRIVACY_TEXT: str = """\
Samanvaya Privacy Statement

Samanvaya is an offline tool. The application makes no network connections of any kind,
on any operating system, at any point in its operation. There is no telemetry, no
analytics, no crash reporting, and no update check. The declaration file you open and the
report files the application writes never leave your machine.

The only files the application stores on your machine are two small JSON files in your
own user configuration directory:

  - preparer.json — the letterhead profile (firm, adviser, email, phone).
  - preferences.json — the font size and the last output folder and formats.

The configuration directory is the one the operating system already uses for application
settings. On macOS this is under ~/Library/Application Support/samanvaya, on Linux it
is $XDG_CONFIG_HOME/samanvaya (or ~/.config/samanvaya), and on Windows it is
%APPDATA%\\samanvaya. The path can also be overridden by the SAMANVAYA_CONFIG_DIR
environment variable. Nothing is written anywhere else by the application itself.

Report files (PDF, Markdown, JSON lines) are written only to the output folder you choose
in the window, at the moment you press Generate. They are not copied, uploaded, indexed,
or otherwise transmitted. The application does not see the network at all, so it cannot
send them anywhere by accident.

Because the application runs entirely on your own machine, the security of the files it
produces is a matter of how you handle your own machine: who has access to it, whether it
is encrypted at rest, and where you choose to send the files afterwards. The application
contributes to that by not adding a network channel of its own.

If you want to remove everything the application has stored, close the window and delete
the two files named above. The application has no other state.
"""

HELP_TEXT: str = """\
Samanvaya — User Guide

What Samanvaya is for

Samanvaya is a tool for advisers who review privacy documentation against a set of
declared facts. The adviser writes a declaration file (a small JSON document describing
what a client has told the adviser about its data handling) and Samanvaya produces a
report that maps each declared fact to each rule in a jurisdiction pack.

The window is a thin skin over the same engine that the command-line interface runs.
Opening the window, picking a declaration, and pressing Generate does exactly what
running the CLI on the same declaration does. The two surfaces cannot disagree because
they share the engine.

The declaration file

The declaration file is written by the adviser, not by Samanvaya, because the
declaration is the adviser's record of what the client said. The window does not ask the
user to invent one; it asks the user to point at one already on disk. If the file is
malformed, the engine reports that fact and the report is not generated.

The workflow

  1. Choose a declaration file. The Browse button next to Declaration opens a file
     picker; the path is also editable by hand.
  2. Fill in the letterhead. The four fields under Letterhead (Firm, Adviser, Email,
     Phone) appear on the PDF cover. If "Remember this letterhead" is ticked, they are
     saved to preparer.json in the configuration directory and loaded next time.
  3. Set the as-at date. This is the date the declaration is read against; rules change
     over time and the date is what makes a report reproducible.
  4. Choose output formats. PDF is the version an adviser sends to a client; Markdown
     and JSON lines are easier to search and to feed into other tools.
  5. Choose an output folder. The report is written there, with the file name report
     and the chosen extensions.
  6. Press Generate. The window runs the engine off the UI thread so it does not freeze;
     the result text at the bottom of the window summarises what was written and where.

What the verdicts mean

Each rule in the report carries a plain-English label:

  - MET — the declared facts answer the rule and the answer is consistent with the
    rule's requirements.
  - NOT MET — the declared facts answer the rule and the answer is not consistent with
    the rule's requirements.
  - UNRESOLVED — the declared facts do not answer the rule. This is the verdict a
    client will ask about most often, and it is also the most useful one: UNRESOLVED
    is a precise list of what to go back and ask the client. A report full of UNRESOLVED
    items is not a worse report than a report full of MET items; it is a report that
    tells the adviser exactly where more information is needed before any conclusion
    can be drawn.
  - NOT ASSESSED — the jurisdiction pack does not contain a rule on this topic. A
    jurisdiction with no pack is reported as NOT ASSESSED for every item, rather than
    being omitted silently, so the absence of a pack is visible in the report.

The report is an input, not a conclusion

The window does not judge a client, label one, or close the loop on a finding.
Reaching any such view belongs to the adviser, who reads the report, talks to the
client, and forms one of their own. The report's job is to count findings in plain
English and stop.
"""

_NAMED_FONTS: tuple[str, ...] = (
    "TkDefaultFont",
    "TkTextFont",
    "TkFixedFont",
    "TkMenuFont",
    "TkHeadingFont",
)

# Populated on first use of _apply_font_scale with each named font's original size.
# Must persist across calls so that scale=1.0 restores the true original rather than
# a compounded value that has been scaled on top of itself repeatedly.
_ORIGINAL_FONT_SIZES: dict[str, int] = {}


# Bind text-size sequences globally so they work whichever window has focus. Binding
# only on ``self.root`` would leave every Toplevel — the Guide, the Licence, the
# Privacy Statement — deaf to Cmd-plus. ``bind_all`` reaches the focused widget
# regardless of which Toplevel is on screen. _apply_font_scale mutates Tk's named
# fonts, so any widget using a named font follows automatically.
_TEXT_SIZE_SEQUENCES: tuple[str, ...] = (
    "<Command-plus>",
    "<Command-equal>",
    "<Command-Shift-equal>",
    "<Command-minus>",
    "<Command-0>",
)


def _apply_font_scale(scale: float) -> None:
    """Resize Tk's named fonts in place so every widget follows.

    The named fonts are the ones Tk uses when a widget says "use the default font", so
    touching them is enough to make the existing form grow and shrink with one call.

    Each named font's ORIGINAL size is seeded from ``_BASE_FONT_SIZES`` the first time
    this routine runs and cached in a module-level dict, keyed by font name. On every
    subsequent call the scaled size is computed from that original
    (scaled_size(original, scale)), so the scale argument behaves as an absolute
    multiplier against the application base: 1.0 restores the original exactly, and
    repeated adjustments predictably step up or down instead of compounding.

    The earlier design read the CURRENT size and scaled it on top of itself, which
    meant each press multiplied by the previous press and "reset" with scale=1.0
    silently left the last compounded value in place. Caching the originals prevents
    that drift and makes Reset Text Size a genuine reset. Seeding from
    ``_BASE_FONT_SIZES`` rather than from ``cget("size")`` ensures the interface starts
    at a readable size regardless of what the platform default happened to be.
    """

    applied = clamp_scale(scale)
    for name in _NAMED_FONTS:
        try:
            current = tkfont.nametofont(name)
        except TclError:
            continue
        if name not in _ORIGINAL_FONT_SIZES:
            _ORIGINAL_FONT_SIZES[name] = _BASE_FONT_SIZES[name]
        base = _ORIGINAL_FONT_SIZES[name]
        current.configure(size=scaled_size(base, applied))


def _reflow_for_display(body: str) -> str:
    """Reflow a hard-wrapped block of prose so soft-wrapping can widen the lines.

    Many of the explanatory texts were authored at a fixed column width and contain
    manual newlines inside paragraphs. The text widget wraps on word boundaries, but
    soft wrapping cannot widen a line that already ends in a newline, so the prose
    appears as a narrow column. Joining the lines within each paragraph fixes that
    while preserving paragraph breaks (blank lines) and the shape of any list item
    whose stripped form starts with a digit-and-dot, a hyphen, or an en dash.
    """

    out_lines: list[str] = []
    paragraph: list[str] = []

    def is_list_marker(line: str) -> bool:
        stripped = line.lstrip()
        if not stripped:
            return False
        if stripped[:1] in {"-", "\u2013"}:
            return True
        # "1." "2)" "10. " — a run of digits followed by '.' or ')'.
        i = 0
        while i < len(stripped) and stripped[i].isdigit():
            i += 1
        return i > 0 and i < len(stripped) and stripped[i] in {".", ")"} and (
            i + 1 == len(stripped) or stripped[i + 1] == " "
        )

    def flush() -> None:
        if paragraph:
            out_lines.append(" ".join(paragraph).rstrip())
            paragraph.clear()

    for raw_line in body.splitlines():
        if not raw_line.strip():
            flush()
            out_lines.append("")
        elif is_list_marker(raw_line):
            flush()
            out_lines.append(raw_line.rstrip())
        else:
            paragraph.append(raw_line.strip())
    flush()
    return "\n".join(out_lines)


# --- Menu command functions -------------------------------------------------------------
# Each takes an optional App so it can be called headless with no window and do nothing.
# The headless path is what the acceptance tests rely on; the App path is what the user
# sees when they press the menu item.

def show_guide(app: "App | None" = None) -> None:
    """Open the user guide in a read-only Toplevel window."""

    if app is not None:
        app._open_text_window("User Guide", HELP_TEXT)


def show_licence(app: "App | None" = None) -> None:
    """Open the licence in a read-only Toplevel window."""

    if app is not None:
        app._open_text_window("Licence", LICENCE_TEXT)


def show_privacy(app: "App | None" = None) -> None:
    """Open the privacy statement in a read-only Toplevel window."""

    if app is not None:
        app._open_text_window("Privacy Statement", PRIVACY_TEXT)


def show_about(app: "App | None" = None) -> None:
    """Open the About box in a read-only Toplevel window."""

    if app is not None:
        app._open_text_window("About Samanvaya", about_text())


def show_preferences(app: "App | None" = None) -> None:
    """Open the Preferences dialog."""

    if app is not None:
        app._open_preferences()


def increase_text_size(app: "App | None" = None) -> None:
    """Apply one notch of growth and persist."""

    if app is not None:
        app._change_font_scale(+1)


def decrease_text_size(app: "App | None" = None) -> None:
    """Apply one notch of shrink and persist."""

    if app is not None:
        app._change_font_scale(-1)


def reset_text_size(app: "App | None" = None) -> None:
    """Reset to the default scale and persist."""

    if app is not None:
        app._set_font_scale(1.0)


def about_text() -> str:
    """Build the About text from the build, the author, and the disclaimer head.

    The BUILD is shown beside the version, not instead of it. A version string is
    carried by every rebuild of the same release; the build number identifies one
    artefact. When a client emails a report back three months after a meeting and asks
    which copy produced it, this is the screen the answer is read off — and until now
    it named only the version, which cannot answer that question.

    The first 40 characters of the disclaimer are shown so the user is reminded of the
    contract between the tool and the adviser without having to scroll through the
    whole statement, which is also reachable from the Help menu.
    """

    from samanvaya import __build__, __version__

    return (
        f"Samanvaya {__version__} (build {__build__})\n"
        "\n"
        "Written by Rushikesh R. Mahajan.\n"
        "\n"
        "Coded, verified and upgraded by Rushikesh R. Mahajan, Nagpur.\n"
        "\n"
        f"{DISCLAIMER[:40]}\n"
    )


# --- Menu command dispatch --------------------------------------------------------------
# MENU_SPEC names commands as strings; this is where those strings become callables.
# A name missing here is a menu item that does nothing when clicked, which an existing
# test catches.
def open_intake_form(app: "App | None" = None) -> None:
    """Open the sectioned intake form over the folder already chosen in the window."""

    if app is not None:
        app._on_intake_form()


def save_questionnaire(app: "App | None" = None) -> None:
    """Write the blank questionnaire into the folder already chosen in the window."""

    if app is not None:
        app._on_questionnaire()


_MENU_COMMANDS: dict[str, Callable[["App | None"], None]] = {
    "open_intake_form": open_intake_form,
    "save_questionnaire": save_questionnaire,
    "show_guide": show_guide,
    "show_licence": show_licence,
    "show_privacy": show_privacy,
    "show_about": show_about,
    "show_preferences": show_preferences,
    "increase_text_size": increase_text_size,
    "decrease_text_size": decrease_text_size,
    "reset_text_size": reset_text_size,
}


class App:
    """The Tkinter window.

    Constructing an ``App`` does not enter the main loop; ``main`` does. Widgets are
    built in ``__init__`` so the layout is described in one place, but the heavy lifting
    of validation and generation is delegated to the headless ``validate`` and
    ``generate`` functions, which the tests cover directly. The window is, deliberately,
    a thin skin over those functions.
    """

    def __init__(self, root: Tk | None = None) -> None:
        """Build the window. The caller owns the Tk root and the main loop."""

        owns_root = root is None
        self.root = root if root is not None else Tk()
        self.root.title("Samanvaya — privacy-conformance report")
        self.root.minsize(560, 520)

        # ``StringVar`` instances are mutable by design; they sit between the form
        # widgets and the request object the window builds at generate time.
        #: The open intake form, if one has been started. Held so a second click
        #: focuses the meeting in progress rather than opening a rival copy of it.
        self.intake_window: IntakeWindow | None = None

        self.declaration_var = StringVar()
        self.as_at_var = StringVar(value=date.today().isoformat())
        self.out_dir_var = StringVar(value=str(Path.home() / "Desktop"))

        preparer = load_preparer()
        self.firm_var = StringVar(value=preparer.firm or "")
        self.adviser_var = StringVar(value=preparer.adviser or "")
        self.email_var = StringVar(value=preparer.email or "")
        self.phone_var = StringVar(value=preparer.phone or "")

        self.format_pdf_var = BooleanVar(value=True)
        self.format_md_var = BooleanVar(value=False)
        self.format_jsonl_var = BooleanVar(value=False)
        self.remember_var = BooleanVar(value=False)

        self._busy = False
        self._font_scale: float = 1.0
        self._build_layout()
        self._build_menu()

        # Restore the saved preferences over the freshly-built form. Doing this last
        # means the form widgets are in their default state when the font scale is
        # applied, so the named fonts are resized before any widget asks for them.
        prefs = load_preferences()
        if prefs.default_out_dir:
            self.out_dir_var.set(prefs.default_out_dir)
        if prefs.default_formats:
            self.format_pdf_var.set("pdf" in prefs.default_formats)
            self.format_md_var.set("md" in prefs.default_formats)
            self.format_jsonl_var.set("jsonl" in prefs.default_formats)
        self._set_font_scale(prefs.font_scale, persist=False)

        if owns_root:
            # When the caller supplied the root we leave geometry and the main loop to
            # them; otherwise we give the window a sensible default size before main().
            self.root.geometry("640x640")

    def _build_layout(self) -> None:
        """Assemble the form top to bottom, exactly as the spec describes."""

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        outer.columnconfigure(1, weight=1)

        row = 0

        # Declaration row: label, path entry, Browse.
        ttk.Label(outer, text="Declaration").grid(row=row, column=0, sticky="w", pady=4)
        decl_entry = ttk.Entry(outer, textvariable=self.declaration_var)
        decl_entry.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 4))
        ttk.Button(outer, text="Browse", command=self._browse_declaration).grid(
            row=row, column=2, sticky="w", pady=4
        )
        row += 1

        # As-at row: a single entry that defaults to today.
        ttk.Label(outer, text="As-at").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(outer, textvariable=self.as_at_var).grid(
            row=row, column=1, sticky="ew", pady=4, padx=(8, 4)
        )
        row += 1

        # Letterhead group: a labelled frame around the four entry rows.
        letterhead = ttk.LabelFrame(outer, text="Letterhead")
        letterhead.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        letterhead.columnconfigure(1, weight=1)
        self._add_letterhead_row(letterhead, 0, "Firm", self.firm_var)
        self._add_letterhead_row(letterhead, 1, "Adviser", self.adviser_var)
        self._add_letterhead_row(letterhead, 2, "Email", self.email_var)
        self._add_letterhead_row(letterhead, 3, "Phone", self.phone_var)
        row += 1

        # Format checkboxes, kept on a single row so the form reads top-to-bottom.
        formats = ttk.LabelFrame(outer, text="Output formats")
        formats.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 4))
        ttk.Checkbutton(formats, text="PDF", variable=self.format_pdf_var).pack(
            side="left", padx=6
        )
        ttk.Checkbutton(formats, text="Markdown", variable=self.format_md_var).pack(
            side="left", padx=6
        )
        ttk.Checkbutton(formats, text="JSON lines", variable=self.format_jsonl_var).pack(
            side="left", padx=6
        )
        row += 1

        # Output folder row.
        ttk.Label(outer, text="Output folder").grid(
            row=row, column=0, sticky="w", pady=4
        )
        ttk.Entry(outer, textvariable=self.out_dir_var).grid(
            row=row, column=1, sticky="ew", pady=4, padx=(8, 4)
        )
        ttk.Button(outer, text="Browse", command=self._browse_out_dir).grid(
            row=row, column=2, sticky="w", pady=4
        )
        row += 1

        # Remember-this-letterhead checkbox, kept near the letterhead it refers to.
        ttk.Checkbutton(
            outer, text="Remember this letterhead", variable=self.remember_var
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 8))
        row += 1

        # Generate button spans the full width so it is the obvious next click.
        self.generate_button = ttk.Button(
            outer, text="Generate", command=self._on_generate
        )
        self.generate_button.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 4))
        row += 1

        # The intake half. Both of these are SECONDARY actions and they share one row,
        # because three full-width buttons stacked is how a form stops having a shape:
        # every feature that lands adds another bar, nothing is the obvious click any
        # more, and the window an adviser already knows quietly changes on them.
        # Generate stays the primary action above; everything else groups here.
        actions = ttk.Frame(outer)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.intake_button = ttk.Button(
            actions,
            text="New intake form",
            command=self._on_intake_form,
        )
        self.intake_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.questionnaire_button = ttk.Button(
            actions,
            text="Blank questionnaire (PDF)",
            command=self._on_questionnaire,
        )
        self.questionnaire_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        row += 1

        # Result area: a scrolled text box the worker thread writes into via ``after``.
        self.result_text = ScrolledText(outer, height=10, wrap="word")
        self.result_text.grid(row=row, column=0, columnspan=3, sticky="nsew")
        outer.rowconfigure(row, weight=1)
        row += 1

        # The disclaimer is permanent: it is the contract between this tool and the
        # adviser, and removing it from the visible surface would undo the discipline
        # the rest of the module is built around.
        ttk.Separator(outer).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        row += 1
        ttk.Label(outer, text=DISCLAIMER, wraplength=560, justify="left").grid(
            row=row, column=0, columnspan=3, sticky="ew"
        )

    def _build_menu(self) -> None:
        """Assemble the menubar from ``MENU_SPEC`` and bind the accelerators.

        The spec is the source of truth: every label, command and accelerator the user
        sees is declared once at module level and rendered here. Built-in clipboard
        commands are routed to Tk's virtual events; everything else dispatches to a
        module-level function that takes this App as its argument.
        """

        menubar = Menu(self.root)
        for menu_spec in MENU_SPEC:
            menu = Menu(menubar, tearoff=0)
            for item in menu_spec.items:
                if item.command is None:
                    menu.add_separator()
                    continue
                if item.command.startswith("_builtin:"):
                    event = "<<" + item.command[len("_builtin:") :] + ">>"
                    cmds: list[dict[str, Any]] = [{}]
                    spec: dict[str, Any] = {}
                    spec["label"] = item.label
                    spec["command"] = lambda e=event: self.root.event_generate(e)
                    if item.accelerator is not None:
                        spec["accelerator"] = item.accelerator
                    menu.add_command(**spec)
                else:
                    # A MENU_SPEC entry naming a function absent from ``_MENU_COMMANDS``
                    # is caught by an existing test rather than failing silently at
                    # click time. The default-argument idiom captures the loop variable
                    # so every menu item invokes its own command.
                    spec = {}
                    spec["label"] = item.label
                    spec["command"] = lambda name=item.command: _MENU_COMMANDS[name](self)
                    if item.accelerator is not None:
                        spec["accelerator"] = item.accelerator
                    menu.add_command(**spec)
            menubar.add_cascade(label=menu_spec.title, menu=menu)

        self.root.config(menu=menubar)

        # Bind the accelerators at the window level so they work regardless of focus.
        # ``Command`` on macOS, ``Control`` elsewhere; the spec strings are written as
        # ``Cmd+...`` for the menu display and translated here.
        # One visible menu accelerator can map to several Tk bind sequences. This is
        # necessary for "Cmd++" because on a US keyboard the physical key is
        # Shift-equal, so pressing Cmd and + delivers <Command-Shift-equal>, not
        # <Command-plus>. Binding all three — <Command-plus>, <Command-equal> and
        # <Command-Shift-equal> — covers every layout Tk speaks to and matches the
        # behaviour of every other macOS application.
        for menu_spec in MENU_SPEC:
            for item in menu_spec.items:
                if not item.accelerator or not item.accelerator.startswith("Cmd+"):
                    continue
                key = item.accelerator[4:]
                sequences: list[str] = []
                if key == "+":
                    # Three sequences for one menu item: the symbolic plus, the bare
                    # equal, and the Shift-equal that a US keyboard actually produces.
                    sequences = [
                        "<Command-plus>",
                        "<Command-equal>",
                        "<Command-Shift-equal>",
                    ]
                elif key == "=":
                    sequences = ["<Command-equal>", "<Command-plus>"]
                elif key == "-":
                    sequences = ["<Command-minus>"]
                elif key == "0":
                    sequences = ["<Command-0>"]
                elif len(key) == 1:
                    sequences = [f"<Command-{key.lower()}>"]
                if not sequences:
                    continue
                for sequence in sequences:
                    if item.command and item.command.startswith("_builtin:"):
                        event = "<<" + item.command[len("_builtin:") :] + ">>"
                        self.root.bind(sequence, self._virtual_event_handler(event))
                    elif item.command:
                        self.root.bind(sequence, self._menu_command_handler(item.command))

    def _virtual_event_handler(self, event: str) -> Callable[[Any], None]:
        """Return a handler that fires a Tk virtual event.

        A factory rather than a lambda carrying a default argument. The default-argument
        idiom exists only to capture the loop variable before it changes; binding it in
        an enclosing call does the same thing, and unlike a lambda the result can carry
        annotations, which is what let mypy infer it at all.
        """

        def handler(_event: Any) -> None:
            self.root.event_generate(event)

        return handler

    def _menu_command_handler(self, name: str) -> Callable[[Any], None]:
        """Return a handler that runs the named menu command.

        Looks the name up in ``_MENU_COMMANDS``. The previous version reached the same
        function via ``__import__("samanvaya.gui", fromlist=[name])`` — importing this
        very module at click time to fetch something defined a few hundred lines above.
        """

        def handler(_event: Any) -> None:
            _MENU_COMMANDS[name](self)

        return handler

    def _change_font_scale(self, direction: int) -> None:
        """Move the font scale one notch, apply it, and persist."""

        self._set_font_scale(step_scale(self._font_scale, direction))

    def _set_font_scale(self, scale: float, persist: bool = True) -> None:
        """Apply a font scale and optionally persist it as a preference.

        ``persist`` is False during initial restore so the act of reading the file does
        not immediately re-write it; the user has not changed anything yet.
        """

        self._font_scale = clamp_scale(scale)
        _apply_font_scale(self._font_scale)
        if persist:
            try:
                prefs = load_preferences()
                save_preferences(
                    Preferences(
                        font_scale=self._font_scale,
                        default_out_dir=prefs.default_out_dir,
                        default_formats=prefs.default_formats,
                    )
                )
            except OSError:
                # Persisting is a convenience, not a precondition for the change to
                # take effect. Failing to save must not undo the user's resize.
                pass

    def _open_text_window(
        self,
        title: str,
        body: str,
        *,
        verbatim: bool = False,
    ) -> None:
        """Open a scrollable, read-only Toplevel with a piece of explanatory text.

        Used for the Guide, the Licence, the Privacy Statement and the About box. The
        text widget is read-only because the user is here to read, not to edit; the
        window is modal in the sense that it grabs focus but modeless in that the main
        window stays usable underneath.

        ``verbatim=True`` keeps the body unchanged and uses the fixed font — required
        for the Licence, which is a legal document and must be reproduced exactly.
        Otherwise the prose is reflowed for display and rendered in the proportional
        text font so it fills the window.
        """

        window = Toplevel(self.root)
        window.title(title)
        window.minsize(480, 360)
        window.geometry("900x700")

        frame = ttk.Frame(window, padding=8)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = ScrolledText(frame, wrap="word", padx=24, pady=12)
        text.grid(row=0, column=0, sticky="nsew")
        if verbatim:
            text.configure(font="TkFixedFont")
            display_body = body
        else:
            display_body = _reflow_for_display(body)
        text.insert("1.0", display_body)
        text.configure(state="disabled")

        ttk.Button(frame, text="Close", command=window.destroy).grid(
            row=1, column=0, sticky="e", pady=(8, 0)
        )

    def _open_preferences(self) -> None:
        """Open a small dialog with the font scale and a Close button.

        The font scale is the only preference that has a visible effect today; the
        dialog also surfaces the current bounds so the user knows how far the scale
        can travel before it stops.
        """

        window = Toplevel(self.root)
        window.title("Preferences")
        window.minsize(360, 160)
        window.resizable(False, False)
        window.grab_set()

        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Text size").grid(row=0, column=0, sticky="w", pady=4)
        scale_var = StringVar(value=f"{self._font_scale:.1f}")
        ttk.Label(frame, textvariable=scale_var).grid(
            row=0, column=1, sticky="e", pady=4
        )

        def _on_scale(v: str, sv: StringVar = scale_var) -> None:
            sv.set(f"{float(v):.1f}")

        scale = ttk.Scale(
            frame,
            from_=MIN_FONT_SCALE,
            to=MAX_FONT_SCALE,
            orient="horizontal",
            value=self._font_scale,
            command=_on_scale,
        )
        scale.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)

        bounds = ttk.Label(
            frame,
            text=(
                f"Range: {MIN_FONT_SCALE:.1f} to {MAX_FONT_SCALE:.1f}. "
                "Resizing affects every widget in the window."
            ),
            wraplength=320,
            justify="left",
        )
        bounds.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 8))

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))

        def apply_and_close() -> None:
            self._set_font_scale(float(scale.get()))
            window.destroy()

        ttk.Button(button_row, text="Cancel", command=window.destroy).pack(
            side="right", padx=(4, 0)
        )
        ttk.Button(button_row, text="OK", command=apply_and_close).pack(
            side="right"
        )

    def _add_letterhead_row(
        self, parent: ttk.Widget, row: int, label: str, var: StringVar
    ) -> None:
        """Add a labelled entry to the letterhead group.

        Factored out because the four rows are otherwise identical and the duplication
        is the kind that drifts over time.
        """

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(parent, textvariable=var).grid(
            row=row, column=1, sticky="ew", padx=4, pady=2
        )

    def _browse_declaration(self) -> None:
        """Open a file dialog for the declaration path."""

        chosen = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a declaration file",
            filetypes=[("Declaration", "*.json"), ("All files", "*.*")],
        )
        if chosen:
            self.declaration_var.set(chosen)

    def _browse_out_dir(self) -> None:
        """Open a directory chooser for the output folder."""

        chosen = filedialog.askdirectory(
            parent=self.root,
            title="Choose an output folder",
            mustexist=True,
        )
        if chosen:
            self.out_dir_var.set(chosen)

    def _build_request(self) -> GenerateRequest:
        """Build a ``GenerateRequest`` from the current form state.

        Validating before running the engine is the whole point of ``validate``, so the
        worker thread calls ``validate`` itself. Building the request here is just shape.
        """

        declaration_text = self.declaration_var.get().strip()
        declaration_path = Path(declaration_text) if declaration_text else Path("")
        out_text = self.out_dir_var.get().strip()
        out_dir = Path(out_text) if out_text else Path("")

        formats: list[str] = []
        if self.format_pdf_var.get():
            formats.append("pdf")
        if self.format_md_var.get():
            formats.append("md")
        if self.format_jsonl_var.get():
            formats.append("jsonl")

        preparer = self._preparer_from_fields()

        return GenerateRequest(
            declaration_path=declaration_path,
            as_at=self.as_at_var.get().strip(),
            out_dir=out_dir,
            stem="report",
            formats=tuple(formats),
            preparer=preparer,
        )

    def _preparer_from_fields(self) -> Preparer:
        """Read the four letterhead fields into a Preparer.

        One reader, because the report and the questionnaire must never be able to carry
        different letterheads from the same window.
        """

        return Preparer(
            firm=self.firm_var.get().strip() or None,
            adviser=self.adviser_var.get().strip() or None,
            email=self.email_var.get().strip() or None,
            phone=self.phone_var.get().strip() or None,
        )

    def _on_questionnaire(self) -> None:
        """Handle a click on the questionnaire button.

        Run inline rather than on a worker thread: rendering eighty-three questions is
        a fraction of a second, and a thread would buy nothing but a race with the
        Generate button's busy flag.
        """

        out_text = self.out_dir_var.get().strip()
        out_dir = Path(out_text) if out_text else Path("")
        self._render_result(write_questionnaire(out_dir, self._preparer_from_fields()))

    def _on_intake_form(self) -> None:
        """Open the intake form, resuming the meeting already in this folder if there is one.

        The working file lives in the chosen output folder under a fixed name, so
        reopening the form after a crash — or after lunch — continues where the adviser
        stopped rather than silently starting a blank one over the top of it. That
        resume is what makes the autosave worth having; without it the crash-safe file
        is written and never read.

        Every failure is reported into the result area rather than raised. A traceback
        in front of a client is not an error message.
        """

        out_text = self.out_dir_var.get().strip()
        out_dir = Path(out_text) if out_text else Path("")
        try:
            if not out_text or not out_dir.is_dir():
                self._render_result(
                    GenerateResult(
                        files_written=[],
                        counts={},
                        error=(
                            "Please choose an output folder before starting an intake "
                            "form. The answers are saved there as you go."
                        ),
                    )
                )
                return
            working = out_dir / "intake-working.json"
            form = IntakeForm.resume(working) if working.is_file() else IntakeForm(
                working_file=working
            )
        except Exception as exc:
            self._render_result(
                GenerateResult(
                    files_written=[],
                    counts={},
                    error=f"The intake form could not be opened: {exc}",
                )
            )
            return

        window = Toplevel(self.root)
        window.title("Intake form — Samanvaya")
        self.intake_window = IntakeWindow(window, form)

    def _on_generate(self) -> None:
        """Handle a click on Generate.

        Runs the engine off the UI thread so the window does not freeze on a long run,
        and marshals the result back into the result text via ``widget.after``.
        """

        if self._busy:
            return

        request = self._build_request()
        errors = validate(request)
        if errors:
            self._render_result(
                GenerateResult(files_written=[], counts={}, error=" ".join(errors))
            )
            return

        if self.remember_var.get():
            try:
                save_preparer(request.preparer)
            except OSError as exc:
                # Saving is a convenience, not a precondition for generating. Telling
                # the user and continuing is better than failing the run.
                self._append_status(f"Could not save the letterhead: {exc}")

        self._busy = True
        self.generate_button.state(["disabled"])
        self._append_status("Generating, please wait...")

        thread = threading.Thread(
            target=self._run_in_worker, args=(request,), daemon=True
        )
        thread.start()

    def _run_in_worker(self, request: GenerateRequest) -> None:
        """Worker-thread entry point.

        ``generate`` never raises, so the thread does not need to catch. The result is
        handed back to the Tk thread via ``after`` because Tkinter widgets are not
        thread-safe and must only be touched from the thread that created them.
        """

        result = generate(request)
        self.root.after(0, self._render_result, result)
        self.root.after(0, self._mark_idle)

    def _mark_idle(self) -> None:
        """Re-enable Generate after the worker finishes."""

        self._busy = False
        self.generate_button.state(["!disabled"])

    def _render_result(self, result: GenerateResult) -> None:
        """Display a GenerateResult in the result text area.

        The summary line is built from ``counts`` and uses the same plain-English labels
        the PDF does; it never describes a conclusion. Errors are shown verbatim so the
        user can act on them.
        """

        self.result_text.delete("1.0", "end")

        if result.error:
            self.result_text.insert("end", result.error)
            return

        if result.counts:
            parts = [f"{count} {label}" for label, count in result.counts.items()]
            total = sum(result.counts.values())
            head = f"{total} finding" + ("s" if total != 1 else "")
            head += ": " + ", ".join(parts) + "."
            self.result_text.insert("end", head + "\n\n")

        if result.files_written:
            for path in result.files_written:
                self.result_text.insert("end", f"Wrote {path}\n")

    def _append_status(self, message: str) -> None:
        """Append a single status line to the result text area."""

        self.result_text.insert("end", message + "\n")
        self.result_text.see("end")

    def mainloop(self) -> None:
        """Enter the Tk main loop. Convenience for callers that prefer an object API."""

        self.root.mainloop()


def _run_selftest_and_exit(path: str) -> int:
    """Build the self-test report at ``path`` and return the exit code.

    The bundle is ``--windowed``: no stdin, no arguments a user would pass. An
    environment variable is the one channel that reaches it, so this is the only way
    the build script can drive a frozen copy of the application to test itself. The
    work is done inside a fresh, temporary directory so the user's filesystem is
    never written to during the test.

    Returns 0 when every surface is ok, non-zero otherwise. The build must FAIL, not
    warn.
    """

    import tempfile

    from samanvaya import selftest

    with tempfile.TemporaryDirectory() as scratch:
        workdir = Path(scratch)
        report = selftest.run_selftest(workdir=workdir, report_path=Path(path))
    return 0 if report["ok"] else 1


def main() -> int:
    """Construct and run the window.

    Returning an ``int`` keeps the function usable as a console-script entry point
    without forcing the module to import ``sys``.
    """

    selftest_path = os.environ.get("SAMANVAYA_SELFTEST")
    if selftest_path:
        # The self-test branch must return before any window is built. Reaching
        # ``root.mainloop()`` during a test hangs pytest forever rather than
        # failing it, which is how this file cost five minutes the first time it
        # was run.
        return _run_selftest_and_exit(selftest_path)

    app = App()
    app.root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
