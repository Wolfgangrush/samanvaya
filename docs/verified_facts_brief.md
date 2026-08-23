# Verified Facts Brief

Every statutory constant in this codebase must trace to an entry here, or be carried as
`[FACT NEEDED: ...]`. Nothing is admitted on a model's say-so — not this tool's, not a
delegate's. Each entry below was read on the primary text and quoted from it.

**Method.** The instrument was downloaded from the issuing authority's own site and the
provision extracted by string search, with no language model in the path between the
statute and this file. Where a source could not be reached, that is recorded as such and
the constant stays `[FACT NEEDED]`. A constant that cannot be sourced does not enter the
code.

**Verified by:** the maintainer, 2026-08-19, an automated build session.

---

## 1. India — VERIFIED (primary Gazette text)

Digital Personal Data Protection Act 2023 (22 of 2023) and Digital Personal Data
Protection Rules 2025, notified **G.S.R. 846(E)**, made **13 November 2025**, Gazette of
India Extraordinary, Part II Section 3(i).

Settled in full by Diego on the Gazette PDF itself. The ruling is the source of record:
`an internal notes reference`,
with the PDF and extracted text beside it.

| Constant | Provision | Value |
|---|---|---|
| Commencement — immediate | Rule 1(2) | Rules 1, 2 and 17 to 21, on the date of publication |
| Commencement — one year | Rule 1(3) | Rule 4 |
| Commencement — eighteen months | Rule 1(4) | Rules 3, 5 to 16, 22 and 23 |
| Security minima | Rule 6(1)(a)–(g) | seven limbs, closed list |
| Log and data retention | Rule 6(1)(e) | **one year**, unless another law requires otherwise |
| Processor contract clause | Rule 6(1)(f) | safeguards must be provided for *in the contract* |
| Breach — data principal | Rule 7(1) | **without delay**, concise, clear and plain |
| Breach — Board, first stage | Rule 7(2)(a) | **without delay** |
| Breach — Board, detailed report | Rule 7(2)(b) | **within seventy-two hours** of becoming aware |
| SDF assessments | Rule 13 | DPIA and audit **once every twelve months** |
| Grievance redressal period | Rule 14(3) | **not exceeding ninety days** |
| Consent Manager net worth | Rule 4 + First Schedule | **two crore rupees**, company incorporated in India |
| Child | DPDP Act 2023 | a person **under eighteen years** |

> **⚠️ Rule 14(3) is the only occurrence of "ninety" in the whole instrument, and it attaches
> to GRIEVANCE REDRESSAL alone.** It does not apply to access, correction, updating or
> erasure. The Rules prescribe **no** response period for those rights. PIB's own explainer
> misstates this; repeating PIB's sentence imports its error. A tool that imposes a
> ninety-day clock on ss.11–12 rights is inventing an obligation.

> **⚠️ OPEN — commencement anchor.** Rule 1 anchors commencement to the date of
> *publication*, and 13 vs 14 November 2025 is not yet settled against the e-Gazette
> record. Every derived commencement date therefore carries ±1 day and is
> `[FACT NEEDED: exact publication date of G.S.R. 846(E) on egazette.gov.in]`. The code
> must never compute one.

---

## 2. European Union — VERIFIED (EUR-Lex)

Regulation (EU) 2016/679. Source: EUR-Lex consolidated text, CELEX `02016R0679-20160504`,
downloaded and extracted 2026-08-19.

