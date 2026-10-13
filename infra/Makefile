# Terraform helpers for remitx-data and remitx-gcp-* workspaces.
# Run from repo root: make -C infra help
# deploy.yml terraform job uses *-apply-ci, neon-storage-verify, plan.
# App rollout (Docker, Cloud Run, Firebase): ../deploy/Makefile
#
# HCP Terraform (required for init/plan/apply):
#   export TF_CLOUD_ORGANIZATION=your-org
#   export TF_TOKEN_app_terraform_io=...   # or: terraform login
#
# Data workspace also needs TF_VAR_* (see data/README.md), e.g.:
#   export TF_VAR_hcp_organization=$TF_CLOUD_ORGANIZATION
#   export TF_VAR_neon_api_key=$NEON_API_KEY
#   export TF_VAR_tfe_token=$TF_TOKEN_app_terraform_io
#   export TF_VAR_neon_org_id=...
#   export TF_VAR_neon_project_id=...

.DEFAULT_GOAL := help
SHELL := bash
REPO_ROOT := $(abspath ..)

ENV ?= qa
VALID_ENVS := qa prod
GCP_WS := remitx-gcp-$(ENV)
GCP_TF_ARGS := -var-file=environments/$(ENV).tfvars \
	-var=environment=$(ENV)
GITHUB_TF_ENV := $(REPO_ROOT)/scripts/github-tf-env.sh
GITHUB_TF_ENV_SECRETS := $(REPO_ROOT)/scripts/github-tf-secrets-from-env.sh

# GitHub Environment variables (gh) + optional repo-root .env secrets for TF_VAR_*.
# Skip gh with SKIP_GITHUB_ENV=1; skip .env with SKIP_DOTENV_TF=1.
define load_github_env
	set -a; \
	if [ "$${SKIP_GITHUB_ENV:-}" = "1" ]; then \
	  :; \
	elif command -v gh >/dev/null 2>&1; then \
	  eval "$$($(GITHUB_TF_ENV) $(ENV) --shell)"; \
	else \
	  echo "Install gh and authenticate, or export TF_VAR_* / set SKIP_GITHUB_ENV=1" >&2; \
	  exit 1; \
	fi; \
	if [ "$${SKIP_DOTENV_TF:-}" != "1" ]; then \
	  eval "$$($(GITHUB_TF_ENV_SECRETS))"; \
	fi; \
	set +a
endef
# HCP workspace selection (empty workspaces {} in backend.tf): TF_WORKSPACE, not -cloud-workspace.
GCP_ENV := TF_WORKSPACE=$(GCP_WS)
TF_INIT := terraform init -input=false

.PHONY: help
help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-28s %s\n", $$1, $$2} /^##@ / {printf "\n%s\n", substr($$0, 5)}' $(MAKEFILE_LIST)

.PHONY: check-tfc
check-tfc: ## Fail if HCP Terraform org/token are unset
	@test -n "$${TF_CLOUD_ORGANIZATION:-}" || { echo "Set TF_CLOUD_ORGANIZATION" >&2; exit 1; }
	@test -n "$${TF_TOKEN_app_terraform_io:-}" || { echo "Set TF_TOKEN_app_terraform_io (HCP Terraform API token)" >&2; exit 1; }

.PHONY: check-env check-env-name
check-env-name: ## Validate ENV is qa or prod
	@test "$(filter $(ENV),$(VALID_ENVS))" = "$(ENV)" || { echo "ENV must be qa or prod (got '$(ENV)')" >&2; exit 1; }

check-env: check-tfc check-env-name ## HCP token + ENV for GCP/data targets

##@ GitHub Environment (qa / prod)

.PHONY: github-env github-shell github-env-check
github-env: check-env-name ## Shell exports for ENV → eval "$(make -C infra --no-print-directory github-env ENV=qa)"
	@$(GITHUB_TF_ENV) $(ENV) --shell

github-shell: check-env-name ## Interactive shell with GitHub variables loaded (secrets still manual)
	@bash -c 'set -a; eval "$$($(GITHUB_TF_ENV) $(ENV) --shell)"; set +a; \
	  echo "Loaded GitHub environment $(ENV) (variables only)."; \
	  exec "$$SHELL"'

github-env-check: check-env-name ## Verify required variable names exist on GitHub
	@$(REPO_ROOT)/scripts/github-tf-env-check.sh $(ENV)

##@ remitx-data (infra/data)

.PHONY: data-init data-plan data-apply data-output-urls data-output-ids
data-init: check-tfc ## terraform init for workspace remitx-data
	cd data && $(TF_INIT)

data-plan: check-tfc check-env ## Plan Neon stack (loads GitHub vars for ENV)
	@$(load_github_env); cd data && $(TF_INIT) && terraform plan -input=false

data-apply: check-tfc check-env ## Apply Neon stack (interactive approve)
	@$(load_github_env); cd data && $(TF_INIT) && terraform apply -input=false

data-apply-ci: check-tfc check-env ## Apply Neon stack (CI: -auto-approve)
	@$(load_github_env); cd data && $(TF_INIT) && terraform apply -auto-approve -input=false

data-output-urls: check-tfc ## Print sensitive database_urls output (qa + prod)
	cd data && $(TF_INIT) && terraform output -json database_urls | jq .

