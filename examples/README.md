# Example declarations

A **declaration** is a JSON file stating what is currently known about an organisation's
personal-data practices: who it is, where it operates, what it collects and why, what it tells
people, and how it handles breaches, access requests, and transfers. It is written by an
adviser — typically by hand, from a discovery interview with the organisation — and then fed to
the tool, which reports conformance across six privacy regimes. A declaration is not the output
of a scan or a connector: it is a human account of facts as understood on a given day, which is
why it carries a `declaration_author` and, optionally, a `declaration_date`.

Only the keys defined by schema version 1.0 are accepted; anything else is refused. No secrets
belong in a declaration — no keys, tokens, passwords, or connection strings. A declaration that
contains credential-shaped material is rejected before it is ever checked.

## The five examples

### `01-india-saas-startup.json`
A 40-person Indian B2B SaaS company operating only in India, with one cloud region abroad
carrying its customer data. Notice, consent, breach, and retention facts are well described —
including the 72-hour regulator deadline — while a few governance facts are deliberately left
unstated. It shows a small but reasonably well-run data fiduciary, and exercises the tool's
treatment of partial governance information.

### `02-eu-uk-ecommerce.json`
A 900-person retailer trading in Germany and the United Kingdom, large enough that the
records-of-processing duty plainly bites. Special-category data: no. It has a privacy officer,
maintains processing records, and makes transfers outside the jurisdiction under a stated
mechanism. This is the multi-jurisdiction GDPR/UK-GDPR shape, and it exercises the tool's
handling of overlapping European regimes.

### `03-us-california-hospital.json`
A Californian hospital with 250,000 consumers and $60m revenue — a healthcare provider sitting
under a state consumer-privacy statute and a federal sectoral health-privacy law at once. That
overlap is the case the tool exists to handle. Breach notification, special-category data, and
children's records are all described.

### `04-canada-quebec-fintech.json`
A financial institution operating federally in Canada and in Quebec, with 4,000 consumers. It
exercises the tool's handling of the federal/Quebec provincial overlap for a regulated sector,
including a maintained breach register with a stated five-year retention period.

### `05-minimal-unknowns.json`
The honest opposite: an organisation at the *start* of a discovery interview, where only the
schema version, the author, one jurisdiction, and the legal name are known. Everything else is
omitted. It exists to show that an unfinished declaration is a legitimate starting point, and it
exercises the tool's default behaviour on almost entirely unstated facts.

## Unknowns are safe

Every fact in a declaration is either stated or not stated. An omitted (or `null`) fact is
reported as `contested` — the tool's way of saying "this is not yet known" — and never as a gap
or a failure. A `false` means the client said no; an omission means the client did not say, and
those are different findings. Write down only what you actually learned in the interview, and
let the tool mark the rest as contested. A half-finished declaration is a safe, useful artifact.

## Running an example

    samanvaya check examples/01-india-saas-startup.json --as-at 2027-12-01 --out report
