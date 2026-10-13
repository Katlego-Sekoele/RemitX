resource "google_firebase_project" "this" {
  provider = google-beta
  project  = var.project_id
}

resource "google_firebase_hosting_site" "this" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.site_id

  depends_on = [google_firebase_project.this]
}

resource "google_firebase_hosting_custom_domain" "this" {
  count = var.custom_domain != "" ? 1 : 0

  provider    = google-beta
  project     = var.project_id
  site_id     = google_firebase_hosting_site.this.site_id
  custom_domain = var.custom_domain

  depends_on = [google_firebase_hosting_site.this]
}
