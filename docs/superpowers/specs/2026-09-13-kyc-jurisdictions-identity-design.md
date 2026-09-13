# KYC Jurisdictions and Identity Schemes Design

**Date:** 2026-09-13
**Status:** Implemented
**Branch:** `60-kyc-5-onboarding-flow`

## Summary

Onboarding treats country as free text and identification as "South African,
or something we do not check". Four country fields accept any two letters
(`XX` saves), a passport number is never validated, and the SA ID check runs on
every `national_id` whatever its issuing country — so a US applicant who picks
"national ID" is told their number must be 13 digits. `"ZA"` is hard-coded in
the risk rules and in every frontend default, and although the reason code
`UNSUPPORTED_JURISDICTION` exists, nothing ever refuses an applicant for where
they live.

This design makes both concepts data:

- a **`countries`** table — every ISO 3166-1 country, with `operates_in` true
  for **South Africa** and the **United States** only;
- a **`kyc_identity_schemes`** table — which identification each country
  supports, and which validator checks its number.

Residence is the gate: an applicant must live in a country we operate in.
Nationality is unrestricted, and a passport from any country is accepted, so
internationals living in South Africa can onboard. Adding a jurisdiction later
is a migration flipping `operates_in`, plus a scheme row and — only if its
number format is new — a validator function.

## Decisions

| Question | Decision | Why |
|---|---|---|
| What does "operate in" gate on? | **Residential country** | The regulator that matters is where the customer lives. Gating on nationality would block the internationals a passport is meant to serve. |
| What is a US "national ID"? | **Social Security Number** | The US has no national ID card; SSN is the identifier US customer identification programmes collect, and it has real format rules. The uploaded document is still a government photo ID. |
| Passports | **Any issuing country, with an expiry date** | Any country, or the passport option serves nobody. Expiry is required and must be in the future; `DOCUMENT_EXPIRED` already exists as a reason code. |
| When is an applicant told we do not operate where they live? | **Both** — on welcome, before a draft exists, and again on the address step if they change it | Nobody should type an ID number before learning they cannot finish; nobody should be able to change their way around the gate either. |
| Where does the knowledge live? | **Reference tables, validators keyed by row** | The KYC module's established pattern: tiers, risk signals and the onboarding catalogue are rows the API reads, with only logic (`SIGNAL_DETECTORS`) in code. A pure-Python registry was rejected because turning a country on would need a deploy and would break "the database is the authority". A frontend-only list was rejected because the API must enforce the gate anyway. |

## Data model

### `countries` (new)

Shared reference data, not KYC-prefixed: beneficiaries (brief §4) will need it.

| column | type | notes |
|---|---|---|
| `code` | text PK | ISO 3166-1 alpha-2, upper case, `CHECK (length(code) = 2 AND code = upper(code))` |
| `name` | text not null | English short name |
| `operates_in` | boolean not null default false | `true` for `ZA` and `US` |

Seeded with every officially assigned ISO 3166-1 alpha-2 code from
`models/orm/country_seed.py` (`COUNTRY_SEEDS`), following the `kyc_seed.py`
convention: the migration inserts the seed, tests load it, nothing reads the
tuples at runtime.

### `kyc_identity_schemes` (new)

| column | type | notes |
|---|---|---|
| `scheme` | text PK | `za_national_id`, `us_national_id`, `za_passport`, `us_passport`, `passport` |
| `country` | text FK → `countries.code`, nullable | `NULL` means "any issuing country" |
| `id_type` | text not null | existing `KycIdType` values: `national_id` / `passport` |
| `label` | text not null | "South African ID", "Social Security Number", "Passport" |
| `validator` | text not null | key into `IDENTITY_VALIDATORS` |
| `requires_expiry` | boolean not null | true for every passport scheme |
| `input_mode` | text not null | `numeric` / `text`, the frontend's `inputMode` |
| `number_hint` | text not null | "13 digits", "9 digits, for example 123-45-6789", "As printed on the photo page" |
| `document_hint` | text not null | For SSN: "Upload a government photo ID, such as a driver's licence". Otherwise the current ID-scan hint. |

Uniqueness: `UNIQUE (country, id_type)` for country-specific rows, plus a
partial unique index on `id_type WHERE country IS NULL` so there is at most one
any-country fallback per type.

