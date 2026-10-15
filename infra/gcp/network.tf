resource "google_compute_network" "this" {
  name                    = "remitx-${var.environment}"
  auto_create_subnetworks = false

  depends_on = [
    google_project_service.this,
    google_project_iam_member.github_deploy,
  ]
}

resource "google_compute_subnetwork" "this" {
  name                     = "remitx-${var.environment}"
  network                  = google_compute_network.this.id
  region                   = var.gcp_region
  ip_cidr_range            = "10.8.0.0/26"
  private_ip_google_access = true
}

resource "google_compute_router" "this" {
  name    = "remitx-${var.environment}"
  region  = var.gcp_region
  network = google_compute_network.this.id
}

resource "google_compute_router_nat" "this" {
  name   = "remitx-${var.environment}"
  router = google_compute_router.this.name
  region = var.gcp_region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
