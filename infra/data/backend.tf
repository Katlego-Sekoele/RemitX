terraform {
  cloud {
    # Organization: TF_CLOUD_ORGANIZATION in CI / local shell.
    workspaces {
      name = "remitx-data"
    }
  }
}
