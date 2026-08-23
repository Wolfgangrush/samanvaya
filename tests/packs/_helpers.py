"""Shared declaration builders for the pack tests."""

from __future__ import annotations

from samanvaya.types import Declaration, JurisdictionRef, Organisation


def decl(country: str = "IN", **org: object) -> Declaration:
    return Declaration(
        schema_version="1.0",
        organisation=Organisation(legal_name="Acme", **org),  # type: ignore[arg-type]
        jurisdictions=(JurisdictionRef(country),),
        declaration_author="adviser",
    )
