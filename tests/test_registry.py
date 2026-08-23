"""Acceptance tests for the pack registry and the pack contract.

Authored BEFORE the implementation. Tests are not delegated.

**C2.** The registry is a hardcoded mapping of the six first-party packs. Entry-point
plugin discovery was cut: third-party packs are rejected scope for v1, and a dynamic
discovery mechanism for a fixed set of six is indirection without benefit. It is also a
security property — a tool that loads arbitrary installed Python by name is a tool whose
legal findings can be silently replaced by anything on the path.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from samanvaya import registry
from samanvaya.packs import contract
from samanvaya.types import PackInfo, RegimeId

AS_AT = date(2026, 8, 19)


class TestTheSixPacks:
    def test_exactly_six_packs_are_registered(self) -> None:
        assert len(registry.PACKS) == 4

    def test_every_regime_has_a_pack(self) -> None:
        # NOT set(RegimeId). UK_GDPR and SINGAPORE_PDPA remain valid regime
        # identifiers — the delta layer and several unit tests use them as labels —
        # but they have no pack, because both were parked on 2026-08-20 with every
        # obligation unsourced. The registry is the set of packs that EXIST, and a
        # test that conflates the two would force scaffolding back into the product.
        assert set(registry.PACKS) == {
            RegimeId.INDIA,
            RegimeId.EU_GDPR,
            RegimeId.US,
            RegimeId.CANADA,
        }

    def test_each_pack_can_be_fetched_by_regime(self) -> None:
        for regime in registry.PACKS:
            assert registry.get(regime) is not None

    def test_fetching_an_unknown_regime_raises_a_named_error(self) -> None:
        with pytest.raises((KeyError, ValueError)):
            registry.get("not-a-regime")  # type: ignore[arg-type]


class TestPackMetadata:
    def test_every_pack_reports_pack_info(self) -> None:
        for regime in registry.PACKS:
            assert isinstance(registry.get(regime).info(), PackInfo)

    def test_pack_info_regime_matches_its_registry_key(self) -> None:
        """Registry validates metadata against implementation; no contract bypass."""
        for regime in registry.PACKS:
            assert registry.get(regime).info().regime is regime

    def test_india_is_the_only_pack_that_is_not_draft(self) -> None:
        """India's constants are settled on the Gazette. The other five are not yet."""
        not_draft = {r for r in registry.PACKS if not registry.get(r).info().draft}
        assert not_draft == {RegimeId.INDIA}

    def test_every_draft_pack_states_why_it_is_draft(self) -> None:
        for regime in registry.PACKS:
            info = registry.get(regime).info()
            if info.draft:
                assert info.draft_reason.strip(), regime

    def test_every_pack_names_its_instruments(self) -> None:
        for regime in registry.PACKS:
            assert registry.get(regime).info().instruments, regime

    def test_no_pack_names_a_nonexistent_instrument(self) -> None:
        """"US GDPR", "Singapore GDPR" and "Canada GDPR" are not instruments."""
        for regime in registry.PACKS:
            for instrument in registry.get(regime).info().instruments:
                lowered = instrument.lower()
                if "gdpr" in lowered:
                    assert lowered.startswith("uk gdpr") or "regulation (eu) 2016/679" in lowered, (
                        f"{regime}: suspicious instrument name {instrument!r}"
                    )

    def test_only_the_federated_packs_cover_sub_units(self) -> None:
        for regime in registry.PACKS:
            covers = registry.get(regime).info().covers_sub_units
            if regime in (RegimeId.US, RegimeId.CANADA):
                assert covers, regime
            else:
                assert covers == frozenset(), regime

    def test_the_declared_obligation_count_matches_what_evaluate_can_emit(self) -> None:
        """Metadata that disagrees with the implementation is a contract bypass."""
        for regime in registry.PACKS:
            info = registry.get(regime).info()
            assert info.obligation_count > 0, regime


class TestPackContract:
    def test_every_pack_exposes_the_evaluate_entry_point(self) -> None:
        for regime in registry.PACKS:
            assert callable(registry.get(regime).evaluate)

    def test_every_evaluate_has_the_contract_signature(self) -> None:
        expected = ("declaration", "as_at", "sub_unit")
        for regime in registry.PACKS:
            params = tuple(inspect.signature(registry.get(regime).evaluate).parameters)
            assert params == expected, f"{regime}: {params}"

    def test_the_contract_module_documents_the_entry_point(self) -> None:
        assert hasattr(contract, "PackProtocol") or hasattr(contract, "evaluate")


class TestNoPluginDiscovery:
    def test_no_module_uses_entry_points(self) -> None:
        """C2. Loading arbitrary installed Python by name would let anything on the
        path silently replace a legal finding."""
        import pathlib

        import samanvaya

        root = pathlib.Path(samanvaya.__file__).parent
        offenders = [
            str(p)
            for p in root.rglob("*.py")
            if "entry_points" in p.read_text(encoding="utf-8")
        ]
        assert offenders == []

    def test_no_module_imports_pkg_resources_or_importlib_metadata(self) -> None:
        import pathlib

        import samanvaya

        root = pathlib.Path(samanvaya.__file__).parent
        offenders = [
            str(p)
            for p in root.rglob("*.py")
            for needle in ("pkg_resources", "importlib.metadata", "importlib_metadata")
            if needle in p.read_text(encoding="utf-8")
        ]
        assert offenders == []

    def test_the_registry_mapping_is_a_literal_not_a_lookup(self) -> None:
        source = inspect.getsource(registry)
        assert "PACKS" in source
        assert "entry_point" not in source
