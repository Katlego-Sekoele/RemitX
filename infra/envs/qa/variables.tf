variable "environment" {
  type = string
}

variable "location" {
  type    = string
  default = "southafricanorth"
}

variable "tags" {
  type    = map(string)
  default = {}
}
