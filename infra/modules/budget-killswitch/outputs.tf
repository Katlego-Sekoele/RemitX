output "action_group_id" {
  value = azurerm_monitor_action_group.killswitch.id
}

output "webhook_expiry" {
  value       = azurerm_automation_webhook.scale_to_zero.expiry_time
  description = "Renew (bump webhook_expiry and re-apply) before this date or the killswitch stops firing silently"
}