data-output-ids: check-tfc ## Print neon_project_id and branch ids (non-sensitive)
	cd data && $(TF_INIT) && terraform output -json \
	  | jq '{neon_project_id, qa_branch_id, prod_branch_id}'

.PHONY: data-import-help
data-import-help: ## Echo Neon import commands (set PROJECT_ID, *_BRANCH_ID, *_ENDPOINT_ID)
	@echo "From infra/data after data-init. See data/README.md."
	@echo ""
	@echo 'terraform import '"'"'module.neon.neon_project.this'"'"' "$${PROJECT_ID}"'
	@echo 'terraform import '"'"'module.neon.neon_branch.qa'"'"' "$${PROJECT_ID}/$${QA_BRANCH_ID}"'
	@echo 'terraform import '"'"'module.neon.neon_branch.prod'"'"' "$${PROJECT_ID}/$${PROD_BRANCH_ID}"'
	@echo 'terraform import '"'"'module.neon.neon_endpoint.qa'"'"' "$${PROJECT_ID}/$${QA_ENDPOINT_ID}"'
	@echo 'terraform import '"'"'module.neon.neon_endpoint.prod'"'"' "$${PROJECT_ID}/$${PROD_ENDPOINT_ID}"'

##@ remitx-gcp-qa | remitx-gcp-prod (infra/gcp) — use ENV=qa|prod

.PHONY: gcp-init gcp-plan gcp-apply gcp-apply-ci gcp-output-deploy-sa
gcp-init: check-env ## terraform init for remitx-gcp-$(ENV) (TF_WORKSPACE)
	cd gcp && $(GCP_ENV) $(TF_INIT)

gcp-plan: check-env ## Plan GCP stack for ENV (loads GitHub env vars via gh)
	@$(load_github_env); cd gcp && $(GCP_ENV) $(TF_INIT) && $(GCP_ENV) terraform plan $(GCP_TF_ARGS)

gcp-apply: check-env ## Apply GCP stack for ENV (interactive approve)
	@$(load_github_env); cd gcp && $(GCP_ENV) $(TF_INIT) && $(GCP_ENV) terraform apply $(GCP_TF_ARGS)

gcp-apply-ci: check-env ## Apply GCP stack for ENV (CI: -auto-approve)
	@$(load_github_env); cd gcp && $(GCP_ENV) $(TF_INIT) && $(GCP_ENV) terraform apply -auto-approve $(GCP_TF_ARGS)

gcp-output-deploy-sa: check-env ## Print github_deploy_service_account_email for ENV workspace
	@$(load_github_env); cd gcp && $(GCP_ENV) $(TF_INIT) && $(GCP_ENV) terraform output -raw github_deploy_service_account_email

##@ Neon object storage (scripts/neon-storage)

.PHONY: neon-storage-verify neon-storage-bootstrap
neon-storage-verify: check-env ## Verify KYC bucket exists (NEON_API_KEY, NEON_PROJECT_ID, NEON_*_BRANCH_ID)
	@test -n "$${NEON_API_KEY:-}" || { echo "Set NEON_API_KEY" >&2; exit 1; }
	@test -n "$${NEON_PROJECT_ID:-}" || { echo "Set NEON_PROJECT_ID" >&2; exit 1; }
	@bid="$${NEON_BRANCH_ID:-}"; \
	if [ -z "$$bid" ]; then case "$(ENV)" in qa) bid="$${NEON_QA_BRANCH_ID:-}" ;; prod) bid="$${NEON_PROD_BRANCH_ID:-}" ;; esac; fi; \
	test -n "$$bid" || { echo "Set NEON_BRANCH_ID or NEON_QA_BRANCH_ID / NEON_PROD_BRANCH_ID for ENV=$(ENV)" >&2; exit 1; }; \
	case "$(ENV)" in \
	  qa)  bucket="remitx-qa-kyc-documents" ;; \
	  prod) bucket="remitx-prod-kyc-documents" ;; \
	esac; \
	NEON_STORAGE_MODE=verify NEON_BRANCH_ID="$$bid" NEON_BUCKET_NAME="$$bucket" \
	  "$(REPO_ROOT)/scripts/neon-storage/ensure.sh"

neon-storage-bootstrap: check-env ## Create bucket/credential if missing (prints secrets once)
	@test -n "$${NEON_API_KEY:-}" || { echo "Set NEON_API_KEY" >&2; exit 1; }
	@test -n "$${NEON_PROJECT_ID:-}" || { echo "Set NEON_PROJECT_ID" >&2; exit 1; }
	@bid="$${NEON_BRANCH_ID:-}"; \
	if [ -z "$$bid" ]; then case "$(ENV)" in qa) bid="$${NEON_QA_BRANCH_ID:-}" ;; prod) bid="$${NEON_PROD_BRANCH_ID:-}" ;; esac; fi; \
	test -n "$$bid" || { echo "Set NEON_BRANCH_ID or NEON_QA_BRANCH_ID / NEON_PROD_BRANCH_ID for ENV=$(ENV)" >&2; exit 1; }; \
	case "$(ENV)" in \
	  qa)  bucket="remitx-qa-kyc-documents" ;; \
	  prod) bucket="remitx-prod-kyc-documents" ;; \
	esac; \
	NEON_STORAGE_MODE=bootstrap NEON_BRANCH_ID="$$bid" NEON_BUCKET_NAME="$$bucket" \
	  "$(REPO_ROOT)/scripts/neon-storage/ensure.sh"