| Constant | Provision | Verified text |
|---|---|---|
| Child's consent age | Art 8(1) | "lawful where the child is at least **16 years old**… Member States may provide by law for a lower age… provided that such lower age is **not below 13 years**" |
| DSR response period | Art 12(3) | "without undue delay and in any event **within one month** of receipt… may be extended by **two further months** where necessary" |
| Processor contract | Art 28(3) | processing by a processor "governed by a contract or other legal act" |
| Records derogation | Art 30(5) | obligations "shall not apply to an enterprise or an organisation employing **fewer than 250 persons**", unless processing is likely to result in a risk, is not occasional, or includes Art 9(1) or Art 10 data |
| Security of processing | Art 32(1) | "appropriate technical and organisational measures to ensure a level of security appropriate to the risk", including "(a) the pseudonymisation and encryption of personal data" |
| Breach → supervisory authority | Art 33(1) | "without undue delay and, where feasible, **not later than 72 hours** after having become aware of it"; if later, reasons for the delay must accompany it |
| Breach → data subject | Art 34(1) | trigger is "likely to result in a **high risk** to the rights and freedoms of natural persons"; then "without undue delay" |
| DPIA | Art 35(1) | required where processing "is likely to result in a high risk", **prior to** the processing |
| DPO designation | Art 37(1) | (a) public authority or body; (b) core activities require regular and systematic monitoring of data subjects on a large scale; (c) core activities are large-scale processing of special categories |
| Principles | Art 5 | "Principles relating to processing of personal data" |
| Lawfulness | Art 6 | "Lawfulness of processing" |
| Notice | Art 13 | "Information to be provided where personal data are collected from the data subject" |
| Transfers | Art 44 | "General principle for transfers" |

> **OPEN.** Which Member States have exercised the Art 8(1) derogation, and to what age, is
> `[FACT NEEDED]` — it requires 27 national instruments. The EEA extension (Norway, Iceland,
> Liechtenstein) is deliberately **not assumed**; whether the tool should treat EEA states as
> GDPR regimes is `[FACT NEEDED]`.

---

## 3. Canada — VERIFIED (Justice Laws Canada)

Personal Information Protection and Electronic Documents Act, S.C. 2000, c. 5, and the
Breach of Security Safeguards Regulations, SOR/2018-64. Downloaded and extracted 2026-08-19.

| Constant | Provision | Verified text |
|---|---|---|
| Breach report to Commissioner | PIPEDA s.10.1(1) | required where it is reasonable to believe the breach "creates a **real risk of significant harm** to an individual" |
| Timing of that report | PIPEDA s.10.1(2) | "**as soon as feasible** after the organization determines that the breach has occurred" |
| Notification to individual | PIPEDA s.10.1(3) | same real-risk-of-significant-harm threshold |
| Breach records | PIPEDA s.10.3(1) | "keep and maintain a record of **every** breach of security safeguards" |
| Record retention | SOR/2018-64, s.6 | "**24 months** after the day on which the organization determines that the breach has occurred" |
| Fair information principles | PIPEDA Schedule 1 | **10 principles**, being the National Standard of Canada CAN/CSA-Q830-96; Principle 1 (Accountability) at clause 4.1 |

> **OPEN — Quebec.** `legisquebec.gouv.qc.ca` timed out repeatedly on 2026-08-19. Every
> Quebec Law 25 constant — the privacy impact assessment for communication outside Quebec,
> the age of parental consent, the penalty ceilings, the person in charge — is therefore
> `[FACT NEEDED]`. **The Canada pack stays `draft`.** Provincial statutes beyond Quebec are
> also `[FACT NEEDED]`.

---

## 4. United States — PARTIALLY VERIFIED (eCFR)

There is **no "US GDPR"** and no federal omnibus privacy statute. The US layer is federal
sectoral law plus roughly twenty comprehensive state statutes.

### Verified — federal sectoral

| Constant | Provision | Verified text |
|---|---|---|
| COPPA — child | 16 CFR 312.2 | "**Child** means an individual **under the age of 13**." |
| HIPAA — individual notice | 45 CFR 164.404(b) | "without unreasonable delay and in no case later than **60 calendar days** after discovery of a breach" |
| HIPAA — Secretary, 500+ | 45 CFR 164.408(b) | for breaches involving **500 or more** individuals, notify **contemporaneously** with the §164.404(a) notice |
| HIPAA — Secretary, under 500 | 45 CFR 164.408(c) | maintain a log and notify "**not later than 60 days after the end of each calendar year**" for breaches discovered in the preceding year |
| HIPAA — breach subpart applicability | 45 CFR 164.400 | breaches occurring on or after **23 September 2009** |
| HIPAA — Security Rule | 45 CFR 164.306 | "Security standards: General rules", Subpart C |
| GLBA Safeguards — partial exemption | 16 CFR 314.6 | §§314.4(b)(1), (d)(2), (h) and (i) "do not apply to financial institutions that maintain customer information concerning **fewer than five thousand consumers**" |

