# GCP rollout: preflight, Artifact Registry push, Cloud Run, Firebase Hosting.
# Terraform lives in ../infra/Makefile.
#
# Required env (GitHub Actions sets these on deploy jobs):
#   DEPLOY_ENV=qa|prod  GCP_PROJECT_ID  GCP_REGION (default africa-south1)
#   GOOGLE_CREDENTIALS  NEON_*  TF_CLOUD_ORGANIZATION  TF_TOKEN_app_terraform_io
#   SERVICE_ROLE=api|worker (Cloud Run)  IMAGE=... (after push, or from TF output)
#   GITHUB_SHA or IMAGE_TAG for image tags (default: local)

.DEFAULT_GOAL := help
SHELL := bash

REPO_ROOT := $(abspath ..)
DEPLOY_SCRIPTS := $(REPO_ROOT)/.github/scripts
ENV ?= qa
SERVICE_ROLE ?= api
GCP_REGION ?= africa-south1
# Empty GitHub var must not override the default (Make treats export AR_REPO= as set).
_AR_REPO := $(if $(strip $(AR_REPO)),$(AR_REPO),remitx)
IMAGE_TAG ?= $(or $(GITHUB_SHA),local)
REGISTRY := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT_ID)/$(_AR_REPO)

.PHONY: help
help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-24s %s\n", $$1, $$2} /^##@ / {printf "\n%s\n", substr($$0, 5)}' $(MAKEFILE_LIST)

.PHONY: check-deploy-env check-cloud-run
check-deploy-env: ## Fail if DEPLOY_ENV / GCP_PROJECT_ID unset
	@test -n "$${DEPLOY_ENV:-}" || { echo "Set DEPLOY_ENV=qa|prod" >&2; exit 1; }
	@test -n "$${GCP_PROJECT_ID:-}" || { echo "Set GCP_PROJECT_ID" >&2; exit 1; }

check-cloud-run: check-deploy-env ## Fail if SERVICE_ROLE is api or worker
	@test "$${SERVICE_ROLE}" = api -o "$${SERVICE_ROLE}" = worker \
	  || { echo "SERVICE_ROLE must be api or worker (got '$${SERVICE_ROLE}')" >&2; exit 1; }

##@ Rollout checks

.PHONY: preflight
preflight: ## Verify rollout secrets/vars (GOOGLE_CREDENTIALS, NEON_*, GCP_PROJECT_ID)
	"$(DEPLOY_SCRIPTS)/gcp-preflight-rollout.sh"

##@ Container images (Artifact Registry)

.PHONY: docker-auth push-api push-worker
docker-auth: check-deploy-env ## gcloud configure-docker for $(GCP_REGION)
	gcloud auth configure-docker "$(GCP_REGION)-docker.pkg.dev" --quiet

push-api: check-deploy-env docker-auth ## Build and push api:$(IMAGE_TAG); sets IMAGE in GITHUB_ENV when present
	@IMAGE="$(REGISTRY)/api:$(IMAGE_TAG)"; \
	docker build -f "$(REPO_ROOT)/api/Dockerfile" -t "$$IMAGE" "$(REPO_ROOT)/api"; \
	docker push "$$IMAGE"; \
	echo "Pushed $$IMAGE"; \
	if [ -n "$${GITHUB_ENV:-}" ]; then echo "IMAGE=$$IMAGE" >> "$$GITHUB_ENV"; else export IMAGE="$$IMAGE"; fi

push-worker: check-deploy-env docker-auth ## Build and push worker:$(IMAGE_TAG); sets IMAGE in GITHUB_ENV when present
	@IMAGE="$(REGISTRY)/worker:$(IMAGE_TAG)"; \
	docker build -f "$(REPO_ROOT)/api/Dockerfile.worker" -t "$$IMAGE" "$(REPO_ROOT)/api"; \
	docker push "$$IMAGE"; \
	echo "Pushed $$IMAGE"; \
	if [ -n "$${GITHUB_ENV:-}" ]; then echo "IMAGE=$$IMAGE" >> "$$GITHUB_ENV"; else export IMAGE="$$IMAGE"; fi

##@ Cloud Run + Firebase

.PHONY: deploy-cloud-run deploy-frontend
deploy-cloud-run: check-cloud-run ## gcloud run deploy from Terraform outputs (needs IMAGE or TF default)
	"$(DEPLOY_SCRIPTS)/gcp-deploy-cloud-run.sh"

deploy-frontend: check-deploy-env ## npm build + firebase hosting deploy
	"$(DEPLOY_SCRIPTS)/gcp-deploy-firebase.sh"
