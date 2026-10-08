"""Every asked question must round-trip through the declaration schema.

Companion to ``tests/test_question_homes.py``. That file pins the COUNT of orphan
questions — paths with no field on a block dataclass — at zero. This file pins the
SUBSTANCE: for each of the ten paths that were orphaned on 2026-08-22, an answer
built by ``answers_to_declaration`` must survive ``schema.validate`` and land,
unchanged, on the named field of the validated declaration — and a question that
was never answered must leave that field at its default (``None`` or the empty
tuple), never ``False``. An unanswered fact reported as a declared "no" is the
gap/contested confusion the whole input layer exists to prevent.
"""

from __future__ import annotations

import pytest

from samanvaya import schema
from samanvaya.interview import answers_to_declaration
from samanvaya.types import Declaration

_JURISDICTIONS: list[dict[str, object]] = [
    {"country": "IN", "sub_units": [], "sub_units_complete": True}
]

#: path -> (answer as the interview records it, value expected on the validated
#: dataclass). List answers become tuples of str; str answers stay str; the bool
#: answer stays a real bool.
CASES: dict[str, tuple[object, object]] = {
    "organisation.data_categories": (
        ["name", "email address"],
        ("name", "email address"),
    ),
    "organisation.purposes": (
        ["order fulfilment", "marketing"],
        ("order fulfilment", "marketing"),
    ),
    "organisation.recipients": (
        ["payment processor"],
        ("payment processor",),
    ),
    "organisation.retention": (
        "order fulfilment: 5 years; marketing: 1 year",
        "order fulfilment: 5 years; marketing: 1 year",
    ),
    "notice.is_multi_lingual": ("English and Hindi", "English and Hindi"),
    "consent_mechanism.consent_text": (
        "I agree to the processing of my personal data for order fulfilment.",
        "I agree to the processing of my personal data for order fulfilment.",
    ),
    "consent_mechanism.withdrawal_method": (
        "email to the privacy officer",
        "email to the privacy officer",
    ),
    "breach_workflow.incident_severity_rule": (
        "risk of harm to the individual",
        "risk of harm to the individual",
    ),
    "dsr_workflow.request_channel": (
        "the privacy portal web form",
        "the privacy portal web form",
    ),
    "children.responsible_person_designated": (True, True),
}


def _validate(answers: dict[str, object]) -> Declaration:
    """Build a declaration dict from `answers` and run it through the schema."""
    built = answers_to_declaration(
        answers,
        legal_name="Example Ltd",
        author="A. Adviser",
        jurisdictions=[dict(entry) for entry in _JURISDICTIONS],
    )
    return schema.validate(built)


def _field(declaration: Declaration, path: str) -> object:
    block, _, field_name = path.partition(".")
    return getattr(getattr(declaration, block), field_name)


@pytest.mark.parametrize("path", sorted(CASES))
def test_an_answered_question_lands_on_its_field(path: str) -> None:
    """The client's answer reaches the dataclass field unchanged."""
    answer, expected = CASES[path]
    declaration = _validate({path: answer})
    value = _field(declaration, path)
    assert type(value) is type(expected), (
        f"{path}: expected {type(expected).__name__}, got {type(value).__name__}"
    )
    assert value == expected, f"{path}: {value!r} != {expected!r}"


@pytest.mark.parametrize("path", sorted(CASES))
def test_an_unanswered_question_stays_at_its_default(path: str) -> None:
    """A skipped question is absent or None on the field — never False."""
    declaration = _validate({})
    value = _field(declaration, path)
    assert value is not False, (
        f"{path}: an unanswered question became a declared 'no'"
    )
    assert value is None or value == (), (
        f"{path}: expected None or (), got {value!r}"
    )


def test_a_false_answer_is_preserved_as_false() -> None:
    """The one bool among the ten must keep a real 'no' distinct from unanswered."""
    declaration = _validate({"children.responsible_person_designated": False})
    assert declaration.children.responsible_person_designated is False