> **⚠️ Correction to a delegate's research.** A research delegate reported the HIPAA 500-or-more deadline as
> "60 calendar days". The rule says **contemporaneously** with the individual notice. The
> 60-day figure belongs to §164.404(b) and, separately, to the annual §164.408(c) filing.
> Recorded because it is precisely the class of error the verification step exists to catch.

> **⚠️ Note on §314.6.** The exemption is **partial** — it disapplies four named paragraphs,
> not the whole rule. A tool that reports "GLBA does not apply" below 5,000 consumers would
> be wrong.

### Not verified

`[FACT NEEDED]` — CCPA/CPRA section range and its three applicability thresholds
(`leginfo.legislature.ca.gov` timed out 2026-08-19); the list of US states with a
comprehensive statute in effect during 2026, with citations and effective dates; FERPA's
operative provisions. **The US pack stays `draft`.**

---

## 5. United Kingdom — NOT VERIFIED

`legislation.gov.uk` answered **every** request on 2026-08-19 — HTML page, `data.xml`,
`data.xht`, over curl, urllib and WebFetch — with **HTTP 202 and a zero-length body**, and
never resolved across eight retries. Nothing about the UK could be read on primary source.

`[FACT NEEDED]` — Data Protection Act 2018 s.9 and the UK age of consent for information
society services; the Data (Use and Access) Act 2025 citation, Royal Assent date and phased
commencement schedule; UK GDPR Article 33 as retained and amended. **The UK pack stays
`draft`.** A delegate reported "DPA 2018 s.9, 13 years" and "2025 c. 18, 19 June 2025"; that
is a research lead, **not a source**, and it has not entered the code.

---

## 6. Singapore — NOT VERIFIED

`sso.agc.gov.sg` returned only its site shell, not the text of the Act.

`[FACT NEEDED]` — Personal Data Protection Act 2012 sections imposing the data breach
notification obligation and its deadline; the section requiring a data protection officer;
the Consent Obligation sections; the financial penalty ceiling; the Personal Data Protection
(Amendment) Act 2020 number and commencement. **The Singapore pack stays `draft`.**

---

## Register of open [FACT NEEDED] items

| # | Question | Blocks |
|---|---|---|
| 1 | Exact publication date of G.S.R. 846(E) on egazette.gov.in — 13 or 14 November 2025 | every India commencement date, and live client advice |
| 2 | Which EU Member States lowered the Art 8(1) age, and to what | EU children rail |
| 3 | Whether EEA states are in scope as GDPR regimes | jurisdiction resolver |
| 4 | DPA 2018 s.9 — UK age of consent | UK children rail |
| 5 | Data (Use and Access) Act 2025 — citation, assent, phased commencement | UK pack, `as_at` handling |
| 6 | UK GDPR Art 33 as retained and amended | UK breach rail |
| 7 | PDPA 2012 — breach notification section and deadline | SG breach rail |
| 8 | PDPA 2012 — DPO section | SG governance rail |
| 9 | PDPA 2012 — Consent Obligation sections | SG consent rail |
| 10 | PDPA 2012 — penalty ceiling provision | SG penalty rail |
| 11 | PDPA (Amendment) Act 2020 — number and commencement | SG `as_at` handling |
| 12 | Quebec — PIA for communication outside Quebec | Canada sub-national rail |
| 13 | Quebec — age of parental consent | Canada children rail |
| 14 | Quebec — penalty ceilings | Canada penalty rail |
| 15 | Quebec — person in charge of protection of personal information | Canada governance rail |
| 16 | Canadian provincial statutes beyond Quebec | Canada tree |
| 17 | CCPA/CPRA — section range and three applicability thresholds | US California rail |
| 18 | US states with a comprehensive statute in effect in 2026, with citations and effective dates | whole US state tree |
| 19 | FERPA — operative provisions | US education rail |
| 20 | DPDP Rules 10–12 — verifiable consent mechanics | India children and disability rails |

Items 1 and 18 are the two that most constrain the tool's usefulness. Item 1 is one lookup
on the e-Gazette. Item 18 is a research task with no single official source — a delegate
searching state legislature sites reported, correctly, that no aggregated official list
exists, so it has to be assembled statute by statute.
