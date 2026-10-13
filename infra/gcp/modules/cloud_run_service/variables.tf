variable "name" { type = string }
variable "location" { type = string }
variable "container_image" { type = string }
variable "service_account_email" { type = string }
variable "env" {
  type      = map(string)
  sensitive = true
}
variable "allow_unauthenticated" { type = bool }
variable "min_instance_count" { type = number }
