# Parked packs — not built, not loaded, not shipped

These two regime packs are **parked, not deleted**. Nothing here is imported by the tool:
this directory sits outside `src/`, so it is neither packaged nor importable, and neither
pack appears in `samanvaya.registry.PACKS`.

## Why they were parked, on 2026-08-20

Both were scaffolding. Every obligation in each carried a `[FACT NEEDED: ...]` marker,
because the statutory text was never read on a primary source:

| Pack | Obligations | Sourced | Why not |
|---|---|---|---|
| `uk_gdpr` | 4 | **0** | `legislation.gov.uk` returned HTTP 202 with an empty body on every request on 2026-08-19 — HTML, XML and plain text alike |
| `singapore_pdpa` | 4 | **0** | `sso.agc.gov.sg` returned only its site shell, not the text of the Act |

An unsourced obligation is not a small defect in this tool. It makes
`Obligation.has_unsourced_constant()` true, which forces the finding to `contested` — and
a `contested` row renders in a client-facing PDF as a line reading, in full,
`[FACT NEEDED: which section imposes the data breach notification obligation?]`.

That is a document, on an advocate's letterhead, advertising that the work was not done.
Shipping it into the United Kingdom and Singapore — two of the practice's live
correspondent markets — was the specific outcome not worth a larger regime count on the
README.

## What happens now when someone declares GB or SG

They are no longer mapped to a regime, so they fall through to
`JurisdictionResolution.unknown_countries` and produce a visible incompleteness notice
saying the jurisdiction was **not assessed**. That is deliberate: silence about a declared
jurisdiction reads as a clean bill, and this tool never lets an absence pass for a finding.

## Un-parking them

1. Read the statute on a primary source and replace every `fact_needed(...)` with the real
   constant, recording where it was read and on what date, as the India pack does.
2. Move the package back under `src/samanvaya/packs/`.
3. Restore the entry in `registry.PACKS` and the country tokens in `jurisdiction.py`.
4. Move the test module back to `tests/packs/`.
5. Confirm the pack reports `draft=False` and that
   `tests/test_falsifiers.py::test_the_india_rules_constants_are_all_sourced`'s sibling
   check for that regime passes with an empty offender set.
