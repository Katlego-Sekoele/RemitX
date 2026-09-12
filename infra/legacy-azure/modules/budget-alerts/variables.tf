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
