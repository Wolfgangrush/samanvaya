"""Samanvaya conformance engine — jurisdiction resolution.

Offline privacy-conformance CLI. This module maps declared country tokens and
ISO 3166-2 sub-national units onto regulatory regimes and expansion targets.
It reaches no network, persists nothing, and deliberately contains NO statutory
constants — no section numbers, dates, ages or thresholds live here.

Two design anchors from the PRD live in this file:

- A3: federated countries (the United States, Canada) emit exactly ONE
  incompleteness notice per country, not one per obligation, and
  ``sub_units_complete=True`` is the only way to assert that the named
  sub-units are exhaustive.
- Determinism: targets are de-duplicated and sorted so that two declarations
  naming the same places in different orders resolve identically.

Sub-national units are ISO 3166-2 codes (``US-CA``, ``CA-QC``) so that a bare
``CA`` at the country level always means Canada and never California.
"""

from __future__ import annotations

from dataclasses import dataclass

from samanvaya.types import (
    Declaration,
    FEDERATED_REGIMES,
    IncompletenessNotice,
    JurisdictionRef,
    RegimeId,
    fact_needed,
)

# NOTE on the EEA: whether Norway, Iceland and Liechtenstein should be treated
# as GDPR regimes by this tool is a legal question that has not been settled on
# primary sources. Their inclusion is therefore deliberately NOT assumed here
# and is flagged for fact sourcing instead.
EEA_EXTENSION_NOTE: str = fact_needed(
    "Confirm on primary sources whether EEA states (NO, IS, LI) are GDPR regimes"
)

# The 27 EU Member States, by ISO 3166-1 alpha-2 code and common English name.
# The membership list is a factual constant, sourced from the official list of
# EU Member States published by the European Union. It is not a statutory
# threshold and is reproduced here only as a country-to-regime mapping.
_EU_MEMBER_STATES: frozenset[str] = frozenset(
    {
        "AT", "Austria",
        "BE", "Belgium",
        "BG", "Bulgaria",
        "HR", "Croatia",
        "CY", "Cyprus",
        "CZ", "Czechia", "Czech Republic",
        "DK", "Denmark",
        "EE", "Estonia",
        "FI", "Finland",
        "FR", "France",
        "DE", "Germany",
        "GR", "Greece",
        "HU", "Hungary",
        "IE", "Ireland",
        "IT", "Italy",
        "LV", "Latvia",
        "LT", "Lithuania",
        "LU", "Luxembourg",
        "MT", "Malta",
        "NL", "Netherlands",
        "PL", "Poland",
        "PT", "Portugal",
        "RO", "Romania",
        "SK", "Slovakia", "Slovak Republic",
        "SI", "Slovenia",
        "ES", "Spain",
        "SE", "Sweden",
    }
)

# Country tokens (ISO 3166-1 alpha-2 codes and common English names), lower-
# cased. "GB"/"UK"/"United Kingdom"/"Great Britain" map to UK_GDPR and never
# to EU_GDPR, because the United Kingdom is its own regime.
_COUNTRY_TOKENS: dict[str, RegimeId] = {
    "in": RegimeId.INDIA,
    "india": RegimeId.INDIA,
    "us": RegimeId.US,
    "usa": RegimeId.US,
    "united states": RegimeId.US,
    "united states of america": RegimeId.US,
    "ca": RegimeId.CANADA,
    "canada": RegimeId.CANADA,
    "eu": RegimeId.EU_GDPR,
}
for _token in _EU_MEMBER_STATES:
    _COUNTRY_TOKENS[_token.casefold()] = RegimeId.EU_GDPR

# ISO 3166-1 alpha-2 country code for each regime, used to validate that a
# sub-unit's prefix matches the country it was declared under.
_REGIME_COUNTRY_CODE: dict[RegimeId, str] = {
    RegimeId.INDIA: "IN",
    RegimeId.EU_GDPR: "EU",
    RegimeId.US: "US",
    RegimeId.CANADA: "CA",
}


