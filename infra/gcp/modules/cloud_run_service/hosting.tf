# Custom domain on Firebase Hosting; every path proxies to this Cloud Run service.
# shortcut: Hosting→Cloud Run rewrites omit africa-south1 (Firebase docs, 2026-10-13), move the service to a listed region if apply rejects the version.

resource "google_firebase_hosting_site" "this" {
  count = var.custom_domain != "" ? 1 : 0

  provider = google-beta
  site_id  = var.name
}

resource "google_firebase_hosting_version" "this" {
  count = var.custom_domain != "" ? 1 : 0

  provider = google-beta
  site_id  = google_firebase_hosting_site.this[0].site_id

  config {
    rewrites {
      glob = "**"
      run {
        service_id = google_cloud_run_v2_service.this.name
        region     = var.location
      }
    }
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [google_cloud_run_v2_service_iam_member.public]
}

resource "google_firebase_hosting_release" "this" {
  count = var.custom_domain != "" ? 1 : 0

  provider     = google-beta
  site_id      = google_firebase_hosting_site.this[0].site_id
  version_name = google_firebase_hosting_version.this[0].name
  message      = "Rewrite to Cloud Run"
}

resource "google_firebase_hosting_custom_domain" "this" {
  count = var.custom_domain != "" ? 1 : 0

  provider      = google-beta
  site_id       = google_firebase_hosting_site.this[0].site_id
  custom_domain = var.custom_domain

  depends_on = [google_firebase_hosting_release.this]
}