Seeds (in `kyc_seed.py`, `IDENTITY_SCHEME_SEEDS`):

| scheme | country | id_type | validator |
|---|---|---|---|
| `za_national_id` | ZA | national_id | `za_id` |
| `us_national_id` | US | national_id | `us_ssn` |
| `za_passport` | ZA | passport | `za_passport` |
| `us_passport` | US | passport | `us_passport` |
| `passport` | — | passport | `icao_passport` |

There is deliberately no any-country `national_id` row: a national ID is only
accepted where we can check its structure.

### `kyc_applications`

- New nullable `id_expiry_date date`.
- `nationality`, `issuing_country`, `residential_country` and `pep_country`
  gain foreign keys to `countries.code`. On Postgres the constraints are
  created `NOT VALID`: new writes are enforced, but submitted and decided
  applications are declared history (FICA §23) and the migration must not
  rewrite what an applicant claimed. `alembic check` must still report no drift.
- `id_type` is unchanged — generic `national_id` / `passport`, same CHECK
  constraint. The pair `(issuing_country, id_type)` identifies the scheme; the
  scheme row supplies the label, so `US` + `national_id` displays as
  "Social Security Number".

### Onboarding catalogue

- New requirement `id-document / id_expiry_date / field / required_when =
  "id_requires_expiry" / copy_on_resubmit = true`.
- `_requirement_applies` gains the `id_requires_expiry` predicate, resolved
  against the reference catalogue (see below).
- The `id-document` step description becomes "ID type, number, issuing
  country, expiry where applicable, and the ID document."

## API

### Reference catalogue

`JurisdictionRepository.load()` (repositories/jurisdiction_repository.py) returns a frozen `JurisdictionCatalogue`
(countries and schemes), mirroring `KycOnboardingRepository` /
`OnboardingCatalogue`. Loading refuses a scheme whose `validator` has no entry
in `IDENTITY_VALIDATORS`, the same way `RiskRuleSet` refuses an active signal
with no detector.

The catalogue offers:

- `country(code) -> Country | None`
- `operating_countries -> tuple[Country, ...]`
- `resolve_scheme(issuing_country, id_type) -> IdentityScheme | None` — the
  country-specific row first, then the any-country row, else `None`.

Services stay pure: the controller loads the catalogue and passes it in.

### `GET /kyc/reference` (new)

Customer router, no PII. Returns:

```json
{
  "countries": [{"code": "ZA", "name": "South Africa", "operates_in": true}],
  "identity_schemes": [{
    "scheme": "us_national_id", "country": "US", "id_type": "national_id",
    "label": "Social Security Number", "requires_expiry": false,
    "input_mode": "numeric", "number_hint": "9 digits, for example 123-45-6789",
    "document_hint": "Upload a government photo ID, such as a driver's licence"
  }]
}
```

Kept off `GET /kyc/application`, which is refetched after every save.

### Validators — `services/identity_validators.py` (new)

Pure functions, `(number: str, *, date_of_birth: date | None) -> str`,
returning the normalised number to store or raising `IdentityFormatError`
with an applicant-facing message about **format only**.

| key | accepts | stores |
|---|---|---|
| `za_id` | Existing `parse_sa_id_number`, plus the existing declared-date-of-birth match. Messages unchanged. | 13 digits |
| `us_ssn` | 9 digits after removing spaces and hyphens; area not `000`, `666` or `900`–`999`; group not `00`; serial not `0000` | 9 digits, no separators |
| `us_passport` | 9 digits, or 1 letter followed by 8 digits | upper case |
| `za_passport` | 1 letter followed by 8 digits | upper case |
| `icao_passport` | 6–9 letters or digits after removing spaces (ICAO 9303 document-number field) | upper case, no spaces |

`services/sa_id_number.py` is unchanged; `za_id` wraps it.

The ZA and US passport patterns must be checked against a published source
while implementing, and the source cited in the validator's docstring. If a
country-specific pattern cannot be confirmed, that scheme row is dropped and
the country falls back to `icao_passport`.

### Validation, by entry point

`validate_merged_identification` is replaced by
`validate_identification(id_type, issuing_country, id_number, date_of_birth,
id_expiry_date, catalogue)`, which returns the normalised number. It runs only
once type, country and number are all present, as today:

