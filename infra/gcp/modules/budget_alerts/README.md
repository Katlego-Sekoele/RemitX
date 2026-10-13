# GCP budget email alerts (prod)

Creates Monitoring email notification channels and **segmented** monthly billing budgets on this GCP project.

- **Planning target:** `budget_amount_usd` (root: `monthly_budget_amount`, default **$10**). The alert at **$10** is “100% of the first segment cap,” not the last email of the month.
- **Step:** `budget_alert_step_usd` (default **$2**) — one email per whole **$2** of **current** spend.
- **Coverage:** `budget_alert_coverage_usd` (default **$100**) — alerts keep going at **$12, $14, …** through the coverage cap (implemented as one budget per **$10** window so GCP does not duplicate lower thresholds).
- **Recipients:** comma-separated `alert_emails` (GitHub secret `BUDGET_ALERT_EMAILS` on prod).

GCP budgets **notify only**; they do not block charges. Raise `budget_alert_coverage_usd` (in **$10** increments with the default target) if you need runway beyond **$100**.
