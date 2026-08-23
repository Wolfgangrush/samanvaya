"""Samanvaya conformance engine — the pack registry.

A hardcoded mapping of the six first-party packs. Dynamic discovery was cut
deliberately (finding C2): third-party packs are out of scope for v1, and a
discovery mechanism for a fixed set of six is indirection without benefit.
It is also a security property — a tool that loads arbitrary installed Python
by name is a tool whose legal findings can be silently replaced by anything
on the path.

On import the registry VALIDATES each pack against the contract: its
``info().regime`` must equal its registry key, and it must expose a callable
``evaluate`` with exactly the parameters ``("declaration", "as_at",
"sub_unit")``. A mismatch raises PackLoadError naming the pack, so metadata
that disagrees with the implementation cannot bypass the contract.
"""

from __future__ import annotations

import inspect
from types import ModuleType
from typing import TYPE_CHECKING

from samanvaya.packs.canada import pack as canada_pack
from samanvaya.packs.eu_gdpr import pack as eu_gdpr_pack
from samanvaya.packs.india import pack as india_pack
from samanvaya.packs.us import pack as us_pack
from samanvaya.types import PackLoadError, RegimeId

if TYPE_CHECKING:
    from samanvaya.packs.contract import PackProtocol

__all__ = ["PACKS", "get"]

# The literal, first-party-only registry. No lookups, no discovery.
#
# UK_GDPR and SINGAPORE_PDPA are ABSENT deliberately, parked on 2026-08-20 in
# `unsourced-packs/` because every obligation in each was a `fact_needed` placeholder.
# A regime with no entry here is not mapped by `jurisdiction.py` either, so declaring
# GB or SG now yields a visible 'not assessed' notice rather than silence. See
# `unsourced-packs/README.md` for what un-parking them requires.
PACKS: dict[RegimeId, ModuleType] = {
    RegimeId.INDIA: india_pack,
    RegimeId.EU_GDPR: eu_gdpr_pack,
    RegimeId.US: us_pack,
    RegimeId.CANADA: canada_pack,
}

_EXPECTED_PARAMETERS: tuple[str, ...] = ("declaration", "as_at", "sub_unit")


def _validate(regime: RegimeId, pack: ModuleType) -> None:
    """Check a pack honours the contract before it can serve any findings."""
    try:
        info = pack.info()
    except Exception as exc:  # pragma: no cover - defensive
        raise PackLoadError(f"pack for {regime.value} has no usable info(): {exc}") from exc
    if info.regime is not regime:
        raise PackLoadError(
            f"pack for {regime.value} reports regime {info.regime.value!r}; "
            "registry metadata must match the pack key"
        )
    evaluate = getattr(pack, "evaluate", None)
    if not callable(evaluate):
        raise PackLoadError(f"pack for {regime.value} exposes no callable evaluate()")
    parameters = tuple(inspect.signature(evaluate).parameters)
    if parameters != _EXPECTED_PARAMETERS:
        raise PackLoadError(
            f"pack for {regime.value} evaluate() parameters {parameters} "
            f"do not match the contract {_EXPECTED_PARAMETERS}"
        )


for _regime, _pack in PACKS.items():
    _validate(_regime, _pack)


def get(regime: RegimeId) -> "PackProtocol":
    """Return the pack for a regime, raising KeyError for anything unknown.

    A non-RegimeId argument (including an unhashable one) is reported as
    KeyError with an actionable message rather than leaking a TypeError.
    """
    try:
        pack = PACKS.get(regime)
    except TypeError as exc:
        raise KeyError(
            f"no pack is registered for {regime!r}; "
            f"known regimes are {[r.value for r in RegimeId]}"
        ) from exc
    if pack is None:
        raise KeyError(
            f"no pack is registered for {regime!r}; "
            f"known regimes are {[r.value for r in RegimeId]}"
        )
    # The pack was validated against the contract at import time; the cast
    # here reflects that validation rather than trusting the module blindly.
    return pack
