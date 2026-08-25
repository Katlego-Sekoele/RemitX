variable "name_prefix" { type = string }
variable "resource_group_name" { type = string }
variable "resource_group_id" { type = string }
variable "subscription_id" { type = string }
variable "alert_emails" { type = list(string) }
variable "monthly_budget_cap" {
  type    = number
  default = 20
  validation {
    condition     = var.monthly_budget_cap >= 5 && var.monthly_budget_cap % 5 == 0
    error_message = "monthly_budget_cap must be a positive multiple of 5 (Azure allows 5 thresholds per budget segment)."
  }
}
variable "budget_start_date" { type = string }
variable "enable_subscription_budget" {
  type        = bool
  default     = false
  description = "Enable subscription-wide segment budgets. Set true in prod only (once per subscription)."
}

variable "killswitch_action_group_id" {
  type        = string
  default     = null
  description = "Action group ID to notify only once actual spend hits the full monthly_budget_cap (not the intermediate per-dollar thresholds). Wire in infra/modules/budget-killswitch's action_group_id output to auto-shutdown on overspend; leave null for alert-only budgets."
}
