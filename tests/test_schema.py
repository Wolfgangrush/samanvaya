"""Acceptance tests for the declaration loader and schema validator.

Authored BEFORE the implementation. Tests are not delegated.

Two things are load-bearing here.

**Unknown keys are refused, never ignored.** A declaration is a legal instrument in
miniature: if the adviser writes ``sub_national_unit`` where the schema says
``sub_units``, silently dropping it produces a report that omits a whole federation
and reads as a clean bill of health. Refusing is the only safe behaviour.

**A declaration carrying a credential is refused.** The PRD's first banned item is
connections and credentials, because possession of a client's credentials would make
the author a Data Fiduciary or Processor in his own right, with his own breach duty.
The tool must refuse to hold one even by accident.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samanvaya.declaration import canonical_hash, load, load_text
from samanvaya.schema import validate
from samanvaya.types import DeclarationError, RegimeId

FIXTURES = Path(__file__).parent / "fixtures"


def _canonical() -> dict:
    return json.loads((FIXTURES / "canonical_declaration.json").read_text())


class TestLoading:
    def test_loads_the_canonical_json_declaration(self) -> None:
        decl = load(FIXTURES / "canonical_declaration.json")
        assert decl.organisation.legal_name == "Example Analytics Private Limited"

    def test_loads_the_canonical_yaml_declaration(self) -> None:
        decl = load(FIXTURES / "canonical_declaration.yaml")
        assert decl.organisation.legal_name == "Example Analytics Private Limited"

    def test_json_and_yaml_of_the_same_content_produce_equal_declarations(self) -> None:
        assert load(FIXTURES / "canonical_declaration.json") == load(
            FIXTURES / "canonical_declaration.yaml"
        )

    def test_json_and_yaml_of_the_same_content_hash_identically(self) -> None:
        """The hash must describe the content, not the file's whitespace."""
        a = canonical_hash(load(FIXTURES / "canonical_declaration.json"))
        b = canonical_hash(load(FIXTURES / "canonical_declaration.yaml"))
        assert a == b

    def test_the_hash_is_a_sha256_hex_digest(self) -> None:
        h = canonical_hash(load(FIXTURES / "canonical_declaration.json"))
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)

    def test_changing_one_declared_value_changes_the_hash(self) -> None:
        base = _canonical()
        before = canonical_hash(validate(base))
        base["organisation"]["employee_count"] = 41
        assert canonical_hash(validate(base)) != before

    def test_a_missing_file_raises_a_named_error(self) -> None:
        with pytest.raises((DeclarationError, FileNotFoundError)):
            load(FIXTURES / "does_not_exist.json")

    def test_an_unrecognised_extension_is_refused(self, tmp_path: Path) -> None:
        p = tmp_path / "decl.txt"
        p.write_text("{}")
        with pytest.raises(DeclarationError):
            load(p)


class TestMalformedInput:
    def test_malformed_json_raises_declaration_error(self) -> None:
        with pytest.raises(DeclarationError):
            load_text("{ not json", "json")

    def test_malformed_yaml_raises_declaration_error(self) -> None:
        with pytest.raises(DeclarationError):
            load_text("a: [1, 2\nb: }", "yaml")

    def test_json_nan_is_refused(self) -> None:
        """NaN is not standard JSON and must not enter a legal report."""
        with pytest.raises(DeclarationError):
            load_text('{"schema_version": NaN}', "json")

    def test_yaml_duplicate_keys_are_refused(self) -> None:
        """A duplicate key means the adviser wrote two answers; pick neither."""
        text = (
            "schema_version: '1.0'\n"
            "declaration_author: a\n"
            "organisation: {legal_name: X}\n"
            "jurisdictions: []\n"
            "purposes: [one]\n"
            "purposes: [two]\n"
        )
        with pytest.raises(DeclarationError):
            load_text(text, "yaml")

    def test_a_yaml_document_that_is_not_a_mapping_is_refused(self) -> None:
        with pytest.raises(DeclarationError):
            load_text("- just\n- a\n- list\n", "yaml")

    def test_yaml_python_object_tags_are_refused(self) -> None:
        """safe_load only. An arbitrary tag must never construct an object."""
        with pytest.raises(DeclarationError):
            load_text("!!python/object/apply:os.system ['echo hi']\n", "yaml")


