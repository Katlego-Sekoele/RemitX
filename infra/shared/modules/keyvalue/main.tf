resource "render_keyvalue" "this" {
  name              = var.name
  plan              = var.plan
  region            = var.region
  max_memory_policy = "noeviction"
  # Empty list: private network only. Free web services can still reach
  # datastores in the same region; the public internet cannot.
  ip_allow_list = []
}
