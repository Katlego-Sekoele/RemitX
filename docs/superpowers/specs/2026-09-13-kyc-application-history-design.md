# KYC Application History Design

**Date:** 2026-09-13
**Status:** Approved

## Summary

A customer's verification becomes a history of applications they can browse,
instead of one wizard that always opens at "where do you live?". Each
application has a read-only detail page — the applicant's version of the admin
review screen — and can be edited only while it is a draft or a reviewer has
asked for more information. A new application can be started only while the
customer is still onboarding or their verification has expired. Verification
moves under Profile.

## Problems with the current flow

1. **The welcome step is the entry point.** `/app/verification` renders
   `routes/onboarding/welcome.tsx` unconditionally, so a customer with a draft,
   a submitted, an approved or a rejected application is asked for their
   country of residence again.
2. **Rejection messages outlive the rejection.** `latest_rejection_reason`
   returns the newest *rejected* application's message whether or not a later
   application exists, so rejected-then-approved still shows "your last
   application was not approved".
3. **Approved customers start new applications by accident.** Welcome's
   "Continue" POSTs `/kyc/application`, which only refuses when an *open*
   application exists. `approved` is not open, so a new `in_progress` row is
   created — and because `get_standing` derives status from the newest row, the
   customer's standing drops from `approved` to `in_progress`.
4. **The API only knows about one application.** There is no way for a
   customer to list their applications or read one by id, so a history cannot
   be built on the frontend alone.

## Rules

### When a new application may start

| Standing | `POST /kyc/applications` |
|---|---|
| `not_started` | Creates an application |
| `rejected` | Creates an application, pre-filled from the rejected one (existing `copy_fields`) |
| `review_due` (including an expired approval, below) | Creates an application, pre-filled |
| `in_progress`, `submitted`, `under_review`, `more_info_required` | Returns the open application unchanged (idempotent resume, as today) |
| `approved`, not expired | Refused: `KycApplicationStartNotAllowedError`, 409 |

The frontend shows "Start new application" only where the first three rows
apply and "Continue" where an open application exists; the server enforces the
rule regardless.

### When an application is editable

`editable` is true only for the caller's open application whose stored status
is in `kyc_onboarding_editable_statuses` (`in_progress`,
`more_info_required`). Every other application is read-only. PATCH and submit
addressed to a non-editable application are refused with 409, as
`KycApplicationNotEditableError` does today.

### Expiry

Approval already stores `next_review_at` (risk-rated interval). Expiry is
derived on read rather than written by a scheduler:

```
effective_status(application, now) =
    review_due  if application.status == approved
                and application.next_review_at is not None
                and application.next_review_at <= now
    application.status  otherwise
```

The stored row is not changed. `get_standing`, the customer endpoints, and the
admin queue and detail responses all report status through `effective_status`,
so admin and customer never disagree. A tier granted by an expired approval
still counts — `VERIFIED_STATUSES` already includes `review_due` — so expiry
unlocks a new application without cutting off an existing customer.

Queue filtering by status continues to use the stored column; an expired
approval is not in the reviewer queue either way, since neither `approved` nor
`review_due` is a queue status.

## API

### Status helper

`effective_status` lives beside the lifecycle definitions in
`models/orm/kyc_lifecycle.py` (pure function, takes `now` so tests control the
clock via `remitx_api.clock.utcnow`). `KycApplicationRepository.get_standing`
uses it for `status`; the admin and customer read schemas populate `status`
from it.

### Applicant message

`KycApplicationRepository.latest_rejection_reason(user_id)` is replaced by
`applicant_message(application)`:

- `more_info_required` → the latest `more_info_required` decision's
  `reason_text` (the fields or documents the reviewer named).
- `rejected` → the catalogue message for the latest rejection's reason code
  (`applicant_message_for`), falling back to `reason_text` for legacy rows with
  no code. Never the reviewer's internal note, never a tipping-off reason.
- Anything else → `None`.

Because the message belongs to one application, an old rejection cannot appear
on a newer one.

### Endpoints

All on the customer router, tag `kyc.onboarding`.

| Method & path | Handler | Notes |
|---|---|---|
| `GET /kyc/application` | `get_application` | Kept: standing, current application, `next_step`. Used by the sidebar, home card and overview. `rejection_reason` removed. |
| `GET /kyc/applications` | `list_my_applications` | Caller's applications, newest first. |
| `GET /kyc/applications/{application_id}` | `get_my_application` | One of the caller's applications; 404 if it belongs to anyone else. |
| `POST /kyc/applications` | `start_application` | Start rule above; optional `residential_country` as today. Replaces `POST /kyc/application`. |
| `PATCH /kyc/applications/{application_id}` | `patch_application` | As today, addressed by id; 404 if not the caller's, 409 if not editable. Replaces `PATCH /kyc/application`. |
| `POST /kyc/applications/{application_id}/submit` | `submit_application` | As today, addressed by id. Replaces `POST /kyc/submit`. |

### Schemas

`KycApplicationSummaryRead` (list item):
`application_id`, `status` (effective), `created_at`, `submitted_at`,
`decided_at`, `tier_granted`, `next_review_at`, `editable`.

`KycApplicantApplicationRead` (new): the applicant's own unmasked declared
fields — identity, contact, address, funds, PEP answers — plus
`application_id`, `status` (effective), `version`, `tier_granted`,
`created_at`, `submitted_at`, `processing_consented_at`, `next_review_at`.