class TestUnknownKeys:
    def test_an_unknown_top_level_key_is_refused(self) -> None:
        with pytest.raises(DeclarationError):
            load(FIXTURES / "declaration_unknown_key.json")

    def test_the_error_names_the_offending_key(self) -> None:
        with pytest.raises(DeclarationError) as exc:
            load(FIXTURES / "declaration_unknown_key.json")
        assert "sub_national_units" in str(exc.value)

    def test_an_unknown_nested_key_is_refused(self) -> None:
        obj = _canonical()
        obj["organisation"]["headcount"] = 5
        with pytest.raises(DeclarationError) as exc:
            validate(obj)
        assert "headcount" in str(exc.value)

    def test_an_unknown_key_inside_a_list_item_is_refused(self) -> None:
        obj = _canonical()
        obj["security_safeguards"].append({"control": "x", "value": "y", "strength": "high"})
        with pytest.raises(DeclarationError) as exc:
            validate(obj)
        assert "strength" in str(exc.value)


class TestRequiredFields:
    def test_a_missing_schema_version_is_refused(self) -> None:
        obj = _canonical()
        del obj["schema_version"]
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_a_missing_declaration_author_is_refused(self) -> None:
        """Someone must own the assertions. An unattributed declaration is refused."""
        obj = _canonical()
        del obj["declaration_author"]
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_a_missing_organisation_is_refused(self) -> None:
        obj = _canonical()
        del obj["organisation"]
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_an_organisation_without_a_legal_name_is_refused(self) -> None:
        obj = _canonical()
        obj["organisation"] = {}
        with pytest.raises(DeclarationError):
            validate(obj)


class TestTypeChecking:
    def test_a_string_where_an_integer_is_expected_is_refused(self) -> None:
        obj = _canonical()
        obj["organisation"]["employee_count"] = "forty"
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_a_boolean_where_an_integer_is_expected_is_refused(self) -> None:
        """In Python True == 1. In a legal declaration it does not."""
        obj = _canonical()
        obj["organisation"]["employee_count"] = True
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_an_integer_where_a_string_is_expected_is_refused(self) -> None:
        obj = _canonical()
        obj["declaration_author"] = 42
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_a_scalar_where_a_list_is_expected_is_refused(self) -> None:
        obj = _canonical()
        obj["purposes"] = "service delivery"
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_lists_become_tuples_so_the_declaration_stays_frozen(self) -> None:
        decl = validate(_canonical())
        assert isinstance(decl.purposes, tuple)
        assert isinstance(decl.jurisdictions, tuple)
        assert isinstance(decl.security_safeguards, tuple)

    def test_an_explicit_null_optional_is_accepted_as_not_declared(self) -> None:
        obj = _canonical()
        obj["organisation"]["employee_count"] = None
        assert validate(obj).organisation.employee_count is None

    def test_a_declaration_date_parses_to_a_date(self) -> None:
        from datetime import date

        assert validate(_canonical()).declaration_date == date(2026, 8, 19)

    def test_a_malformed_declaration_date_is_refused(self) -> None:
        obj = _canonical()
        obj["declaration_date"] = "19-08-2026"
        with pytest.raises(DeclarationError):
            validate(obj)


