# 05 — SCAFFOLD  ·  Samanvaya Privacy Conformance Tool

**Date:** 2026-08-19

The tree is created BEFORE any feature is written — empty folders and barely-drafted files
included. The point is to hand the agent a bounded scope before it is asked to fill anything
in.

## Tree

```
samanvaya/
├── BMAD/
│   ├── 01-PROBLEM.md
│   ├── 02-ARCHITECTURE.md
│   ├── 03-ARCHITECTURE-ESSENTIALS.md
│   ├── 04-BMAD-SPEC.md
│   └── 05-SCAFFOLD.md
├── LICENSE
├── NOTICE
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── src/
│   └── samanvaya/
│       ├── __init__.py
│       ├── cli.py
│       ├── declaration.py
│       ├── jurisdiction.py
│       ├── schema.py
│       ├── engine.py
│       ├── delta.py
│       ├── report.py
│       ├── offline_check.py
│       ├── registry.py
│       ├── types.py
│       └── packs/
│           ├── __init__.py
│           ├── contract.py
│           ├── india/
│           │   ├── __init__.py
│           │   ├── adapter.py
│           │   └── pack.py
│           ├── eu_gdpr/
│           │   ├── __init__.py
│           │   └── pack.py
│           ├── uk_gdpr/
│           │   ├── __init__.py
│           │   └── pack.py
│           ├── singapore_pdpa/
│           │   ├── __init__.py
│           │   └── pack.py
│           ├── us/
│           │   ├── __init__.py
│           │   ├── pack.py
│           │   ├── federal.py
│           │   └── states.py
│           └── canada/
│               ├── __init__.py
│               ├── pack.py
│               └── federal_quebec.py
├── tests/
│   ├── __init__.py
│   ├── test_schema.py
│   ├── test_jurisdiction.py
│   ├── test_pack_contract.py
│   ├── test_applies_if.py
│   ├── test_depends_on.py
│   ├── test_delta.py
│   ├── test_offline.py
│   ├── test_report.py
│   ├── test_registry.py
│   ├── test_cli.py
│   ├── packs/
│   │   ├── __init__.py
│   │   ├── test_india_adapter.py
│   │   ├── test_eu_gdpr.py
│   │   ├── test_uk_gdpr.py
│   │   ├── test_singapore_pdpa.py
│   │   ├── test_us.py
│   │   └── test_canada.py
│   └── fixtures/
│       ├── canonical_declaration.json
│       ├── canonical_declaration.yaml
│       ├── us_hospital.json
│       ├── canada_with_quebec.json
│       ├── canada_without_quebec.json
│       └── us_no_states_incomplete.json
└── docs/
    └── verified_facts_brief.md
```

## File-by-file intent

