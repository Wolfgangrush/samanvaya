"""Every question the product asks must have somewhere to put the answer.

Found 2026-08-22, by the intake form's resume path losing 11 of 83 answers.

`answers_to_declaration` writes an answer only when its path matches a field on the
matching block dataclass. Ten questions in `QUESTIONS` have no such field, so the
interview asks them, the adviser spends a client's time on them, and the answers are
dropped on the floor.

The harm is not the wasted typing. An obligation whose facts were discarded is reported
as **unresolved** — so the conformance report tells the client that a fact they actually
declared is not established. That is a false statement about the client's own position,
on an advocate's letterhead.

This is the second instance of the same defect. `declaration.security_safeguards` had it,
was found, and was patched with a special case whose comment reads: *"the interview asks
the question and discards what it is told"*. Nobody then asked what else was in that
class. Ten more were.

WHAT THIS FILE DOES, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------------
It does NOT fix the ten. That is a product decision with two defensible answers and it
belongs to the maintainer, not to a test:

  (a) grow the schema so the facts are recorded — honest, larger, and the fields would
      sit inert until a pack reads them; or
  (b) stop asking questions the product cannot consume — smaller, and it throws away
      intake material whose `why` text cites real provisions.

What it does is stop the rot: the known orphans are listed here explicitly, so an
eleventh one fails this test the moment it is added, and removing one from the list is a
deliberate act recorded in a commit. Same shape as the UI baseline — the current state is
pinned, and change has to be argued for rather than happening quietly.
"""

from __future__ import annotations

import dataclasses

import samanvaya.types as T
from samanvaya.interview import QUESTIONS

#: Blocks a question path can address, and the dataclass that defines what each holds.
_BLOCKS: dict[str, type] = {
    "organisation": T.Organisation,
    "notice": T.NoticeDeclaration,
    "consent_mechanism": T.ConsentMechanism,
    "breach_workflow": T.BreachWorkflow,
    "dsr_workflow": T.DsrWorkflow,
    "governance": T.GovernanceDeclaration,
    "cross_border": T.CrossBorderDeclaration,
    "children": T.ChildProcessingDeclaration,
}

#: Paths handled outside the block loop by an explicit special case in
#: `answers_to_declaration`. These DO reach the declaration.
_TOP_LEVEL_SPECIAL_CASES: frozenset[str] = frozenset(
    {"declaration.security_safeguards"}
)

#: Questions asked whose answers the declaration cannot hold, as measured on
#: 2026-08-22. This list is a record of a known defect, not a design. It must only ever
#: get SHORTER.
KNOWN_ORPHANS: frozenset[str] = frozenset(
    {
        "organisation.data_categories",
        "organisation.purposes",
        "organisation.recipients",
        "organisation.retention",
        "notice.is_multi_lingual",
        "consent_mechanism.consent_text",
        "consent_mechanism.withdrawal_method",
        "breach_workflow.incident_severity_rule",
        "dsr_workflow.request_channel",
        "children.responsible_person_designated",
    }
)


def _orphans() -> set[str]:
    """Return every question path with no field to land in."""
    fields = {
        block: {f.name for f in dataclasses.fields(cls)}
        for block, cls in _BLOCKS.items()
    }
    found: set[str] = set()
    for question in QUESTIONS:
        if question.path in _TOP_LEVEL_SPECIAL_CASES:
            continue
        block, _, field = question.path.partition(".")
        if block not in fields or field not in fields[block]:
            found.add(question.path)
    return found


class TestNoQuestionQuietlyLosesItsAnswer:
    def test_no_new_orphan_has_appeared(self) -> None:
        """An eleventh discarded question must fail here, not in front of a client."""
        new = _orphans() - KNOWN_ORPHANS
        assert not new, (
            "these questions are asked and their answers cannot be recorded: "
            + ", ".join(sorted(new))
        )

    def test_the_known_list_has_not_silently_grown_stale(self) -> None:
        """If one is fixed, this fails and the list gets shortened deliberately."""
        fixed = KNOWN_ORPHANS - _orphans()
        assert not fixed, (
            "these are recorded as orphans but now have a home; remove them from "
            "KNOWN_ORPHANS: " + ", ".join(sorted(fixed))
        )

    def test_the_special_cases_really_are_special_cased(self) -> None:
        """A path exempted here must actually reach the declaration."""
        import json

        from samanvaya.interview import answers_to_declaration

        answers: dict[str, object] = {
            path: ["a value"] for path in _TOP_LEVEL_SPECIAL_CASES
        }
        built = answers_to_declaration(
            answers,
            legal_name="Example Ltd",
            author="A. Adviser",
            jurisdictions=[
                {"country": "IN", "sub_units": [], "sub_units_complete": True}
            ],
        )
        blob = json.dumps(built)
        for path in _TOP_LEVEL_SPECIAL_CASES:
            assert "a value" in blob, f"{path} is exempted but still does not land"

    def test_the_scale_of_the_defect_is_stated_not_buried(self) -> None:
        """A number in a test is harder to forget than a number in a commit message."""
        assert len(KNOWN_ORPHANS) == 10, (
            f"the orphan count changed to {len(KNOWN_ORPHANS)}; say so out loud"
        )
        assert len(QUESTIONS) == 83