class TestCredentialRefusal:
    def test_a_connection_string_in_the_declaration_is_refused(self) -> None:
        """PRD banned scope item 1. The tool must not hold a client credential."""
        with pytest.raises(DeclarationError):
            load(FIXTURES / "declaration_with_credential.json")

    def test_the_error_says_it_looks_like_a_credential(self) -> None:
        with pytest.raises(DeclarationError) as exc:
            load(FIXTURES / "declaration_with_credential.json")
        assert "credential" in str(exc.value).lower()

    def test_the_error_does_not_echo_the_secret_back(self) -> None:
        """Refusing must not copy the secret into a traceback or a log."""
        with pytest.raises(DeclarationError) as exc:
            load(FIXTURES / "declaration_with_credential.json")
        assert "hunter2" not in str(exc.value)

    @pytest.mark.parametrize(
        "value",
        [
            "postgresql://u:p@host:5432/db",
            "mysql://root:toor@10.0.0.1/app",
            "mongodb+srv://admin:pw@cluster.mongodb.net",
            "AKIAIOSFODNN7EXAMPLE",
            "-----BEGIN RSA PRIVATE KEY-----",
            "aws_secret_access_key=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY",
        ],
    )
    def test_common_credential_shapes_are_refused(self, value: str) -> None:
        obj = _canonical()
        obj["recipients"] = [value]
        with pytest.raises(DeclarationError):
            validate(obj)

    def test_ordinary_prose_is_not_mistaken_for_a_credential(self) -> None:
        obj = _canonical()
        obj["recipients"] = [
            "Cloud hosting provider (contract dated 1 April 2026)",
            "Payment processor: settlement only, no card data retained",
        ]
        assert validate(obj) is not None


class TestNoRuamel:
    def test_ruamel_is_not_imported_anywhere(self) -> None:
        """C3. Round-trip fidelity exists to preserve comments on write-back, and
        the tool is banned from writing back. A heavy dependency for a forbidden
        capability."""
        import pathlib

        import samanvaya

        root = pathlib.Path(samanvaya.__file__).parent
        offenders = [
            str(p) for p in root.rglob("*.py") if "ruamel" in p.read_text(encoding="utf-8")
        ]
        assert offenders == []

    def test_ruamel_is_not_a_declared_dependency(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for name in ("requirements.txt", "pyproject.toml"):
            text = (root / name).read_text(encoding="utf-8")
            assert "ruamel" not in text


class TestScenarioFixtures:
    def test_the_california_hospital_fixture_loads(self) -> None:
        decl = load(FIXTURES / "us_hospital.json")
        assert decl.organisation.is_healthcare_provider is True
        assert decl.jurisdictions[0].sub_units == ("US-CA",)

    def test_the_incomplete_us_fixture_declares_no_states(self) -> None:
        decl = load(FIXTURES / "us_no_states_incomplete.json")
        assert decl.jurisdictions[0].sub_units == ()
        assert decl.jurisdictions[0].sub_units_complete is False

    def test_the_quebec_fixture_names_quebec(self) -> None:
        decl = load(FIXTURES / "canada_with_quebec.json")
        assert "CA-QC" in decl.jurisdictions[0].sub_units

    def test_the_ontario_fixture_does_not_name_quebec(self) -> None:
        decl = load(FIXTURES / "canada_without_quebec.json")
        assert "CA-QC" not in decl.jurisdictions[0].sub_units

    def test_the_multi_regime_fixture_spans_the_covered_regimes(self) -> None:
        """India and the EU resolve; GB and SG are declared but no longer covered.

        The fixture still names four countries on purpose. Two of them — GB and SG — were
        parked on 2026-08-20 with every obligation unsourced, so they now resolve to
        nothing and must surface as `unknown_countries`. Keeping them in the fixture means
        the mixed case (some covered, some not) is exercised by the suite rather than
        assumed.
        """
        from samanvaya.jurisdiction import resolve

        decl = load(FIXTURES / "multi_regime.json")
        resolution = resolve(decl)
        assert resolution.regimes == frozenset({RegimeId.INDIA, RegimeId.EU_GDPR})
        assert set(resolution.unknown_countries) == {"GB", "SG"}
