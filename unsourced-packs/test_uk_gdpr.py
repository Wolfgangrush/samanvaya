"""Acceptance tests for the UK pack. Tests are not delegated.

Nothing about the UK could be read on primary source on 2026-08-19: legislation.gov.uk
answered every request — HTML, XML and data API, over curl, urllib and WebFetch — with
HTTP 202 and a zero-length body, across eight retries.

So this pack's job tonight is to be **honestly empty**. A delegate reported plausible
values for the UK constants. A research lead is not a source, and these tests exist to
prove those values did not quietly enter the code.
"""

from __future__ import annotations

from datetime import date

from samanvaya.packs.uk_gdpr import pack
from samanvaya.types import FACT_NEEDED_PREFIX, ObligationResult, RegimeId

from ._helpers import decl

AS_AT = date(2026, 8, 19)


class TestMetadata:
    def test_the_regime_is_the_uk(self) -> None:
        assert pack.info().regime is RegimeId.UK_GDPR

    def test_it_is_draft_and_the_reason_names_the_source_failure(self) -> None:
        info = pack.info()
        assert info.draft is True
        assert "202" in info.draft_reason or "legislation.gov.uk" in info.draft_reason

    def test_it_names_the_uk_instruments_and_no_invented_one(self) -> None:
        names = " ".join(pack.info().instruments).lower()
        assert "data protection act 2018" in names
        for banned in ("us gdpr", "singapore gdpr", "canada gdpr"):
            assert banned not in names

    def test_it_covers_no_sub_units(self) -> None:
        assert pack.info().covers_sub_units == frozenset()


class TestEverythingIsUnsourced:
    def test_every_obligation_carries_a_fact_needed_marker(self) -> None:
        findings = pack.evaluate(decl("GB"), AS_AT, None)
        assert findings
        for f in findings:
            assert f.obligation.has_unsourced_constant(), f.obligation.obligation_id

    def test_every_finding_is_contested(self) -> None:
        """An unsourced constant can never support a gap or a pass."""
        for f in pack.evaluate(decl("GB"), AS_AT, None):
            assert f.result is ObligationResult.CONTESTED

    def test_no_age_appears_anywhere_in_the_pack_source(self) -> None:
        """A delegate reported '13' for DPA 2018 s.9. It must not be in the code."""
        import inspect
        import re

        source = inspect.getsource(pack)
        body = "\n".join(
            line for line in source.splitlines() if FACT_NEEDED_PREFIX not in line
        )
        assert not re.search(r"\b(?:13|16|18)\s*(?:years|$)", body)

    def test_the_module_records_why_the_values_are_absent(self) -> None:
        import inspect

        doc = (inspect.getdoc(pack) or "").lower()
        assert "202" in doc or "legislation.gov.uk" in doc
