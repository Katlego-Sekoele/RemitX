variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "daily_quota_gb" {
  description = <<-EOT
    Ceiling on Log Analytics ingestion per UTC day, in GB. -1 is uncapped.

    This is the one meter that bills with every replica at zero, so a parked
    environment sets a cap as a backstop against a log loop rather than as a
    target. Ingestion stops for the rest of the day once the cap is hit and
    that data is lost, not queued — do not cap an environment you are
    actually watching.
  EOT

  type    = number
  default = -1
}
