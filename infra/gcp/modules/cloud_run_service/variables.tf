variable "name" { type = string }
variable "location" { type = string }
variable "container_image" { type = string }
variable "service_account_email" { type = string }
variable "env" {
  type = map(string)
}
variable "secret_env" { type = map(string) }
variable "allow_unauthenticated" { type = bool }
variable "min_instance_count" { type = number }
