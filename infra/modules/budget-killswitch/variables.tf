variable "name_prefix" { type = string }
variable "resource_group_name" { type = string }
variable "resource_group_id" { type = string }
variable "location" { type = string }
variable "subscription_id" {
  type        = string
  description = "Subscription GUID (not the /subscriptions/... resource ID) the container apps live in"
}

variable "container_app_names" {
  type        = list(string)
  description = "Container Apps to scale to 0/0 replicas when the budget cap is hit"
}

variable "webhook_expiry" {
  type        = string
  default     = "2028-08-25T00:00:00Z"
  description = "Expiry (RFC3339) for the Automation webhook the budget alert calls. Azure webhooks cannot auto-renew — bump this and re-apply before it lapses, or the killswitch silently stops firing."
}