1. `resolve_scheme`; none → *"We don't accept a national ID issued by
   {country name}. Use your passport instead."*
2. Run the scheme's validator; store its normalised result.
3. If `requires_expiry` and an expiry date is present, it must be after today
   → otherwise *"This passport has expired."*

Country fields (`_as_country`) now require a code present in `countries` —
*"Choose a country from the list"* — and `residential_country` additionally
requires `operates_in` → `UnsupportedJurisdictionError`:
*"We don't operate in {country name} yet. RemitX currently serves residents of
South Africa and the United States."* (the list comes from the catalogue).

| Entry point | Behaviour |
|---|---|
| `POST /kyc/application` (start) | Accepts an optional body `{"residential_country": "ZA"}`. Unsupported → 400 `UnsupportedJurisdictionError`, **no draft is created**. Supported → stored on the new draft, or on the open draft when resuming. Absent → today's behaviour, so the auto-start in `use-onboarding.ts` keeps working. |
| `PATCH /kyc/application` | Country and residence checks above; merged identification check, now scheme-aware (fixes the SA-checksum-on-a-US-number bug). |
| `POST /kyc/submit` | Re-runs residence and identification checks on the stored draft: catches a passport that expired between save and submit, drafts created before this change, and a country later switched off. |

`UnsupportedJurisdictionError` subclasses `DomainError` in `errors/kyc.py`, so
it maps to 400 like `InvalidKycDraftError`.

### PII

SSN is stored in `id_number`, which `KycApplicationRead` already tail-masks
for staff. No new masking.

## Frontend

### Shared pieces

- **`useKycReference()`** (`hooks/`) — React Query over `GET /kyc/reference`,
  `staleTime: Infinity`.
- **`CountryCombobox`** (`components/kyc/country-combobox.tsx`) — searchable
  by name or code, on shadcn's `combobox` (`npx shadcn@latest add combobox`;
  none is installed today). Replaces all four two-letter text inputs.
- **`ResidenceField`** (`components/kyc/residence-field.tsx`) — the operating
  countries plus **"Somewhere else"**. Choosing it shows a non-destructive
  `Alert`: *"We don't operate in your country yet. RemitX currently serves
  residents of South Africa and the United States."* — names from reference
  data. While it is selected, the owning form cannot be submitted.

### Per step

| Step | Change |
|---|---|
| Welcome | Adds "Where do you live?" (`ResidenceField`). Continue is disabled until a supported country is chosen and sends `residential_country` to start. A resuming applicant sees their saved value. The "does not check your ID against Home Affairs" copy becomes jurisdiction-neutral ("against a government database"). |
| Identity | Nationality → `CountryCombobox`, blank by default (no `"ZA"` assumption). |
| ID document | Order becomes issuing country (defaults to declared nationality) → ID type → number → expiry → upload. ID type options are the schemes resolved for that country (ZA: SA ID / Passport; US: SSN / Passport; elsewhere: Passport only, with a one-line note). Label, `number_hint`, `input_mode` and `document_hint` come from the scheme. A `DatePicker` for expiry appears when `requires_expiry`. The card description explains the check for the selected scheme rather than always the SA ID. Changing the country to one where the chosen type is not offered resets the type. |
| Address | Country → `ResidenceField`, same notice and block. |
| Declarations | PEP country → `CountryCombobox` (any country). |
| Review, admin application pages | Country names and scheme labels instead of `US` / `national_id`. |

### Forms and progress

Every step is a react-hook-form form with a zod schema, rendered with shadcn's
`Field` components (`data-invalid` on the field, `aria-invalid` on the
control, `FieldError` beneath it), validating `onTouched`. Schemas check
presence and shape only — number *format* stays with the API, whose messages
on the ID step are placed on the field they concern (number, type or expiry)
rather than in a banner. `@hookform/resolvers` is pinned to 5.2.x: later
releases pull an optional `@typeschema` peer that conflicts with React
Router's `valibot`.

