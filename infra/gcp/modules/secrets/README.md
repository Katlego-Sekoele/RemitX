# Secret Manager (phase 2)

Runtime secrets currently flow from GitHub Environment secrets into Cloud Run
via the deploy job. When you enable Secret Manager, add `google_secret_manager_secret`
resources here and switch `cloud_run_service` to `value_source.secret_key_ref`.
