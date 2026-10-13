variable "project_number" { type = string }
variable "billing_account_id" { type = string }

variable "budget_amount_usd" {
  type        = number
  description = "Planning segment size in USD (default target); alerts also fire at 100% of each segment cap ($10, $20, …)."
  validation {
    condition     = var.budget_amount_usd > 0
    error_message = "budget_amount_usd must be positive."
  }
}

variable "budget_alert_step_usd" {
  type        = number
  description = "Email on each whole-dollar step of current project spend."
  validation {
    condition = (
      var.budget_alert_step_usd > 0
      && floor(var.budget_amount_usd / var.budget_alert_step_usd) * var.budget_alert_step_usd == var.budget_amount_usd
      && (var.budget_amount_usd / var.budget_alert_step_usd) <= 5
    )
    error_message = "budget_amount_usd must be a positive multiple of budget_alert_step_usd with at most 5 steps per segment (GCP budget rule limit)."
  }
}

variable "budget_alert_coverage_usd" {
  type        = number
  description = "Continue step alerts through this monthly spend (multiples of budget_amount_usd)."
  validation {
    condition = (
      var.budget_alert_coverage_usd >= var.budget_amount_usd
      && floor(var.budget_alert_coverage_usd / var.budget_amount_usd) * var.budget_amount_usd == var.budget_alert_coverage_usd
    )
    error_message = "budget_alert_coverage_usd must be a positive multiple of budget_amount_usd."
  }
}

variable "alert_emails" { type = string }
variable "display_name" { type = string }