@dataclass(frozen=True)
class JurisdictionResolution:
    """The outcome of resolving a declaration's jurisdiction footprint."""

    targets: tuple[tuple[RegimeId, str | None], ...]
    """De-duplicated (regime, sub-unit) pairs the engine must evaluate."""

    regimes: frozenset[RegimeId]
    """Every regime touched by at least one target."""

    completeness: dict[RegimeId, bool]
    """Whether the sub-unit list was asserted exhaustive, per federated regime."""

    notices: tuple[IncompletenessNotice, ...]
    """One notice per federated country whose sub-unit list is not exhaustive."""

    unknown_countries: tuple[str, ...]
    """Country tokens that could not be mapped; never silently dropped."""

    stray_sub_units: tuple[tuple[str, str], ...]
    """(country, sub-unit) pairs that do not belong to the declared country."""


def _lookup_regime(token: str) -> RegimeId | None:
    """Map a country token to a regime, or None if unrecognised."""
    return _COUNTRY_TOKENS.get(token.strip().casefold())


def _notice_for(regime: RegimeId, country: str) -> IncompletenessNotice:
    """Build the single per-country incompleteness notice (A3)."""
    return IncompletenessNotice(
        regime=regime,
        country=country,
        message=(
            f"Sub-national law in {country} binds alongside federal law, and the "
            "tool has not been told whether the declared sub-unit list is "
            "exhaustive; sub-national obligations for unnamed units could not "
            "be evaluated."
        ),
    )


def resolve(declaration: Declaration) -> JurisdictionResolution:
    """Resolve a declaration into regime targets, notices and diagnostics."""
    target_set: set[tuple[RegimeId, str | None]] = set()
    completeness: dict[RegimeId, bool] = {}
    federated_seen: set[tuple[RegimeId, str]] = set()
    notice_regimes: set[RegimeId] = set()
    unknown: set[str] = set()
    strays: list[tuple[str, str]] = []
    stray_seen: set[tuple[str, str]] = set()

    ref: JurisdictionRef
    for ref in declaration.jurisdictions:
        regime = _lookup_regime(ref.country)
        if regime is None:
            # An unknown country is reported, never silently dropped, and
            # produces no target and no regime.
            unknown.add(ref.country)
            continue

        country_code = _REGIME_COUNTRY_CODE[regime]
        federated = regime in FEDERATED_REGIMES

        if federated:
            # Federal sectoral law binds regardless of the state list, so a
            # federal target always accompanies the sub-unit targets.
            target_set.add((regime, None))
        else:
            target_set.add((regime, None))

        for raw in ref.sub_units:
            sub = raw.strip().upper()
            prefix = sub.split("-", 1)[0] if "-" in sub else ""
            if not federated or prefix != country_code:
                # A sub-unit on a unitary country, or one whose prefix
                # contradicts the country it was declared under, is a
                # declaration error: report it and create no target.
                key = (ref.country, raw)
                if key not in stray_seen:
                    stray_seen.add(key)
                    strays.append(key)
                continue
            target_set.add((regime, sub))

        if federated:
            key = (regime, ref.country.strip().casefold())
            federated_seen.add(key)
            # Completeness for a regime is True only if EVERY declaration of
            # that country asserts it.
            completeness[regime] = completeness.get(regime, True) and ref.sub_units_complete
            if not completeness[regime]:
                notice_regimes.add(regime)

    notices = tuple(
        _notice_for(regime, _REGIME_COUNTRY_CODE[regime])
        for regime in sorted(notice_regimes, key=lambda r: r.value)
    )

    targets = tuple(sorted(target_set, key=lambda t: (t[0].value, t[1] or "")))
    regimes = frozenset({regime for regime, _ in target_set})

    return JurisdictionResolution(
        targets=targets,
        regimes=regimes,
        completeness=completeness,
        notices=notices,
        unknown_countries=tuple(sorted(unknown)),
        stray_sub_units=tuple(strays),
    )


def expand(declaration: Declaration) -> tuple[tuple[RegimeId, str | None], ...]:
    """Return the same (regime, sub-unit) pairs as ``resolve``."""
    return resolve(declaration).targets


__all__ = ["EEA_EXTENSION_NOTE", "JurisdictionResolution", "expand", "resolve"]
