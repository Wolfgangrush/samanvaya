"""Command-line interface for the samanvaya conformance tool.

The CLI is the whole product surface: one adviser, one terminal, one declaration file.
Nothing leaves the machine on the tool's say-so — findings are written to a file the
adviser names, `--stdout` is strictly opt-in, and the tool performs no network access,
keeps no history and files nothing anywhere of its own accord.

Failures must be legible. An adviser mid-engagement cannot debug a stack trace, so every
anticipated failure is caught, given a named, actionable message on STDERR and a non-zero
exit code. A traceback reaching the terminal is a defect, not a nuisance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Sequence

from samanvaya import __version__
from samanvaya.declaration import canonical_hash, load
from samanvaya.engine import run
from samanvaya.interview import (
    answers_to_declaration,
    declaration_to_answers,
    run_interview,
)
from samanvaya.pdf_report import Preparer, render_pdf
from samanvaya.questionnaire import render_questionnaire
from samanvaya.registry import PACKS, get
from samanvaya.report import render, write
from samanvaya.schema import validate
from samanvaya.types import (
    DeclarationError,
    PackLoadError,
    RegimeId,
    UpstreamContractError,
)

_COPYRIGHT_DISCLAIMER = "This report is not legal advice."


def _preparer_path() -> Path:
    """Locate the on-disk profile, honouring a runtime env var override."""
    cfg = os.environ.get("SAMANVAYA_CONFIG_DIR")
    base = Path(cfg) if cfg else Path.home() / ".config" / "samanvaya"
    return base / "preparer.json"


def _resolved_preparer(argv: argparse.Namespace) -> Preparer:
    """Build a Preparer from CLI flags, falling back to the saved profile."""
    saved = Preparer.load(_preparer_path())
    overrides: dict[str, str | None] = {
        "firm": getattr(argv, "firm", None),
        "adviser": getattr(argv, "adviser", None),
        "email": getattr(argv, "email", None),
        "phone": getattr(argv, "phone", None),
    }
    values = {
        field: overrides[field] if overrides[field] is not None else getattr(saved, field)
        for field in ("firm", "adviser", "email", "phone")
    }
    return Preparer(**values)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="samanvaya",
        description="Multi-regime regulatory conformance checking tool.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Run a conformance check and write a report.")
    check.add_argument("declaration", help="Path to the declaration JSON file.")
    check.add_argument("--out", default="conformance-report", help="Output path stem.")
    check.add_argument(
        "--as-at",
        default=None,
        help="Date the assessment is made as at, YYYY-MM-DD.",
    )
    check.add_argument(
        "--regime",
        action="append",
        default=None,
        help="Restrict to a regime (repeatable).",
    )
    check.add_argument(
        "--format",
        choices=["md", "jsonl", "both", "pdf", "all"],
        default="both",
        help="Report format: md, jsonl, both, pdf, or all.",
    )
    check.add_argument(
        "--stdout",
        action="store_true",
        help="Additionally print the rendered Markdown to stdout.",
    )
    check.add_argument("--firm", default=None, help="Firm name to letterhead the PDF.")
    check.add_argument("--adviser", default=None, help="Adviser name to letterhead the PDF.")
    check.add_argument("--email", default=None, help="Adviser email to letterhead the PDF.")
    check.add_argument("--phone", default=None, help="Adviser phone to letterhead the PDF.")

    validate = sub.add_parser("validate", help="Validate a declaration file.")
    validate.add_argument("declaration", help="Path to the declaration JSON file.")

    init = sub.add_parser("init", help="Write a minimal declaration skeleton.")
    init.add_argument("--out", default="declaration.json", help="Path to write.")
    init.add_argument(
        "--force", action="store_true", help="Overwrite an existing file."
    )

    interview = sub.add_parser(
        "interview",
        help="Run a guided interview to produce a declaration JSON file.",
    )
    interview.add_argument(
        "--out", default="declaration.json", help="Path to write the declaration."
    )
    interview.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing declaration file.",
    )
    interview.add_argument(
        "--resume",
        default=None,
        help="Path to an existing declaration from which to carry forward answers.",
    )

    profile = sub.add_parser(
        "profile",
        help="Save or display letterhead profile for PDF reports.",
    )
    profile.add_argument("--firm", default=None, help="Firm name to save.")
    profile.add_argument("--adviser", default=None, help="Adviser name to save.")
    profile.add_argument("--email", default=None, help="Adviser email to save.")
    profile.add_argument("--phone", default=None, help="Adviser phone to save.")
    profile.add_argument(
        "--show",
        action="store_true",
        help="Print the saved profile values to stdout.",
    )

    questionnaire = sub.add_parser(
        "questionnaire",
        help="Write the blank pre-meeting questionnaire as a PDF.",
    )
    questionnaire.add_argument(
        "--out",
        required=True,
        help="Path to write the questionnaire PDF to.",
    )
    questionnaire.add_argument("--firm", default=None, help="Firm name for the letterhead.")
    questionnaire.add_argument(
        "--adviser", default=None, help="Adviser name for the letterhead."
    )
    questionnaire.add_argument("--email", default=None, help="Adviser email.")
    questionnaire.add_argument("--phone", default=None, help="Adviser phone.")

    sub.add_parser("version", help="Print the tool version.")
    sub.add_parser("cite", help="List the regulatory packs and their instruments.")
    return parser


def _cmd_check(argv: argparse.Namespace) -> int:
    if argv.as_at is None:
        as_at = date.today()
        # A legal tool must be reproducible: say which clock reading was assumed so the
        # adviser knows a re-run tomorrow will differ unless --as-at is supplied.
        print(
            f"note: --as-at not given; assuming {as_at.isoformat()}; "
            "pass --as-at to make this run reproducible",
            file=sys.stderr,
        )
    else:
        try:
            as_at = date.fromisoformat(argv.as_at)
        except ValueError:
            print(
                f"error: bad --as-at value {argv.as_at!r}: "
                "expected an ISO date, YYYY-MM-DD",
                file=sys.stderr,
            )
            return 2

    regimes: list[RegimeId] | None = None
    if argv.regime is not None:
        regimes = []
        for raw in argv.regime:
            try:
                regimes.append(RegimeId(raw.upper()))
            except ValueError:
                print(
                    f"error: unknown regime {raw!r}: expected one of "
                    + ", ".join(r.value for r in RegimeId),
                    file=sys.stderr,
                )
                return 2

    declaration = load(Path(argv.declaration))
    result = run(declaration, as_at, regimes)
    out_path = Path(argv.out)

    written: list[str] = []
    if argv.format == "all":
        write(result, out_path, "both")
        written.append(str(out_path.with_suffix(".md")))
        written.append(str(out_path.with_suffix(".jsonl")))
        preparer = _resolved_preparer(argv)
        preparer.validate()
        pdf_path = out_path.parent / (out_path.name + ".pdf")
        render_pdf(result, pdf_path, preparer)
        written.append(str(pdf_path))
    elif argv.format == "pdf":
        preparer = _resolved_preparer(argv)
        preparer.validate()
        pdf_path = out_path.parent / (out_path.name + ".pdf")
        render_pdf(result, pdf_path, preparer)
        written.append(str(pdf_path))
    else:
        write(result, out_path, argv.format)
        if argv.format in ("md", "both"):
            written.append(str(out_path.with_suffix(".md")))
        if argv.format in ("jsonl", "both"):
            written.append(str(out_path.with_suffix(".jsonl")))

    # Only a short confirmation goes to the terminal: findings are client material and
    # must not linger in shell history or a screen-share.
    print("wrote " + ", ".join(written))
    if argv.stdout:
        if argv.format == "jsonl":
            print(render(result, "jsonl"))
        else:
            print(render(result, "md"))
    return 0


def _cmd_validate(argv: argparse.Namespace) -> int:
    declaration = load(Path(argv.declaration))
    digest = canonical_hash(declaration)
    print(f"ok {digest}")
    return 0


def _cmd_init(argv: argparse.Namespace) -> int:
    target = Path(argv.out)
    if target.exists() and not argv.force:
        print(f"error: file exists: {target} (use --force to overwrite)", file=sys.stderr)
        return 2
    # Deliberately minimal, and deliberately free of credential-shaped placeholders: a
    # template that suggests a connection string invites exactly the input this tool
    # refuses to hold.
    skeleton = {
        "schema_version": "1.0",
        "organisation": {"legal_name": "Example Organisation Ltd"},
        "jurisdictions": [
            # `country`, not `regime`: the declaration names places, and the
            # resolver maps places to regimes. `sub_units_complete` is false by
            # default so silence never reads as "we checked every state".
            {"country": "IN", "sub_units": [], "sub_units_complete": False}
        ],
        "declaration_author": "Name of the responsible adviser",
    }
    target.write_text(
        json.dumps(skeleton, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {target}")
    return 0


def _cmd_interview(argv: argparse.Namespace) -> int:
    target = Path(argv.out)
    if target.exists() and not argv.force:
        print(
            f"error: file exists: {target} (use --force to overwrite)",
            file=sys.stderr,
        )
        return 2

    existing_answers: dict[str, object] = {}
    if argv.resume is not None:
        resume_path = Path(argv.resume)
        try:
            prior_raw = json.loads(resume_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if isinstance(prior_raw, dict):
            existing_answers = declaration_to_answers(prior_raw)

    print("Legal name of the organisation:")
    try:
        legal_name = input()
    except EOFError:
        legal_name = ""
    legal_name = legal_name.strip()
    if not legal_name:
        legal_name = "Example Organisation Ltd"

    print("Name of the responsible adviser:")
    try:
        author = input()
    except EOFError:
        author = ""
    author = author.strip()
    if not author:
        author = "adviser"

    print(
        "Countries where personal data is processed, as comma-separated ISO codes or names:"
    )
    try:
        jurisdictions_raw = input()
    except EOFError:
        jurisdictions_raw = ""
    tokens = [token.strip() for token in jurisdictions_raw.split(",") if token.strip()]
    jurisdictions: list[dict[str, object]] = [
        {"country": token, "sub_units": [], "sub_units_complete": False}
        for token in tokens
    ]
    if not jurisdictions:
        # Empty is permitted; the schema accepts an empty list and the engine
        # treats it as "no place named", which keeps the obligation surface small.
        jurisdictions = []

    def _read(prompt: str) -> str:
        # `input()` already prints the prompt; the interview prints its own, so we
        # pass an empty prompt here to avoid double-printing.
        try:
            return input("")
        except EOFError:
            return ""

    def _write(line: str) -> None:
        print(line)

    answers = run_interview(_read, _write, existing=existing_answers)

    obj = answers_to_declaration(
        answers,
        legal_name=legal_name,
        author=author,
        jurisdictions=jurisdictions,
        declaration_date=date.today(),
    )

    try:
        validate(obj)
    except DeclarationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        target.write_text(
            json.dumps(obj, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {target}")
    print(
        "Reminder: any question you skipped is reported as `contested`, "
        "not as a gap. Run with --force to overwrite, or pass the file to "
        "`samanvaya check`."
    )
    return 0


def _cmd_profile(argv: argparse.Namespace) -> int:
    if argv.show:
        saved = Preparer.load(_preparer_path())
        if saved.is_empty:
            print("profile: (empty)")
        else:
            if saved.firm is not None:
                print(f"firm: {saved.firm}")
            if saved.adviser is not None:
                print(f"adviser: {saved.adviser}")
            if saved.email is not None:
                print(f"email: {saved.email}")
            if saved.phone is not None:
                print(f"phone: {saved.phone}")
        return 0

    candidate = Preparer(
        firm=argv.firm,
        adviser=argv.adviser,
        email=argv.email,
        phone=argv.phone,
    )
    try:
        candidate.validate()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    target = _preparer_path()
    candidate.save(target)
    print(f"wrote {target}")
    return 0


def _cmd_questionnaire(argv: argparse.Namespace) -> int:
    """Write the blank questionnaire — the document that PRECEDES a declaration.

    It deliberately takes no declaration and no --as-at. It is what the adviser sends a
    client a week before the meeting so there is something to type in afterwards, and
    requiring the declaration it exists to collect would be the same circularity that
    shipped the window as a file picker for a file nothing could create.

    The letterhead is resolved exactly as the report resolves it — flags first, then the
    saved profile — and validated BEFORE anything is written, so a refused run leaves no
    file behind.
    """
    preparer = _resolved_preparer(argv)
    preparer.validate()
    out_path = Path(argv.out)
    render_questionnaire(out_path, preparer)
    print(f"wrote {out_path}")
    return 0


def _cmd_cite(_argv: argparse.Namespace) -> int:
    for regime in RegimeId:
        if regime not in PACKS:
            continue
        pack = get(regime)
        info = pack.info()
        draft_note = " [DRAFT]"
        status = ""
        if info.draft:
            status = draft_note
            if info.draft_reason:
                status += f" ({info.draft_reason})"
        print(f"{info.pack_id} v{info.version}{status}")
        for instrument in info.instruments:
            print(f"  {instrument}")
    print(_COPYRIGHT_DISCLAIMER)
    return 0


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "check": _cmd_check,
    "validate": _cmd_validate,
    "init": _cmd_init,
    "interview": _cmd_interview,
    "profile": _cmd_profile,
    "questionnaire": _cmd_questionnaire,
    "version": lambda argv: (print(__version__), 0)[1],
    "cite": _cmd_cite,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code.

    No exception may escape except the SystemExit argparse raises for a missing or
    invalid subcommand. Every anticipated failure is reported on STDERR with a named,
    actionable message and exit code 2. Exception messages are printed unchanged and no
    context is added, because added context risks reintroducing material (such as a
    matched credential) that the underlying error deliberately omitted.
    """
    args = list(argv) if argv is not None else None
    parser = _build_parser()
    parsed = parser.parse_args(args)
    handler = _COMMANDS[parsed.command]
    try:
        result = handler(parsed)
        return int(result)
    except (
        DeclarationError,
        UpstreamContractError,
        PackLoadError,
        FileNotFoundError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
