# KYC risk rating

How RemitX rates a KYC application, and what the rating changes. The values
below are the seeded defaults. The live values are rows in the database
(`kyc_risk_signals`, `kyc_risk_ratings`, `kyc_tiers`), which compliance can
change without a release.

## Score

At submission, every signal that applies adds its points to a score, which is
capped at 100.

| Signal | Applies when | Points |
|---|---|---|
| PEP declared | The applicant, a family member or a close associate is a domestic or foreign prominent person | 60 |
| Expected volume above standard limit | Expected monthly send exceeds the tier 1 monthly limit | 25 |
| Source of funds "other" | Source of funds declared as other | 25 |
| Nationality differs from residence | Nationality is not the country of residence | 25 |
| Non-national identity document | Identified by passport | 25 |

## Rating

| Rating | Score | Highest tier | Limits | Next review | Decided by |
|---|---|---|---|---|---|
| Low | 0–24 | 2 | 100% of tier | 730 days | Reviewer |
| Medium | 25–59 | 2 | 75% of tier | 365 days | Reviewer |
| High | 60–100 | 1 | 50% of tier | 180 days | Compliance officer |

- A PEP declaration always needs a compliance officer's decision, whatever the
  score.
- A reviewer may override the rating before deciding. They must give a reason,
  and the computed rating is kept beside the override.

## Tiers

| Tier | Name | Daily limit | Monthly limit | Requires |
|---|---|---|---|---|
| 0 | Unverified | R0 | R0 | — |
| 1 | Standard CDD | R3,000 | R25,000 | Approved application |
| 2 | Enhanced CDD | R10,000 | R100,000 | Declared source of wealth |

A customer's limits are their tier's limits multiplied by their rating's
percentage. For example, a medium-risk tier 1 customer may send R2,250 a day and
R18,750 a month.

Declarations are self-declared. Nothing is screened against sanctions, PEP or
adverse-media lists.
