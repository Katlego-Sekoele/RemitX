# Secret Manager

Runtime Secret Manager resources are declared in `infra/gcp/secrets.tf`.
Terraform creates one environment-prefixed secret per runtime setting, versions
it from the corresponding sensitive input, and grants only the API or worker
service account access as appropriate.

Cloud Run receives these through `value_source.secret_key_ref`; rollout uses
`gcloud run deploy --set-secrets`. Secret values must never be added back to
the normal `api_env_vars` or `worker_env_vars` outputs.
