"""Schema definition and validator for samanvaya declarations.

This module describes the shape of a legally significant declaration
and turns a free-form Python dictionary into a fully typed, frozen
``Declaration`` object.  The hard rules in the project brief require us
to refuse unknown keys, refuse secret-shaped strings and never invent
statutory constants — this validator does the first two, and by
construction cannot do the third.
"""

from __future__ import annotations

import dataclasses

from datetime import date
from enum import Enum
from typing import Any, cast, Callable, Mapping

from samanvaya.credentials import assert_clean
from samanvaya.types import (
    ChildProcessingDeclaration,
    NoticeDeclaration,
    BreachWorkflow,
    ConsentMechanism,
    CrossBorderDeclaration,
    Declaration,
    DeclarationError,
    DsrWorkflow,
    GovernanceDeclaration,
    JurisdictionRef,
    Organisation,
    RetentionRule,
    SafeguardPair,
)


SCHEMA_VERSION: str = "1.0"
"""Wire version of the declaration schema accepted by this validator."""

ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "declaration_author",
        "declaration_date",
        "organisation",
        "jurisdictions",
        "data_categories",
        "purposes",
        "recipients",
        "security_safeguards",
        "children",
        "notice",
        "consent_mechanism",
        "breach_workflow",
        "dsr_workflow",
        "governance",
        "cross_border",
        "retention",
    }
)
"""The closed set of top-level keys the validator will accept."""


_ORG_KEYS: frozenset[str] = frozenset(
    {
        "legal_name",
        "legal_form",
        "employee_count",
        "annual_revenue_usd",
        "consumer_count",
        "is_public_authority",
        "is_healthcare_provider",
        "is_financial_institution",
        "is_educational_institution",
        "offers_services_to_children",
        "conducts_large_scale_monitoring",
        "processes_special_category_data",
        "notified_significant_data_fiduciary",
        "share_of_revenue_from_selling_personal_data",
    }
)
"""The closed set of keys permitted inside ``organisation``."""

_CHILDREN_KEYS: frozenset[str] = frozenset(
    {
        "described",
        "processes_data_of_children",
        "verifiable_parental_consent",
        "tracks_children",
        "targeted_advertising_to_children",
        "likely_detrimental_effect",
        "age_verification_method",
    }
)
"""The closed set of keys permitted inside ``children``."""


_NOTICE_KEYS: frozenset[str] = frozenset(
    {
        "described",
        "describes_personal_data",
        "describes_purpose",
        "describes_rights_exercise_method",
        "describes_complaint_method_to_regulator",
        "available_in_local_language",
        "given_before_or_with_consent_request",
        "identifies_recipients",
        "states_retention_period",
        "states_controller_identity",
        "states_transfer_destinations",
    }
)
"""The closed set of keys permitted inside ``notice``."""


_CONSENT_KEYS: frozenset[str] = frozenset(
    {
        "described",
        "mechanism",
        "is_opt_in",
        "withdrawal_as_easy_as_giving",
        "granular_by_purpose",
        "parental_consent_verifiable",
        "records_kept",
        "is_free",
        "is_specific",
        "is_informed",
        "is_unconditional",
        "is_unambiguous",
        "has_clear_affirmative_action",
        "limited_to_specified_purpose",
        "is_pre_checked",
        "is_bundled_with_unrelated_terms",
        "request_in_clear_plain_language",
        "local_language_option_offered",
        "privacy_officer_contact_provided",
        "obtained_via_consent_manager",
    }
)
"""The closed set of keys permitted inside ``consent_mechanism``."""

_BREACH_KEYS: frozenset[str] = frozenset(
    {
        "described",
        "notifies_regulator",
        "regulator_deadline_hours",
        "notifies_affected_individuals",
        "individual_notification_trigger",
        "maintains_breach_register",
        "register_retention_period",
    }
)
"""The closed set of keys permitted inside ``breach_workflow``."""

_DSR_KEYS: frozenset[str] = frozenset(
    {
        "described",
        "rights_supported",
        "response_deadline_days",
        "grievance_mechanism_published",
        "grievance_response_period_days",
        "identity_verification",
    }
)
"""The closed set of keys permitted inside ``dsr_workflow``."""

