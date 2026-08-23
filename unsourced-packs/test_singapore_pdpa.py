"""Acceptance tests for the Singapore pack. Tests are not delegated.

sso.agc.gov.sg returned only its site shell on 2026-08-19, so no PDPA provision could be
read. The pack is honestly empty, and these tests keep it that way.

The PDPA 2012 is not a GDPR and must never be described as one.
"""

from __future__ import annotations

from datetime import date

from samanvaya.packs.singapore_pdpa import pack
from samanvaya.types import ObligationResult, RegimeId

from ._helpers import decl

AS_AT = date(2026, 8, 19)


class TestMetadata:
    def test_the_regime_is_singapore(self) -> None:
        assert pack.info().regime is RegimeId.SINGAPORE_PDPA

    def test_the_instrument_is_the_pdpa_not_a_gdpr(self) -> None:
        assert pack.info().instruments == ("Personal Data Protection Act 2012",)

    def test_the_pack_never_calls_it_a_gdpr(self) -> None:
        """The banned thing is the CONSTRUCTION "Singapore GDPR", not the word.

        Saying "the PDPA is not a GDPR" is exactly the clarification the PRD wants, so a
        blanket ban on the substring would punish the correct sentence.
        """
        import inspect
        import re

        source = inspect.getsource(pack).lower()
        for banned in ("singapore gdpr", "sg gdpr", "singapore's gdpr"):
            assert banned not in source, banned
        # Nor may it describe the PDPA as being one.
        assert not re.search(r"pdpa[^.]{0,40}\bis a gdpr", source)

    def test_it_is_draft_and_says_why(self) -> None:
        assert pack.info().draft is True
        assert pack.info().draft_reason.strip()


class TestEverythingIsUnsourced:
    def test_every_obligation_carries_a_fact_needed_marker(self) -> None:
        findings = pack.evaluate(decl("SG"), AS_AT, None)
        assert findings
        for f in findings:
            assert f.obligation.has_unsourced_constant(), f.obligation.obligation_id

    def test_every_finding_is_contested(self) -> None:
        for f in pack.evaluate(decl("SG"), AS_AT, None):
            assert f.result is ObligationResult.CONTESTED

    def test_no_section_26d_or_penalty_figure_leaked_into_the_code(self) -> None:
        """A delegate reported s.26D and an SGD 1 million ceiling. Neither is sourced."""
        import inspect

        source = inspect.getsource(pack)
        assert "26D" not in source
        assert "1 million" not in source and "1,000,000" not in source
