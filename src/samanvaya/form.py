"""The headless intake form -- BMAD/08 part B.

This is the model behind the sectioned intake window: an adviser sits with a
client, types answers to 83 questions, and the tool holds those answers,
parses them, counts them, autosaves them and turns them into the declaration
the engine reads. The Tk view lives elsewhere; this module is the thing it
watches.

THE RULE THAT OUTRANKS EVERY OTHER ONE HERE
-------------------------------------------
"Not established" is a first-class answer and the default. It is not a
blank, not a missing value, and never a "no". The engine reports an
undeclared fact as ``contested``, which is the honest result; a form that
coerced a guess into a field to look complete would destroy the gap/contested
distinction, and that distinction is the single most dangerous thing this
whole tool could lose. Every default is :data:`NOT_ESTABLISHED`; a question
is only answered when a human answered it.

CONSEQUENCES IMPLEMENTED HERE
-----------------------------
- Every question starts at :data:`NOT_ESTABLISHED`.
- The literal user input ``"Not established"`` (case-insensitive) is accepted
  as an answer for EVERY kind and sets the value back to
  :data:`NOT_ESTABLISHED`, returning ``None`` rather than an error.
- :data:`NOT_ESTABLISHED` never counts as answered in progress.
- :data:`NOT_ESTABLISHED` is omitted from the declaration entirely, which
  is what makes the engine report ``contested`` rather than a gap.
- No inference. Setting one answer never sets another.

The credential firewall (:func:`samanvaya.credentials.assert_clean`) runs on
every free-text and list answer before it is stored. A refused answer never
reaches the working file. A refused answer never destroys the previous value
either: ``set`` returns the error message and the form's state is unchanged.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from pathlib import Path
from typing import Final, Sequence

from samanvaya import credentials
from samanvaya.types import DeclarationError
from samanvaya.interview import (
    Question,
    QUESTIONS,
    answers_to_declaration,
    declaration_to_answers,
)


class _NotEstablished:
    """Sentinel singleton for the default, undeclared state of every question.

    Defined as a class so its :meth:`__repr__` can name it without ambiguity
    (a plain object would inherit the unhelpful ``<object object at 0x...>``).
    Falsy through ``__bool__`` so a truthiness test on a fresh form behaves
    like an unset value, but identity-distinguishable from ``None``, ``False``,
    empty string and zero so the gap/answered distinction survives any test
    the view or the engine might write against it.
    """

    _instance: "_NotEstablished | None" = None

    def __new__(cls) -> "_NotEstablished":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NOT_ESTABLISHED"

    def __bool__(self) -> bool:
        # Falsy: a fresh field reads as "no value". Identity still distinguishes it.
        return False


#: The default and a first-class answer. Identity-distinguishable from
#: ``None``, ``False``, ``""`` and ``0``; falsy; never present in a
#: declaration (its absence is what makes the engine report ``contested``).
NOT_ESTABLISHED: Final["_NotEstablished"] = _NotEstablished()


#: Every user-facing string this module itself writes -- error messages and
#: any labels that could reach the adviser. The form is a gatherer, not an
#: assessor: a test greps this tuple for verdict vocabulary, so any string
#: here that contains ``compliant``, ``non-compliant``, ``pass``, ``fail``,
#: ``at risk``, ``safe``, ``violation``, ``breach of law``, ``you should``,
#: ``we recommend``, ``satisfied``, ``gap`` or ``unresolved`` will fail
#: that test. Errors are written in plain descriptive prose instead.
#: Every user-facing sentence this module writes, each bound to a NAME.
#:
#: They were a bare tuple read positionally (`MSG_LOOKS_LIKE_A_CREDENTIAL`), which has no failure
#: mode a test notices: insert one message at the top and every index below it shifts,
#: so the user is handed a fluent, confident, wrong sentence. Three entries were already
#: dead on arrival, which is the same rot one step earlier. Names cannot shift.
MSG_NOT_A_WHOLE_NUMBER: Final[str] = "That is not a whole number."
MSG_NOT_A_NUMBER: Final[str] = "That is not a number."
MSG_ANSWER_YES_OR_NO: Final[str] = "Please answer yes or no."
MSG_LOOKS_LIKE_A_CREDENTIAL: Final[str] = (
    "That entry looks like a credential. Please describe the control in plain prose "
    "instead."
)
MSG_LEGAL_NAME_MISSING: Final[str] = (
    "Cannot save the declaration: the organisation legal name is missing."
)
MSG_JURISDICTION_MISSING: Final[str] = (
    "Cannot save the declaration: at least one jurisdiction is required."
)
#: Raised while OPENING a file, so it must not talk about saving. An adviser reopening a
#: part-finished meeting who is told the save failed goes looking for a disk problem,
#: when the file they just opened is the thing that is broken.
MSG_WORKING_FILE_UNREADABLE: Final[str] = (
    "Cannot open this file: it is not readable as a declaration."
)

AUTHORED_TEXT: Final[tuple[str, ...]] = (
    MSG_NOT_A_WHOLE_NUMBER,
    MSG_NOT_A_NUMBER,
    MSG_ANSWER_YES_OR_NO,
    MSG_LOOKS_LIKE_A_CREDENTIAL,
    MSG_LEGAL_NAME_MISSING,
    MSG_JURISDICTION_MISSING,
    MSG_WORKING_FILE_UNREADABLE,
)


#: Distinguishes this form's own working file from a declaration. Both open in
#: `resume`; only the first is lossless.
_WORKING_FILE_MARKER: Final[str] = "samanvaya_intake_working_file"
_WORKING_FILE_VERSION: Final[int] = 1


_NOT_ESTABLISHED_RE: Final["re.Pattern[str]"] = re.compile(
    r"^\s*not\s+established\s*$", re.IGNORECASE
)


@dataclasses.dataclass(frozen=True)
class SectionProgress:
    """How many questions in a section are answered.

    Frozen because progress is a value derived from the form, not state to
    mutate; passing the same ``SectionProgress`` to two callers must compare
    equal and convey the same numbers.
    """

    title: str
    answered: int
    total: int


# --- parsing ---------------------------------------------------------------

_TRUE_TOKENS: Final[frozenset[str]] = frozenset({"yes", "y", "true"})
_FALSE_TOKENS: Final[frozenset[str]] = frozenset({"no", "n", "false"})


def _parse_bool(text: str) -> bool | None:
    """Return the parsed boolean, or ``None`` when the text is unparseable."""
    norm = text.strip().casefold()
    if norm in _TRUE_TOKENS:
        return True
    if norm in _FALSE_TOKENS:
        return False
    return None


def _parse_int(text: str) -> int | None:
    """Return the parsed integer, or ``None`` when the text is unparseable.

    A float that happens to be whole-valued (e.g. ``"1.0"``) is REJECTED
    here -- ``int("1.0")`` raises ``ValueError`` in Python, so the test
    against a number-like-but-not-digit-only string is automatic.
    """
    norm = text.strip()
    try:
        return int(norm)
    except ValueError:
        return None


def _parse_float(text: str) -> float | None:
    """Return the parsed number, or ``None`` when the text is unparseable."""
    norm = text.strip()
    try:
        return float(norm)
    except ValueError:
        return None


def _parse_list(text: str) -> list[str]:
    """Comma-split, trim each element, drop empties."""
    parts = [item.strip() for item in text.split(",")]
    return [item for item in parts if item]


# Index by question path so set/get/clear are O(1).
_QUESTIONS_BY_PATH: Final[dict[str, Question]] = {q.path: q for q in QUESTIONS}


class IntakeForm:
    """The 83-question intake form, headless.

    The model holds answers, parses user input, counts progress and persists
    state. The Tk view (which lives elsewhere) reads and writes through this
    object; nothing here knows about Tk or pixels.
    """

    legal_name: str
    author: str

    def __init__(self, working_file: Path | None = None) -> None:
        """Start empty. A ``working_file`` enables autosave; without one
        the form is in-memory only and ``autosave`` is a no-op."""
        self.legal_name = ""
        self.author = ""
        self._working_file: Path | None = working_file
        self._values: dict[str, object] = {}
        self._jurisdictions: list[dict[str, object]] = []

    # --- jurisdictions -------------------------------------------------------

    @property
    def jurisdictions(self) -> tuple[dict[str, object], ...]:
        """Read-only view of the declared jurisdictions, in add-order.

        A tuple so a caller cannot mutate the form's state through the view;
        adding or removing a jurisdiction must go through the dedicated
        methods, which is what keeps the credential and normalisation rules
        enforced at the boundary.
        """
        return tuple(self._jurisdictions)

    def add_jurisdiction(
        self,
        country: str,
        sub_units: Sequence[str] | None = None,
        sub_units_complete: bool = True,
    ) -> None:
        """Add a country, normalised. Adding the same country twice is a no-op."""
        norm = country.strip().upper()
        if not norm:
            return
        for entry in self._jurisdictions:
            if entry["country"] == norm:
                return
        self._jurisdictions.append(
            {
                "country": norm,
                "sub_units": list(sub_units) if sub_units else [],
                "sub_units_complete": bool(sub_units_complete),
            }
        )
        self.autosave()

    def remove_jurisdiction(self, country: str) -> None:
        """Remove a country by case-folded equality on its normalised code."""
        norm = country.strip().upper()
        for index, entry in enumerate(self._jurisdictions):
            if entry["country"] == norm:
                del self._jurisdictions[index]
                self.autosave()
                return

    # --- questions ----------------------------------------------------------

    def questions(self) -> tuple[Question, ...]:
        """The whole question bank in bank order. The form never invents,
        drops or reorders a question."""
        return QUESTIONS

    def sections(self) -> tuple[str, ...]:
        """Section titles in first-seen bank order."""
        seen: list[str] = []
        for question in QUESTIONS:
            if question.section not in seen:
                seen.append(question.section)
        return tuple(seen)

    def questions_in(self, section: str) -> tuple[Question, ...]:
        """The questions in one section, in bank order. Refusing to admit
        cross-section leakage is what makes ``progress`` count correctly."""
        return tuple(q for q in QUESTIONS if q.section == section)

    # --- read / write -------------------------------------------------------

    def get(self, path: str) -> object:
        """The parsed value at ``path``, or :data:`NOT_ESTABLISHED`."""
        return self._values.get(path, NOT_ESTABLISHED)

    def set(self, path: str, raw: str) -> str | None:
        """Parse and store ``raw`` for ``path``.

        Returns ``None`` on success and an error message string on refusal.
        An unknown ``path`` raises ``KeyError`` so a typo in the view never
        silently creates a field the engine will never read. A refused
        answer leaves the stored value untouched, so the previous answer --
        and the working file on disk -- survive a bad paste.
        """
        if path not in _QUESTIONS_BY_PATH:
            raise KeyError(path)
        question = _QUESTIONS_BY_PATH[path]

        # The literal "Not established" is a valid answer for every kind.
        # It is the one input the form accepts that is NOT a typed value,
        # and the one that distinguishes "the client declined" from "the
        # adviser never asked".
        # Blank means the user removed their answer, and an answer removed is Not
        # established — not an error, and never a reason to keep the old value.
        #
        # Text and list answers already behaved this way; numbers and yes/no did not.
        # Backspacing a number field to empty was REFUSED and the previous number was
        # KEPT, so the control on screen read blank while the model still held 7 and
        # the declaration shipped the 7. A declared fact that nobody declared is the
        # exact failure this whole tool exists to prevent, so the rule is now the same
        # for every kind.
        if _NOT_ESTABLISHED_RE.match(raw) or not raw.strip():
            self._values[path] = NOT_ESTABLISHED
            self.autosave()
            return None

        if question.kind == "bool":
            parsed_bool = _parse_bool(raw)
            if parsed_bool is None:
                return MSG_ANSWER_YES_OR_NO
            value: object = parsed_bool
        elif question.kind == "int":
            parsed_int = _parse_int(raw)
            if parsed_int is None:
                return MSG_NOT_A_WHOLE_NUMBER
            value = parsed_int
        elif question.kind == "float":
            parsed_float = _parse_float(raw)
            if parsed_float is None:
                return MSG_NOT_A_NUMBER
            value = parsed_float
        elif question.kind == "str":
            stripped = raw.strip()
            if not stripped:
                # Blank text means "I have not answered this" -- NOT an error.
                self._values[path] = NOT_ESTABLISHED
                self.autosave()
                return None
            # The credential firewall runs BEFORE the value is stored, so a
            # refused answer never reaches the working file.
            try:
                credentials.assert_clean(stripped)
            except ValueError as exc:
                return f"{MSG_LOOKS_LIKE_A_CREDENTIAL} ({exc})"
            value = stripped
        elif question.kind == "list":
            stripped = raw.strip()
            if not stripped:
                self._values[path] = NOT_ESTABLISHED
                self.autosave()
                return None
            items = _parse_list(stripped)
            if not items:
                # A list of only blanks is "I have not answered this".
                self._values[path] = NOT_ESTABLISHED
                self.autosave()
                return None
            try:
                credentials.assert_clean(items)
            except ValueError as exc:
                return f"{MSG_LOOKS_LIKE_A_CREDENTIAL} ({exc})"
            value = items
        else:
            # Defensive: an unknown kind would be a programming error and
            # must not be coerced into one of the known kinds silently.
            return f"Unsupported question kind: {question.kind!r}."

        self._values[path] = value
        self.autosave()
        return None

    def clear(self, path: str) -> None:
        """Return a question to :data:`NOT_ESTABLISHED`. An adviser who
        mistyped must be able to UN-answer, not just overwrite."""
        if path not in self._values:
            return
        del self._values[path]
        self.autosave()

    # --- progress ----------------------------------------------------------

    def progress(self, section: str) -> SectionProgress:
        """Count answered questions in one section. :data:`NOT_ESTABLISHED`
        never counts as answered."""
        questions = self.questions_in(section)
        answered = 0
        for question in questions:
            value = self._values.get(question.path, NOT_ESTABLISHED)
            if value is not NOT_ESTABLISHED:
                answered += 1
        return SectionProgress(title=section, answered=answered, total=len(questions))

    def total_progress(self) -> SectionProgress:
        """Sum of answered and total across every section, under one title."""
        answered = 0
        total = 0
        for section in self.sections():
            section_progress = self.progress(section)
            answered += section_progress.answered
            total += section_progress.total
        return SectionProgress(title="", answered=answered, total=total)

    # --- declaration -------------------------------------------------------

    def to_declaration(self) -> dict[str, object]:
        """Build the declaration dict for the engine.

        :data:`NOT_ESTABLISHED` answers are dropped here: their ABSENCE is
        what causes the engine to report ``contested``, and that distinction
        is the whole reason this module exists. ``legal_name`` and
        ``author`` are passed through; the schema will refuse an empty
        ``legal_name`` at load time, which is the right place for that
        refusal.
        """
        answers = {
            path: value
            for path, value in self._values.items()
            if value is not NOT_ESTABLISHED
        }
        return answers_to_declaration(
            answers,
            legal_name=self.legal_name,
            author=self.author,
            jurisdictions=list(self._jurisdictions),
        )

    def save(self, path: Path) -> None:
        """Write the real declaration as JSON. Refused when ``legal_name``
        is empty or there are no jurisdictions -- the schema requires both,
        and a refusal here beats a traceback at load time."""
        if not self.legal_name:
            raise ValueError(MSG_LEGAL_NAME_MISSING)
        if not self._jurisdictions:
            raise ValueError(MSG_JURISDICTION_MISSING)
        path.write_text(
            json.dumps(self.to_declaration(), indent=2), encoding="utf-8"
        )

    @classmethod
    def resume(cls, path: Path) -> "IntakeForm":
        """Reload a working file (or a CLI-written declaration).

        The working-file format is a valid declaration:
        ``answers_to_declaration`` on the way out, ``declaration_to_answers``
        on the way back. That is what lets the same reader open both a form's
        autosave and a declaration the CLI interview wrote, which is the
        test ``test_resuming_a_saved_declaration_carries_the_answers_in``.

        On a corrupt or unparseable file this RAISES. A form that quietly
        starts blank after a crash would look exactly like a lost two-hour
        meeting; the right behaviour is to refuse and let the user see why.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DeclarationError(MSG_WORKING_FILE_UNREADABLE) from exc
        if not isinstance(raw, dict):
            raise DeclarationError(MSG_WORKING_FILE_UNREADABLE)

        form = cls(working_file=path)

        # Two shapes open here. A working file carries this form's own answers verbatim
        # and is the lossless one. A plain declaration is what the CLI interview writes,
        # and an adviser who started in the terminal must be able to finish in the
        # window — so it is still accepted, with the loss that shape implies.
        if raw.get(_WORKING_FILE_MARKER):
            form.legal_name = str(raw.get("legal_name") or "")
            form.author = str(raw.get("declaration_author") or "")
            jurisdictions = raw.get("jurisdictions")
            if isinstance(jurisdictions, list):
                for entry in jurisdictions:
                    if isinstance(entry, dict) and entry.get("country"):
                        sub_units = entry.get("sub_units")
                        form.add_jurisdiction(
                            str(entry["country"]),
                            sub_units=[str(u) for u in sub_units]
                            if isinstance(sub_units, list)
                            else None,
                            sub_units_complete=bool(
                                entry.get("sub_units_complete", True)
                            ),
                        )
            answers = raw.get("answers")
            if isinstance(answers, dict):
                for answer_path, value in answers.items():
                    if answer_path in _QUESTIONS_BY_PATH:
                        form._values[answer_path] = value
            return form
        # Identity fields first -- they live on the form, not in the answers dict.
        org = raw.get("organisation")
        if isinstance(org, dict):
            legal_name = org.get("legal_name")
            if isinstance(legal_name, str):
                form.legal_name = legal_name
        author = raw.get("declaration_author")
        if isinstance(author, str):
            form.author = author

        # Jurisdictions -- accept the form-shaped dicts verbatim. The schema
        # validates shape on load, but a resume must not fail on an
        # unverified file, so we copy in whatever shape the source had and
        # normalise the bits the form depends on (country code, sub-units).
        jur_raw = raw.get("jurisdictions", [])
        if isinstance(jur_raw, list):
            for entry in jur_raw:
                if not isinstance(entry, dict):
                    continue
                country = entry.get("country")
                if not isinstance(country, str):
                    continue
                sub_units = entry.get("sub_units") or []
                if not isinstance(sub_units, list):
                    sub_units = []
                normalised_sub_units = [
                    str(s) for s in sub_units if isinstance(s, str)
                ]
                complete = entry.get("sub_units_complete", True)
                form._jurisdictions.append(
                    {
                        "country": country.strip().upper(),
                        "sub_units": normalised_sub_units,
                        "sub_units_complete": bool(complete),
                    }
                )

        # Answers -- flatten the declaration back to path-keyed form. The
        # inverse helper skips ``described`` and any None values, which is
        # exactly the rule this form enforces.
        answers = declaration_to_answers(raw)
        for question_path, value in answers.items():
            form._values[question_path] = value

        return form

    # --- persistence -------------------------------------------------------

    def autosave(self) -> None:
        """Write the form's own state to the working file, losslessly and durably.

        The working file is NOT a declaration. It was one, and that lost answers: a
        declaration can only hold what the engine can consume, so every answer whose
        path has no field on a block dataclass was dropped on the way out and gone on
        the way back. Until the schema grew a field for every asked question, ten
        questions were in that position, and reopening a meeting through a saved
        declaration silently discarded eleven of eighty-three answers the client had
        actually given.

        A declaration is what you PRODUCE, at the end, from `save`. Work in progress
        belongs in a container that holds everything the adviser typed, so this writes
        the answers verbatim under a marker `resume` can recognise.

        Temp-file-then-rename, never a direct write. `write_text` truncates the target
        and then writes it; a process that dies in between — a closed lid, a battery,
        the exact crash this autosave exists to survive — would leave the file
        half-written and unopenable. `os.replace` is atomic within a filesystem, so the
        temporary lives beside the target and a reader sees either the previous good
        file or the new one, never half of either.
        """
        if self._working_file is None:
            return
        state: dict[str, object] = {
            _WORKING_FILE_MARKER: _WORKING_FILE_VERSION,
            "legal_name": self.legal_name,
            "declaration_author": self.author,
            "jurisdictions": [dict(entry) for entry in self._jurisdictions],
            "answers": {
                path: value
                for path, value in self._values.items()
                if value is not NOT_ESTABLISHED
            },
        }
        partial = self._working_file.with_name(self._working_file.name + ".partial")
        partial.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(partial, self._working_file)


__all__ = [
    "AUTHORED_TEXT",
    "IntakeForm",
    "NOT_ESTABLISHED",
    "SectionProgress",
]
