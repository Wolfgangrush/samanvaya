"""Acceptance tests for the offline guarantee.

Authored BEFORE the implementation. Tests are not delegated.

**P1, honestly labelled.** The runtime `socket` guard is a **tripwire**, not a proof. A C
extension can open a socket without going through `socket.socket`, and pretending otherwise
would be worse than having no guard, because it would invite reliance. The real assurance is
the install-time dependency audit: the tool's declared dependencies are enumerated and any
that brings a network capability is refused. Belt and braces, each labelled as what it is.

This matters beyond hygiene. "Almost offline" is, operationally and legally, the same as
"online": the offline posture is what keeps the tool's author from becoming a conduit for
client personal data, and a single outbound call defeats it.
"""

from __future__ import annotations

import socket

import pytest

from samanvaya.offline_check import (
    ALLOWED_DEPENDENCIES,
    audit_dependencies,
    install_tripwire,
    remove_tripwire,
)


class TestDependencyAudit:
    def test_the_audit_passes_on_the_declared_dependency_set(self) -> None:
        audit_dependencies()

    def test_the_allowlist_is_explicit_not_inferred(self) -> None:
        """An allowlist computed from what happens to be installed proves nothing."""
        assert isinstance(ALLOWED_DEPENDENCIES, frozenset)
        assert ALLOWED_DEPENDENCIES

    def test_the_allowlist_is_exactly_the_declared_runtime_set(self) -> None:
        """PyYAML for the loader, dpdp-law-to-code for the India rail, fpdf2 and its
        transitive set for the client-facing PDF. Nothing else, and each one is listed
        with a reason in the module — an allowlist nobody justifies is a rubber stamp."""
        assert {d.lower().replace("_", "-") for d in ALLOWED_DEPENDENCIES} == {
            "pyyaml", "dpdp-law-to-code", "fpdf2", "defusedxml", "fonttools", "pillow",
        }

    def test_a_networking_dependency_is_refused_by_name(self) -> None:
        with pytest.raises(RuntimeError) as exc:
            audit_dependencies(declared=("PyYAML", "requests"))
        assert "requests" in str(exc.value)

    @pytest.mark.parametrize(
        "package", ["requests", "httpx", "urllib3", "aiohttp", "boto3", "websockets"]
    )
    def test_known_networking_packages_are_each_refused(self, package: str) -> None:
        with pytest.raises(RuntimeError):
            audit_dependencies(declared=("PyYAML", package))

    def test_an_unrecognised_dependency_is_refused_rather_than_assumed_safe(self) -> None:
        """Fail closed. An unknown package is not evidence of a harmless package."""
        with pytest.raises(RuntimeError):
            audit_dependencies(declared=("PyYAML", "some-package-nobody-vetted"))

    def test_the_error_says_what_to_do(self) -> None:
        with pytest.raises(RuntimeError) as exc:
            audit_dependencies(declared=("requests",))
        assert "offline" in str(exc.value).lower()


class TestRuntimeTripwire:
    def test_the_tripwire_blocks_socket_construction(self) -> None:
        install_tripwire()
        try:
            with pytest.raises(RuntimeError):
                socket.socket()
        finally:
            remove_tripwire()

    def test_the_tripwire_error_names_the_offline_guarantee(self) -> None:
        install_tripwire()
        try:
            with pytest.raises(RuntimeError) as exc:
                socket.socket()
            assert "offline" in str(exc.value).lower()
        finally:
            remove_tripwire()

    def test_removing_the_tripwire_restores_normal_behaviour(self) -> None:
        original = socket.socket
        install_tripwire()
        remove_tripwire()
        assert socket.socket is original

    def test_installing_twice_is_safe(self) -> None:
        original = socket.socket
        install_tripwire()
        install_tripwire()
        remove_tripwire()
        assert socket.socket is original

    def test_removing_without_installing_is_safe(self) -> None:
        remove_tripwire()
        remove_tripwire()

    def test_the_tripwire_also_blocks_create_connection(self) -> None:
        install_tripwire()
        try:
            with pytest.raises(RuntimeError):
                socket.create_connection(("example.invalid", 80), timeout=0.01)
        finally:
            remove_tripwire()


class TestHonestLabelling:
    def test_the_module_calls_the_socket_guard_a_tripwire_not_a_proof(self) -> None:
        import inspect

        from samanvaya import offline_check

        source = inspect.getsource(offline_check).lower()
        assert "tripwire" in source

    def test_the_module_documents_the_c_extension_limit(self) -> None:
        """The known limit must be written down, not discovered by a user."""
        import inspect

        from samanvaya import offline_check

        source = inspect.getsource(offline_check).lower()
        assert "c extension" in source or "c-extension" in source

    def test_the_module_does_not_claim_to_guarantee(self) -> None:
        import inspect

        from samanvaya import offline_check

        source = inspect.getsource(offline_check).lower()
        assert "guarantees that no network" not in source


class TestNoNetworkingImportsAnywhere:
    @pytest.mark.parametrize(
        "banned", ["requests", "httpx", "urllib.request", "urllib3", "aiohttp", "http.client"]
    )
    def test_no_source_module_imports_a_networking_library(self, banned: str) -> None:
        import pathlib

        import samanvaya

        root = pathlib.Path(samanvaya.__file__).parent
        offenders = []
        for path in root.rglob("*.py"):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")) and banned in stripped:
                    offenders.append(f"{path}: {stripped}")
        assert offenders == [], offenders

    def test_only_offline_check_imports_socket(self) -> None:
        """Anything else importing socket is a smell worth catching early."""
        import pathlib

        import samanvaya

        root = pathlib.Path(samanvaya.__file__).parent
        offenders = []
        for path in root.rglob("*.py"):
            if path.name == "offline_check.py":
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith(("import socket", "from socket")):
                    offenders.append(f"{path}: {stripped}")
        assert offenders == [], offenders