_GOVERNANCE_KEYS: frozenset[str] = frozenset(
    {
        "has_privacy_officer",
        "privacy_officer_contact_published",
        "conducts_impact_assessments",
        "impact_assessment_frequency_months",
        "conducts_audits",
        "audit_frequency_months",
        "maintains_processing_records",
        "processor_contracts_in_place",
        "processor_contract_covers_security",
    }
)
"""The closed set of keys permitted inside ``governance``."""

_CROSS_BORDER_KEYS: frozenset[str] = frozenset(
    {
        "transfers_outside_jurisdiction",
        "destination_countries",
        "transfer_mechanism",
        "impact_assessment_per_transfer",
    }
)
"""The closed set of keys permitted inside ``cross_border``."""

_JURISDICTION_KEYS: frozenset[str] = frozenset({"country", "sub_units", "sub_units_complete"})
_SAFEGUARD_KEYS: frozenset[str] = frozenset({"control", "value"})
_RETENTION_KEYS: frozenset[str] = frozenset({"purpose", "period", "basis"})


def _err(path: str, expected: str, found: Any) -> DeclarationError:
    """Build a DeclarationError that names the path and what was expected."""
    return DeclarationError(f"at {path}: expected {expected}, got {type(found).__name__}")


def _require_keys(obj: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    """Refuse keys the schema does not know about at this level."""
    unknown = set(obj) - allowed
    if unknown:
        first = sorted(unknown)[0]
        raise DeclarationError(f"unknown key '{first}' at {path}")


def _expect_str(value: Any, path: str, *, allow_none: bool = False, non_empty: bool = False) -> str | None:
    """Reject ints, floats and bools where a string is required."""
    if value is None:
        if allow_none:
            return None
        raise _err(path, "string", value)
    if isinstance(value, bool) or not isinstance(value, str):
        raise _err(path, "string", value)
    if non_empty and not value:
        raise DeclarationError(f"at {path}: expected non-empty string, got empty value")
    return value


def _expect_int(value: Any, path: str, *, allow_none: bool = False) -> int | None:
    """Reject booleans explicitly: ``True`` is not a legal employee count."""
    if value is None:
        if allow_none:
            return None
        raise _err(path, "integer", value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _err(path, "integer", value)
    return value


def _expect_float(value: Any, path: str, *, allow_none: bool = False) -> float | None:
    """Accept int or float but not bool, because bool is not a legal ratio."""
    if value is None:
        if allow_none:
            return None
        raise _err(path, "number", value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _err(path, "number", value)
    return float(value)


def _expect_bool(value: Any, path: str, *, allow_none: bool = False) -> bool | None:
    """Accept only true booleans; ``1`` is not a declaration of ``True``."""
    if value is None:
        if allow_none:
            return None
        raise _err(path, "boolean", value)
    if not isinstance(value, bool):
        raise _err(path, "boolean", value)
    return value


def _expect_list_of_str(value: Any, path: str) -> tuple[str, ...]:
    """Reject a scalar where a list is expected."""
    if not isinstance(value, list):
        raise _err(path, "list of strings", value)
    out: list[str] = []
    for i, item in enumerate(value):
        out.append(_expect_str(item, f"{path}[{i}]", non_empty=True) or "")
    return tuple(out)


def _expect_date(value: Any, path: str) -> date | None:
    """Accept ISO strings or real ``date`` objects and refuse anything else."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, bool):
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        raise _err(path, "ISO date string YYYY-MM-DD", value)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DeclarationError(f"at {path}: not a valid YYYY-MM-DD date: {exc}") from None


def _build_organisation(obj: Mapping[str, Any]) -> Organisation:
    _require_keys(obj, _ORG_KEYS, "organisation")
    if "legal_name" not in obj:
        raise DeclarationError("organisation is missing required key 'legal_name'")
    legal_name = _expect_str(obj["legal_name"], "organisation.legal_name", non_empty=True) or ""
    return Organisation(
        legal_name=legal_name,
        legal_form=_expect_str(obj.get("legal_form"), "organisation.legal_form", allow_none=True),
        employee_count=_expect_int(
            obj.get("employee_count"), "organisation.employee_count", allow_none=True
        ),
        annual_revenue_usd=_expect_int(
            obj.get("annual_revenue_usd"), "organisation.annual_revenue_usd", allow_none=True
        ),
        consumer_count=_expect_int(
            obj.get("consumer_count"), "organisation.consumer_count", allow_none=True
        ),
        is_public_authority=_expect_bool(
            obj.get("is_public_authority"), "organisation.is_public_authority", allow_none=True
        ),
        is_healthcare_provider=_expect_bool(
            obj.get("is_healthcare_provider"), "organisation.is_healthcare_provider", allow_none=True
        ),
        is_financial_institution=_expect_bool(
            obj.get("is_financial_institution"),
            "organisation.is_financial_institution",
            allow_none=True,
        ),
        is_educational_institution=_expect_bool(
            obj.get("is_educational_institution"),
            "organisation.is_educational_institution",
            allow_none=True,
        ),
        offers_services_to_children=_expect_bool(
            obj.get("offers_services_to_children"),
            "organisation.offers_services_to_children",
            allow_none=True,
        ),
        conducts_large_scale_monitoring=_expect_bool(
            obj.get("conducts_large_scale_monitoring"),
            "organisation.conducts_large_scale_monitoring",
            allow_none=True,
        ),
        processes_special_category_data=_expect_bool(
            obj.get("processes_special_category_data"),
            "organisation.processes_special_category_data",
            allow_none=True,
        ),
        notified_significant_data_fiduciary=_expect_bool(
            obj.get("notified_significant_data_fiduciary"),
            "organisation.notified_significant_data_fiduciary",
            allow_none=True,
        ),
        share_of_revenue_from_selling_personal_data=_expect_float(
            obj.get("share_of_revenue_from_selling_personal_data"),
            "organisation.share_of_revenue_from_selling_personal_data",
            allow_none=True,
        ),
    )


def _build_jurisdiction(obj: Mapping[str, Any], index: int) -> JurisdictionRef:
    _require_keys(obj, _JURISDICTION_KEYS, f"jurisdictions[{index}]")
    country = _expect_str(obj.get("country"), f"jurisdictions[{index}].country", non_empty=True) or ""
    sub_units_raw = obj.get("sub_units", [])
    if sub_units_raw is None:
        sub_units_raw = []
    sub_units = _expect_list_of_str(sub_units_raw, f"jurisdictions[{index}].sub_units")
    complete = _expect_bool(
        obj.get("sub_units_complete", False),
        f"jurisdictions[{index}].sub_units_complete",
    )
    return JurisdictionRef(country=country, sub_units=sub_units, sub_units_complete=bool(complete))


def _build_safeguard(obj: Mapping[str, Any], index: int) -> SafeguardPair:
    _require_keys(obj, _SAFEGUARD_KEYS, f"security_safeguards[{index}]")
    control = _expect_str(obj.get("control"), f"security_safeguards[{index}].control", non_empty=True) or ""
    value = _expect_str(obj.get("value"), f"security_safeguards[{index}].value", non_empty=True) or ""
    return SafeguardPair(control=control, value=value)


def _build_retention(obj: Mapping[str, Any], index: int) -> RetentionRule:
    _require_keys(obj, _RETENTION_KEYS, f"retention[{index}]")
    purpose = _expect_str(obj.get("purpose"), f"retention[{index}].purpose", non_empty=True) or ""
    period = _expect_str(obj.get("period"), f"retention[{index}].period", non_empty=True) or ""
    basis = obj.get("basis")
    if basis is not None:
        basis = _expect_str(basis, f"retention[{index}].basis")
    return RetentionRule(purpose=purpose, period=period, basis=basis)


def _build_children(obj: Mapping[str, Any]) -> ChildProcessingDeclaration:
    """Build the declared children-processing facts. Undeclared limbs stay ``None``."""
    _require_keys(obj, _CHILDREN_KEYS, "children")
    return ChildProcessingDeclaration(
        described=_expect_bool(obj.get("described", False), "children.described") or False,
        processes_data_of_children=_expect_bool(obj.get("processes_data_of_children"), "children.processes_data_of_children", allow_none=True),
        age_verification_method=_expect_str(obj.get("age_verification_method"), "children.age_verification_method", allow_none=True),
        verifiable_parental_consent=_expect_bool(obj.get("verifiable_parental_consent"), "children.verifiable_parental_consent", allow_none=True),
        tracks_children=_expect_bool(obj.get("tracks_children"), "children.tracks_children", allow_none=True),
        targeted_advertising_to_children=_expect_bool(obj.get("targeted_advertising_to_children"), "children.targeted_advertising_to_children", allow_none=True),
        likely_detrimental_effect=_expect_bool(obj.get("likely_detrimental_effect"), "children.likely_detrimental_effect", allow_none=True),
    )


def _build_notice(obj: Mapping[str, Any]) -> NoticeDeclaration:
    """Build the declared notice content. Undeclared limbs stay ``None``.

    ``None`` means the adviser did not record an answer, which the engine reports as
    CONTESTED. It must never be collapsed to ``False``, because "the client did not
    say" and "the client said no" are different findings and only one of them is a gap.
    """
    _require_keys(obj, _NOTICE_KEYS, "notice")
    return NoticeDeclaration(
        described=_expect_bool(obj.get("described", False), "notice.described") or False,
        describes_personal_data=_expect_bool(obj.get("describes_personal_data"), "notice.describes_personal_data", allow_none=True),
        describes_purpose=_expect_bool(obj.get("describes_purpose"), "notice.describes_purpose", allow_none=True),
        describes_rights_exercise_method=_expect_bool(obj.get("describes_rights_exercise_method"), "notice.describes_rights_exercise_method", allow_none=True),
        describes_complaint_method_to_regulator=_expect_bool(obj.get("describes_complaint_method_to_regulator"), "notice.describes_complaint_method_to_regulator", allow_none=True),
        available_in_local_language=_expect_bool(obj.get("available_in_local_language"), "notice.available_in_local_language", allow_none=True),
        given_before_or_with_consent_request=_expect_bool(obj.get("given_before_or_with_consent_request"), "notice.given_before_or_with_consent_request", allow_none=True),
        identifies_recipients=_expect_bool(obj.get("identifies_recipients"), "notice.identifies_recipients", allow_none=True),
        states_retention_period=_expect_bool(obj.get("states_retention_period"), "notice.states_retention_period", allow_none=True),
        states_controller_identity=_expect_bool(obj.get("states_controller_identity"), "notice.states_controller_identity", allow_none=True),
        states_transfer_destinations=_expect_bool(obj.get("states_transfer_destinations"), "notice.states_transfer_destinations", allow_none=True),
    )


def _build_consent(obj: Mapping[str, Any]) -> ConsentMechanism:
    _require_keys(obj, _CONSENT_KEYS, "consent_mechanism")
    return ConsentMechanism(
        described=_expect_bool(obj.get("described", False), "consent_mechanism.described") or False,
        mechanism=_expect_str(obj.get("mechanism"), "consent_mechanism.mechanism", allow_none=True),
        is_opt_in=_expect_bool(obj.get("is_opt_in"), "consent_mechanism.is_opt_in", allow_none=True),
        withdrawal_as_easy_as_giving=_expect_bool(obj.get("withdrawal_as_easy_as_giving"), "consent_mechanism.withdrawal_as_easy_as_giving", allow_none=True),
        granular_by_purpose=_expect_bool(obj.get("granular_by_purpose"), "consent_mechanism.granular_by_purpose", allow_none=True),
        parental_consent_verifiable=_expect_bool(obj.get("parental_consent_verifiable"), "consent_mechanism.parental_consent_verifiable", allow_none=True),
        records_kept=_expect_bool(obj.get("records_kept"), "consent_mechanism.records_kept", allow_none=True),
        is_free=_expect_bool(obj.get("is_free"), "consent_mechanism.is_free", allow_none=True),
        is_specific=_expect_bool(obj.get("is_specific"), "consent_mechanism.is_specific", allow_none=True),
        is_informed=_expect_bool(obj.get("is_informed"), "consent_mechanism.is_informed", allow_none=True),
        is_unconditional=_expect_bool(obj.get("is_unconditional"), "consent_mechanism.is_unconditional", allow_none=True),
        is_unambiguous=_expect_bool(obj.get("is_unambiguous"), "consent_mechanism.is_unambiguous", allow_none=True),
        has_clear_affirmative_action=_expect_bool(obj.get("has_clear_affirmative_action"), "consent_mechanism.has_clear_affirmative_action", allow_none=True),
        limited_to_specified_purpose=_expect_bool(obj.get("limited_to_specified_purpose"), "consent_mechanism.limited_to_specified_purpose", allow_none=True),
        is_pre_checked=_expect_bool(obj.get("is_pre_checked"), "consent_mechanism.is_pre_checked", allow_none=True),
        is_bundled_with_unrelated_terms=_expect_bool(obj.get("is_bundled_with_unrelated_terms"), "consent_mechanism.is_bundled_with_unrelated_terms", allow_none=True),
        request_in_clear_plain_language=_expect_bool(obj.get("request_in_clear_plain_language"), "consent_mechanism.request_in_clear_plain_language", allow_none=True),
        local_language_option_offered=_expect_bool(obj.get("local_language_option_offered"), "consent_mechanism.local_language_option_offered", allow_none=True),
        privacy_officer_contact_provided=_expect_bool(obj.get("privacy_officer_contact_provided"), "consent_mechanism.privacy_officer_contact_provided", allow_none=True),
        obtained_via_consent_manager=_expect_bool(obj.get("obtained_via_consent_manager"), "consent_mechanism.obtained_via_consent_manager", allow_none=True),
    )


def _build_breach(obj: Mapping[str, Any]) -> BreachWorkflow:
    _require_keys(obj, _BREACH_KEYS, "breach_workflow")
    return BreachWorkflow(
        described=_expect_bool(obj.get("described", False), "breach_workflow.described") or False,
        notifies_regulator=_expect_bool(
            obj.get("notifies_regulator"), "breach_workflow.notifies_regulator", allow_none=True
        ),
        regulator_deadline_hours=_expect_int(
            obj.get("regulator_deadline_hours"),
            "breach_workflow.regulator_deadline_hours",
            allow_none=True,
        ),
        notifies_affected_individuals=_expect_bool(
            obj.get("notifies_affected_individuals"),
            "breach_workflow.notifies_affected_individuals",
            allow_none=True,
        ),
        individual_notification_trigger=_expect_str(
            obj.get("individual_notification_trigger"),
            "breach_workflow.individual_notification_trigger",
            allow_none=True,
        ),
        maintains_breach_register=_expect_bool(
            obj.get("maintains_breach_register"),
            "breach_workflow.maintains_breach_register",
            allow_none=True,
        ),
        register_retention_period=_expect_str(
            obj.get("register_retention_period"),
            "breach_workflow.register_retention_period",
            allow_none=True,
        ),
    )


def _build_dsr(obj: Mapping[str, Any]) -> DsrWorkflow:
    _require_keys(obj, _DSR_KEYS, "dsr_workflow")
    rights = _expect_list_of_str(
        obj.get("rights_supported", []), "dsr_workflow.rights_supported"
    )
    return DsrWorkflow(
        described=_expect_bool(obj.get("described", False), "dsr_workflow.described") or False,
        rights_supported=rights,
        response_deadline_days=_expect_int(
            obj.get("response_deadline_days"), "dsr_workflow.response_deadline_days", allow_none=True
        ),
        grievance_mechanism_published=_expect_bool(
            obj.get("grievance_mechanism_published"),
            "dsr_workflow.grievance_mechanism_published",
            allow_none=True,
        ),
        grievance_response_period_days=_expect_int(
            obj.get("grievance_response_period_days"),
            "dsr_workflow.grievance_response_period_days",
            allow_none=True,
        ),
        identity_verification=_expect_bool(
            obj.get("identity_verification"),
            "dsr_workflow.identity_verification",
            allow_none=True,
        ),
    )


def _build_governance(obj: Mapping[str, Any]) -> GovernanceDeclaration:
    _require_keys(obj, _GOVERNANCE_KEYS, "governance")
    return GovernanceDeclaration(
        has_privacy_officer=_expect_bool(
            obj.get("has_privacy_officer"), "governance.has_privacy_officer", allow_none=True
        ),
        privacy_officer_contact_published=_expect_bool(
            obj.get("privacy_officer_contact_published"),
            "governance.privacy_officer_contact_published",
            allow_none=True,
        ),
        conducts_impact_assessments=_expect_bool(
            obj.get("conducts_impact_assessments"),
            "governance.conducts_impact_assessments",
            allow_none=True,
        ),
        impact_assessment_frequency_months=_expect_int(
            obj.get("impact_assessment_frequency_months"),
            "governance.impact_assessment_frequency_months",
            allow_none=True,
        ),
        conducts_audits=_expect_bool(
            obj.get("conducts_audits"), "governance.conducts_audits", allow_none=True
        ),
        audit_frequency_months=_expect_int(
            obj.get("audit_frequency_months"), "governance.audit_frequency_months", allow_none=True
        ),
        maintains_processing_records=_expect_bool(
            obj.get("maintains_processing_records"),
            "governance.maintains_processing_records",
            allow_none=True,
        ),
        processor_contracts_in_place=_expect_bool(
            obj.get("processor_contracts_in_place"),
            "governance.processor_contracts_in_place",
            allow_none=True,
        ),
        processor_contract_covers_security=_expect_bool(
            obj.get("processor_contract_covers_security"),
            "governance.processor_contract_covers_security",
            allow_none=True,
        ),
    )


def _build_cross_border(obj: Mapping[str, Any]) -> CrossBorderDeclaration:
    _require_keys(obj, _CROSS_BORDER_KEYS, "cross_border")
    destinations = _expect_list_of_str(
        obj.get("destination_countries", []), "cross_border.destination_countries"
    )
    return CrossBorderDeclaration(
        transfers_outside_jurisdiction=_expect_bool(
            obj.get("transfers_outside_jurisdiction"),
            "cross_border.transfers_outside_jurisdiction",
            allow_none=True,
        ),
        destination_countries=destinations,
        transfer_mechanism=_expect_str(
            obj.get("transfer_mechanism"), "cross_border.transfer_mechanism", allow_none=True
        ),
        impact_assessment_per_transfer=_expect_bool(
            obj.get("impact_assessment_per_transfer"),
            "cross_border.impact_assessment_per_transfer",
            allow_none=True,
        ),
    )


def _expect_mapping(obj: Any, path: str) -> Mapping[str, Any]:
    """Refuse anything that is not a JSON/YAML mapping."""
    if not isinstance(obj, Mapping):
        raise DeclarationError(f"at {path}: expected mapping, got {type(obj).__name__}")
    return obj


def validate(obj: Mapping[str, Any]) -> Declaration:
    """Turn a raw dict into a fully typed ``Declaration`` or raise.

    Unknown keys are refused everywhere they might occur; required
    fields raise a ``DeclarationError`` naming the missing field; strict
    scalar typing means ``True`` is not an acceptable integer.
    """
    if not isinstance(obj, Mapping):
        raise DeclarationError(f"top level: expected mapping, got {type(obj).__name__}")

    # The credential firewall runs FIRST, before any structural work. It is enforced
    # here rather than in the loader because `validate` is public API: a caller that
    # hands us an already-parsed dict must get the same refusal as one that hands us a
    # file. Holding a client credential would make the tool's author a Data Processor
    # in his own right, with his own breach-notification duty.
    try:
        assert_clean(obj)
    except ValueError as exc:  # raised by the firewall; never carries the secret text
        raise DeclarationError(str(exc)) from None

    _require_keys(obj, ALLOWED_TOP_LEVEL_KEYS, "<top>")

    if "schema_version" not in obj:
        raise DeclarationError("top level: missing required field 'schema_version'")
    schema_version = _expect_str(obj["schema_version"], "schema_version", non_empty=True) or ""

    if "declaration_author" not in obj:
        raise DeclarationError("top level: missing required field 'declaration_author'")
    author = _expect_str(obj["declaration_author"], "declaration_author", non_empty=True) or ""

    if "organisation" not in obj:
        raise DeclarationError("top level: missing required field 'organisation'")
    org_obj = _expect_mapping(obj["organisation"], "organisation")
    organisation = _build_organisation(org_obj)

    if "jurisdictions" not in obj:
        raise DeclarationError("top level: missing required field 'jurisdictions'")
    jur_raw = obj["jurisdictions"]
    if not isinstance(jur_raw, list):
        raise _err("jurisdictions", "list", jur_raw)
    jurisdictions = tuple(_build_jurisdiction(_expect_mapping(j, f"jurisdictions[{i}]"), i) for i, j in enumerate(jur_raw))

    data_categories = _expect_list_of_str(
        obj.get("data_categories", []), "data_categories"
    )
    purposes = _expect_list_of_str(obj.get("purposes", []), "purposes")
    recipients = _expect_list_of_str(obj.get("recipients", []), "recipients")

    safe_raw = obj.get("security_safeguards", [])
    if not isinstance(safe_raw, list):
        raise _err("security_safeguards", "list", safe_raw)
    safeguards = tuple(_build_safeguard(_expect_mapping(s, f"security_safeguards[{i}]"), i) for i, s in enumerate(safe_raw))

    children = _build_children(_expect_mapping(obj.get("children", {}), "children"))
    notice = _build_notice(_expect_mapping(obj.get("notice", {}), "notice"))
    consent_obj = obj.get("consent_mechanism", {})
    consent = _build_consent(_expect_mapping(consent_obj, "consent_mechanism"))

    breach_obj = obj.get("breach_workflow", {})
    breach = _build_breach(_expect_mapping(breach_obj, "breach_workflow"))

    dsr_obj = obj.get("dsr_workflow", {})
    dsr = _build_dsr(_expect_mapping(dsr_obj, "dsr_workflow"))

    gov_obj = obj.get("governance", {})
    governance = _build_governance(_expect_mapping(gov_obj, "governance"))

    cb_obj = obj.get("cross_border", {})
    cross_border = _build_cross_border(_expect_mapping(cb_obj, "cross_border"))

    ret_raw = obj.get("retention", [])
    if not isinstance(ret_raw, list):
        raise _err("retention", "list", ret_raw)
    retention = tuple(_build_retention(_expect_mapping(r, f"retention[{i}]"), i) for i, r in enumerate(ret_raw))

    declaration_date = _expect_date(obj.get("declaration_date"), "declaration_date")

    return Declaration(
        schema_version=schema_version,
        declaration_author=author,
        declaration_date=declaration_date,
        organisation=organisation,
        jurisdictions=jurisdictions,
        data_categories=data_categories,
        purposes=purposes,
        recipients=recipients,
        security_safeguards=safeguards,
        children=children,
        notice=notice,
        consent_mechanism=consent,
        breach_workflow=breach,
        dsr_workflow=dsr,
        governance=governance,
        cross_border=cross_border,
        retention=retention,
    )


def _to_jsonable(value: Any) -> Any:
    """Recursively convert a Declaration tree into plain JSON-safe types.

    This walks the dataclasses generically rather than enumerating their fields by
    hand. A hand-written key list is a silent-drift hazard: add a field to the
    dataclass, forget the list here, and the declaration hash stops covering it — so
    two materially different declarations hash identically and the report's integrity
    claim quietly becomes false. Walking `dataclasses.fields` makes that impossible.

    Field order follows declaration order, and the hash is taken over
    ``json.dumps(..., sort_keys=True)``, so the output is deterministic either way.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _to_jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (frozenset, set)):
        return sorted(_to_jsonable(v) for v in value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in sorted(value.items())}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"cannot canonicalise {type(value).__name__} for hashing")


def canonical_dict(declaration: Declaration) -> dict[str, Any]:
    """Return a deterministic, JSON-serialisable view of ``declaration``.

    The hash is computed over this structure so that YAML and JSON
    representations of the same content produce the same digest.
    """
    # _to_jsonable is annotated -> Any because it handles heterogeneous nodes
    # (lists, scalars, mappings). At its top level it always returns a mapping
    # for a dataclass input, which is what canonical_dict's signature promises.
    return cast("dict[str, Any]", _to_jsonable(declaration))


__all__ = [
    "ALLOWED_TOP_LEVEL_KEYS",
    "SCHEMA_VERSION",
    "canonical_dict",
    "validate",
]
