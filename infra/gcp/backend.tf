terraform {
  cloud {
    # Organization: TF_CLOUD_ORGANIZATION (env var or terraform login context).
    #
    # Empty workspaces { } is intentional: this directory is one codebase for TWO
    # HCP Terraform workspaces (qa + prod). Unlike infra/data (fixed name =
    # remitx-data), the workspace is chosen on every init — never hardcode a single
    # name here or local prod applies would target QA state.
    #
    #   TF_WORKSPACE=remitx-gcp-qa terraform init
    #   TF_WORKSPACE=remitx-gcp-prod terraform init
    #
    # Or: make -C infra gcp-init ENV=qa|prod
    # CI/deploy set TF_WORKSPACE=remitx-gcp-${DEPLOY_ENV} before terraform init.
    workspaces {
    }
  }
}