Progress uses a port of creatorem's stepper (`components/ui/stepper.tsx`,
"circles with connecting lines"). The original keeps the active step in memory
and depends on an unpublished `@kit/utils/stepper`; the port is controlled by
the route, and `maxStep` (the server's `next_step`) replaces
`disableForwardNav`. It replaces `shadcn-space/stepper-03` and the custom
`FormField`.

`lib/api.ts` gains the reference types and `id_expiry_date`.

## Risk rules

Both geography signals are anchored to ZA. Left alone, a US citizen living in
the US with an SSN would fire `foreign_jurisdiction` and
`non_sa_identity_document` — 50, **medium**, 75% limits — for living somewhere
we now serve.

`kyc_assessment_audit_signals` references signal keys, and its model says to
deactivate a signal rather than delete it. Redefining what an existing key
detects would silently change what historical assessments mean, so the
migration **replaces** them:

| Deactivated (`is_active = false`) | New signal (score effect 25) | Fires when |
|---|---|---|
| `foreign_jurisdiction` | `nationality_differs_from_residence` | declared nationality ≠ residential country |
| `non_sa_identity_document` | `non_national_identity_document` | `id_type == passport` |

The second is `id_type == passport` because a national ID can now only be
saved under a scheme with a structural validator (checksum, SSN rules),
whereas a passport number check is much weaker — that difference is the risk.
Neither detector needs the operating-country set, so detectors stay pure and
`RiskRuleSet` is unchanged; the residence gate is what guarantees residence is
supported.

The old detectors and `SOUTH_AFRICA` are removed from `kyc_risk_rules.py`
(inactive rows need no detector). The module docstring's table is updated.

| Applicant | Before | After |
|---|---|---|
| ZA citizen, lives in ZA, SA ID | low (0) | low (0) |
| US citizen, lives in US, SSN | medium (50) | **low (0)** |
| Zimbabwean, lives in ZA, passport | medium (50) | medium (50) |
| SA citizen, lives in US, SA ID | medium (25) | medium (25) |

## Migrations

One revision, `V20260913_HHMM__add_countries_and_identity_schemes.py`, per
[api/alembic/README.md](../../../api/alembic/README.md):

1. Create `countries`, insert `COUNTRY_SEEDS`.
2. Create `kyc_identity_schemes`, insert `IDENTITY_SCHEME_SEEDS`.
3. Add `kyc_applications.id_expiry_date`; add the four country foreign keys
   (`NOT VALID` on Postgres).
4. Insert the `id_expiry_date` onboarding requirement; update the
   `id-document` step description.
5. Insert the two new risk signals; set the two old ones `is_active = false`.

Downgrade reverses each step. New ORM models (`Country`,
`KycIdentityScheme`) inherit `Base` and are imported in
`models/orm/__init__.py`.

## Testing

- **Validators** — table-driven unit tests per validator: valid, each rejection
  rule, normalisation (`123-45-6789` → `123456789`, lower-case passport →
  upper case).
- **Catalogue** — `resolve_scheme` prefers the country row, falls back to the
  any-country row, returns `None` for a national ID from an unsupported
  country; load refuses an unknown validator key.
- **Routes** (`test_kyc_onboarding_routes.py`):
  - start with `FR` → 422, no draft row; with `US` → draft with residence set;
    with no body → unchanged behaviour;
  - PATCH `residential_country=FR` → 422; `nationality=XX` → 422;
  - US + `national_id` + a valid SSN saves normalised, and the SA checksum is
    not applied;
  - `FR` + `national_id` → 422 with the "use your passport" message;
  - passport without expiry blocks submit; expired passport → 422 on PATCH and
    on submit.
- **Risk rules** — update `test_kyc_risk_rules.py` and
  `test_kyc_risk_assessment.py` to the new signals; the four-applicant table
  above becomes a parametrised test.
- **Schema** — `alembic upgrade head` against compose Postgres, then
  `alembic check` reports no drift.
- **Frontend** — `npm run lint`; walk the wizard in the browser as a ZA
  resident with an SA ID, a US resident with an SSN, a ZA resident with a
  foreign passport, and "Somewhere else" on welcome and on address.

## Out of scope

- Remittance limits stay in ZAR for US residents.
- Postal-code formats per country.
- Wiring beneficiary country to `countries` — beneficiaries are not built yet;
  the table is ready when they are.
- Cross-checking an SA ID's citizenship digit against declared nationality.
- Mobile number country restrictions (E.164, any country, as today).