This replaces `KycApplicationReadPII` in **every** applicant response,
including `GET /kyc/application`. Today that endpoint returns
`KycApplicationReadPII`, whose `_ApplicationBase` carries `risk_score`,
`risk_rating`, the rating override and its reason, `effective_risk_rating`,
`risk_rating_overridden_by_user_id` and `reviewer_user_id` — internal
assessment data the applicant should not see (and, for a risk rating, a
tipping-off concern). `KycApplicationReadPII` stays admin-only, behind
`kyc:application:read_pii`, as its docstring already requires.

`KycApplicationDetailRead` (detail):
- `application: KycApplicantApplicationRead`
- `applicant_message: str | None`
- `timeline: list[KycStatusEventRead]` — `status` and `changed_at` only, from
  `kyc_application_history`.
- `editable: bool`, `next_step: str`, `steps`, `stored_document_types`,
  `pep_relationships` — what the step screens need.

Customer schemas carry no risk score or rating, override, reviewer id, reason
code, internal note or assessment audit. They are separate classes that list
what they include, not admin schemas with fields removed, so a field added to
`_ApplicationBase` later does not reach the applicant by default.

### Controller

`KycOnboardingController` gains `list(user_id)`, `detail(user_id,
application_id)`, and id-addressed `patch` / `submit`. A private
`_require_own(user_id, application_id)` returns the application or raises the
404 error, and is the single ownership check every id-addressed method goes
through. `start` checks the start rule against `get_standing` before calling
`KycController.start_application`.

### Tests

- `effective_status`: before, at and after `next_review_at`; `next_review_at`
  null; non-approved statuses unchanged.
- Start rule: each standing in the table, including approved-and-expired.
- Ownership: list, detail, patch and submit with another user's id return 404.
- Rejected, then approved: the approved application's `applicant_message` is
  `None`; the rejected one keeps its message.
- More info required: message is the reviewer's named fields.
- Patch and submit refused for submitted, approved and rejected applications.
- `GET /kyc/application`, `GET /kyc/applications` and
  `GET /kyc/applications/{id}` responses contain none of the internal fields,
  on an application that has been scored, overridden and claimed.
- `test_openapi.py` passes with the regenerated `frontend/openapi.json`.

## Frontend

### Routes

Declared under `routes/app/layout.tsx` in `routes.ts`; modules move from
`routes/onboarding/` to `routes/app/verification/`.

| Path | Module | Screen |
|---|---|---|
| `app/profile/verification` | `history.tsx` | Current-standing card (status badge, tier, review due date) and the application list, newest first, each linking to its detail. "Start new application" when the start rule allows; "Continue" when an open application exists. |
| `app/profile/verification/new` | `new.tsx` | The residence question (today's welcome). Submitting POSTs and navigates to the returned application's `next_step`. |
| `app/profile/verification/:applicationId` | `application.tsx` | Detail page (below). |
| `app/profile/verification/:applicationId/<step>` | existing step modules under `application-layout.tsx` | Loads the application by id; if not `editable`, redirects to its detail page. |
| `app/verification`, `app/verification/*`, `onboarding`, `onboarding/*` | redirect modules | Redirect to `app/profile/verification`. |

Removed: `routes/onboarding/status.tsx`, `components/kyc/rejection-banner.tsx`,
the `welcome` step as a route.

### Detail page

The applicant's version of `components/admin/kyc-review/application-review.tsx`:

- Header: title, status badge, created / submitted / decided dates.
- `applicant_message` as an `Alert` — "A reviewer needs something from you" for
  more info, "Not approved" for rejection.
- Main column: `IdentitySection`, `ContactSection`, `FundsSection`,
  `PepSection`, documents with view links, status timeline.
- Side column: status summary; when `editable`, "Continue" (`in_progress`) or
  "Update and resubmit" (`more_info_required`) linking to `next_step`.

No risk badge, PEP badge, decision panel, reveal button or risk history.

### Shared components

- `IdentitySection`, `ContactSection`, `FundsSection`, `PepSection` move from
  `components/admin/kyc-review/detail-sections.tsx` to
  `components/kyc/application-sections.tsx`; admin imports from there. They
  read declared fields only, so their prop type narrows to the fields shared by
  `KycApplicantApplicationRead`, `KycApplicationRead` and
  `KycApplicationReadPii`.
- `KycApplicationDocuments` takes its documents query as a prop so the admin
  and customer pages share it.

### Paths

`lib/kyc-onboarding.ts` is the only place verification URLs are built:
`verificationPath()`, `newApplicationPath()`, `applicationPath(id)`,
`applicationStepPath(id, step)`. `pathForStep` is removed; the home card,
overview, progress bar and step hooks use the builders.

### Step hooks

`useOnboarding` reads `KycApplicationDetailRead` from the id-based layout's
outlet context. `useSaveStep` PATCHes and submit POSTs by id. The implicit
"start if nothing exists" branch in `useSaveStep` is removed — `/new` owns
starting.

### Navigation

- The Verification entry in `APP_ROUTE_INDEX` points at
  `app/profile/verification`, keeps `kycAttention`, and gains
  `hideWhenVerified: true`. `app-nav.tsx` filters on the standing it already
  fetches.
- `app-nav.tsx` marks only the longest matching href active, so Profile and
  Verification are not both highlighted on verification pages.
- The Profile page gains a Verification card: current status and "View
  history".
- Home and overview CTAs link to `verificationPath()`.

### Checks

`npm run typecheck`, then a browser pass through each state: not started,
draft, submitted, more info required, rejected → new application (pre-filled),
approved (no start button, nav item hidden, old rejection message absent),
expired approval (start button returns).

## Out of scope

- A scheduler that writes `review_due` to the row.
- Withdrawing or deleting an application.
- Changing details on an approved application outside a new application.