| path | holds | created empty? |
|---|---|---|
| BMAD/01-PROBLEM.md | problem statement from PRD | no |
| BMAD/02-ARCHITECTURE.md | architecture record (superseded on A1–A7, C1–C3 by 03) | no |
| BMAD/03-ARCHITECTURE-ESSENTIALS.md | binding architecture essentials + hard-question pass | no |
| BMAD/04-BMAD-SPEC.md | binding spec with build order | no |
| BMAD/05-SCAFFOLD.md | this file | no |
| LICENSE | pristine MIT, no appended text | no |
| NOTICE | not-legal-advice disclaimer | no |
| README.md | project stub | no |
| pyproject.toml | metadata, deps, entry point | no |
| requirements.txt | minimal pinned deps; no network library | no |
| .gitignore | python/build artefacts | no |
| src/samanvaya/__init__.py | package marker | yes |
| src/samanvaya/cli.py | argparse dispatch: check, init, validate, version, cite | no (stubs) |
| src/samanvaya/declaration.py | load + parse declaration (stdlib json/yaml; C3) | no (stubs) |
| src/samanvaya/jurisdiction.py | country → sub-national tree expansion; honours `sub_units_complete` (A3) | no (stubs) |
| src/samanvaya/schema.py | validate structure, reject unknown keys | no (stubs) |
| src/samanvaya/engine.py | dispatch packs, apply `as_at`, topological eval (A6), `applies_if` (A4), rollups | no (stubs) |
| src/samanvaya/delta.py | divergence report; grouping key `(regime, sub_unit, instrument, topic, dimension)` (A2); groups on `dimension` (A1); NO ranking (C1) | no (stubs) |
| src/samanvaya/report.py | Markdown + JSON-lines from one `EngineResult` | no (stubs) |
| src/samanvaya/offline_check.py | install-time audit assertion + runtime `socket` tripwire (P1) | no (stubs) |
| src/samanvaya/registry.py | hardcoded mapping of the six packs (C2; no entry-point discovery) | no (stubs) |
| src/samanvaya/types.py | frozen dataclasses for Declaration, Obligation, Finding, EngineResult; structured sub_topic (A1); applies_if (A4); required_value (A5); depends_on (A6) | no (stubs) |
| src/samanvaya/packs/__init__.py | package marker | yes |
| src/samanvaya/packs/contract.py | `evaluate(declaration, as_at, sub_unit)` signature; pack validation | no (stubs) |
| src/samanvaya/packs/india/__init__.py | package marker | yes |
| src/samanvaya/packs/india/adapter.py | contract check on load (A7); maps `ComplianceResult` → shared enum; deterministic `as_at` boundary | no (stubs) |
| src/samanvaya/packs/india/pack.py | India pack: calls adapter | no (stubs) |
| src/samanvaya/packs/eu_gdpr/__init__.py | package marker | yes |
| src/samanvaya/packs/eu_gdpr/pack.py | Regulation (EU) 2016/679 pack | no (stubs) |
| src/samanvaya/packs/uk_gdpr/__init__.py | package marker | yes |
| src/samanvaya/packs/uk_gdpr/pack.py | UK GDPR + Data (Use and Access) Act 2025 amendments | no (stubs) |
| src/samanvaya/packs/singapore_pdpa/__init__.py | package marker | yes |
| src/samanvaya/packs/singapore_pdpa/pack.py | Singapore PDPA 2012 as amended 2020 | no (stubs) |
| src/samanvaya/packs/us/__init__.py | package marker | yes |
| src/samanvaya/packs/us/pack.py | US state + federal sectoral pack; tree semantics | no (stubs) |
| src/samanvaya/packs/us/federal.py | HIPAA / GLBA / COPPA / FERPA stub | no (stubs) |
| src/samanvaya/packs/us/states.py | ~20 state statutes stub | no (stubs) |
| src/samanvaya/packs/canada/__init__.py | package marker | yes |
| src/samanvaya/packs/canada/pack.py | Canada pack; PIPEDA + Quebec Law 25 | no (stubs) |
| src/samanvaya/packs/canada/federal_quebec.py | PIPEDA + Quebec Law 25 split | no (stubs) |
| tests/__init__.py | package marker | yes |
| tests/test_schema.py | reject unknown keys; malformed inputs; round-trip | no (stubs) |
| tests/test_jurisdiction.py | US/CA tree expansion; `sub_units_complete` true/false | no (stubs) |
| tests/test_pack_contract.py | citation, draft pack, in_force_until, required_value | no (stubs) |
| tests/test_applies_if.py | threshold obligations; missing input → contested (A4) | no (stubs) |
| tests/test_depends_on.py | topological order; cycle as load error (A6) | no (stubs) |
| tests/test_delta.py | one row per `dimension`; CCPA+HIPPA distinct; no strongest (A1, A2, C1) | no (stubs) |
| tests/test_offline.py | tripwire raise; audit failure (P1) | no (stubs) |
| tests/test_report.py | single `EngineResult` source; disclaimer present | no (stubs) |
| tests/test_registry.py | hardcoded six-pack mapping; no `entry_points` (C2) | no (stubs) |
| tests/test_cli.py | subcommands dispatch | no (stubs) |
| tests/packs/__init__.py | package marker | yes |
| tests/packs/test_india_adapter.py | contract check on load (A7); bit-identical upstream | no (stubs) |
| tests/packs/test_eu_gdpr.py | EU GDPR pack | no (stubs) |
| tests/packs/test_uk_gdpr.py | UK GDPR pack | no (stubs) |
| tests/packs/test_singapore_pdpa.py | Singapore PDPA pack | no (stubs) |
| tests/packs/test_us.py | US pack tree + federal sectoral | no (stubs) |
| tests/packs/test_canada.py | Canada PIPEDA + Quebec Law 25 | no (stubs) |
| tests/fixtures/canonical_declaration.json | minimal valid declaration | no |
| tests/fixtures/canonical_declaration.yaml | YAML mirror | no |
| tests/fixtures/us_hospital.json | California hospital under CCPA + HIPAA | no |
| tests/fixtures/canada_with_quebec.json | triggers Law 25 | no |
| tests/fixtures/canada_without_quebec.json | PIPEDA only | no |
| tests/fixtures/us_no_states_incomplete.json | `sub_units_complete: false` | no |
| docs/verified_facts_brief.md | sourced statutory references only | no |

## Build order

1. Scaffold (this file) — no logic.
2. `types.py` + `schema.py` — frozen dataclasses for `Declaration`, `Obligation`, `Finding`, `EngineResult` (carries A1, A2, A4, A5, A6 fields).
3. `declaration.py` — stdlib json/yaml loader; rejects unknown keys via `schema.py`.
4. `jurisdiction.py` — US + Canada trees; honours `sub_units_complete` (A3).
5. `packs/contract.py` + `packs/india/` — contract check on load (A7); India as correctness anchor.
6. `packs/eu_gdpr/`, `packs/uk_gdpr/`, `packs/singapore_pdpa/` — established pack pattern.
7. `packs/us/`, `packs/canada/` — tree-semantics packs; largest scope; built last among packs.
8. `engine.py` — applies `as_at`; evaluates `applies_if` (A4); topological eval (A6); rollups.
9. `delta.py` — divergence on `(regime, sub_unit, instrument, topic, dimension)` (A2); grouped on `dimension` (A1); NO ranking (C1).
10. `report.py` — Markdown + JSON-lines from one `EngineResult`; fixed disclaimer.
11. `offline_check.py` — install-time audit + runtime tripwire (P1).
12. `registry.py` — hardcoded six-pack mapping (C2).
13. `cli.py` — argparse dispatch: `check`, `init`, `validate`, `version`, `cite`.
14. Ship-gate sweep (06-FILTER).

## Verify the scaffold

```bash
python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('src').rglob('*.py')]; print('scaffold parses')"
python -m compileall -q src tests && echo "scaffold compiles"
```

