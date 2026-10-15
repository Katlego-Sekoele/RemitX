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
variable "ingress" { type = string }
variable "vpc_network" { type = string }
variable "vpc_subnetwork" { type = string }
variable "vpc_egress" { type = string }
variable "custom_domain" {
  type    = string
  default = ""
}
