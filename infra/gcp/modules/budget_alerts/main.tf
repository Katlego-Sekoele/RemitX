locals {
  emails = [for e in split(",", var.alert_emails) : trimspace(e) if trimspace(e) != ""]

  segment_size      = var.budget_amount_usd
  step              = var.budget_alert_step_usd
  steps_per_segment = local.segment_size / local.step
  segment_count     = var.budget_alert_coverage_usd / local.segment_size

  # GCP budgets compare project spend to each resource's cap. One budget per
  # $segment_size window, with thresholds only for *new* steps in that window,
  # so we do not re-email at $2/$4/… when a higher-cap budget would also cross.
  segments = {
    for s in range(1, local.segment_count + 1) :
    s => {
      cap_usd = s * local.segment_size
      threshold_percents = [
        for i in range(1, local.steps_per_segment + 1) :
        ((s - 1) * local.segment_size + (i * local.step)) / (s * local.segment_size)
      ]
    }
  }
}

moved {
  from = google_billing_budget.this
  to   = google_billing_budget.segment["1"]
}

resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(local.emails)
  display_name = "remitx-budget-${each.key}"
  type         = "email"
  labels = {
    email_address = each.key
  }
}

resource "google_billing_budget" "segment" {
  for_each        = local.segments
  billing_account = var.billing_account_id
  display_name    = "${var.display_name}-through-${each.value.cap_usd}usd"

  budget_filter {
    projects = ["projects/${var.project_number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(each.value.cap_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = each.value.threshold_percents
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  all_updates_rule {
    monitoring_notification_channels = [
      for c in google_monitoring_notification_channel.email : c.id
    ]
  }
}
