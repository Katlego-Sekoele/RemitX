locals {
  common_secret_values = {
    DATABASE_URL        = local.database_url
    REDIS_URL           = local.redis_url
    CLERK_SECRET_KEY    = var.clerk_secret_key
    XRPL_ENCRYPTION_KEY = var.xrpl_encryption_key
  }

  api_required_secret_values = merge(local.common_secret_values, {
    EXCHANGE_RATE_API_KEY = var.exchange_rate_api_key
  })
  api_optional_secret_values = {
    OBJECT_STORAGE_ACCESS_KEY_ID     = var.object_storage_access_key_id
    OBJECT_STORAGE_SECRET_ACCESS_KEY = var.object_storage_secret_access_key
  }
  api_secret_values = merge(local.api_required_secret_values, {
    for name, value in local.api_optional_secret_values :
    name => value if nonsensitive(value != "")
  })

  worker_required_secret_values = merge(local.common_secret_values, {
    PLATFORM_WALLET_SEED_ENCRYPTED = var.platform_wallet_seed_encrypted
  })
  worker_optional_secret_values = {
    EVM_ENCRYPTION_KEY         = var.evm_encryption_key
    EVM_TREASURY_KEY_ENCRYPTED = var.evm_treasury_key_encrypted
  }
  worker_secret_values = merge(local.worker_required_secret_values, {
    for name, value in local.worker_optional_secret_values :
    name => value if nonsensitive(value != "")
  })

  secret_values       = merge(local.api_secret_values, local.worker_secret_values)
  secret_names        = nonsensitive(toset(keys(local.secret_values)))
  api_secret_names    = nonsensitive(toset(keys(local.api_secret_values)))
  worker_secret_names = nonsensitive(toset(keys(local.worker_secret_values)))
  secret_ids = {
    for name in local.secret_names :
    name => "remitx-${var.environment}-${replace(lower(name), "_", "-")}"
  }
}

resource "google_secret_manager_secret" "runtime" {
  for_each = local.secret_names

  secret_id = local.secret_ids[each.key]
  replication {
    auto {}
  }

  depends_on = [
    google_project_service.this,
    google_project_iam_member.github_deploy,
  ]
}

resource "google_secret_manager_secret_version" "runtime" {
  for_each = local.secret_names

  secret      = google_secret_manager_secret.runtime[each.key].id
  secret_data = local.secret_values[each.key]
}

resource "google_secret_manager_secret_iam_member" "api" {
  for_each = local.api_secret_names

  secret_id = google_secret_manager_secret.runtime[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "worker" {
  for_each = local.worker_secret_names

  secret_id = google_secret_manager_secret.runtime[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

locals {
  api_secret_env = {
    for name in local.api_secret_names :
    name => google_secret_manager_secret.runtime[name].secret_id
  }
  worker_secret_env = {
    for name in local.worker_secret_names :
    name => google_secret_manager_secret.runtime[name].secret_id
  }
}
