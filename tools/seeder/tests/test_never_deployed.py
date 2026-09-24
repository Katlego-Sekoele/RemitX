"""The seeder is a local tool. Nothing that deploys may reach it."""

from __future__ import annotations

import re

from remitx_seeder.settings import REPO_ROOT

DEPLOY_SURFACES = [
    *sorted((REPO_ROOT / "infra").rglob("*.tf")),
    *sorted((REPO_ROOT / "infra").rglob("*.tfvars")),
    REPO_ROOT / ".github" / "workflows" / "deploy.yml",
    REPO_ROOT / "api" / "Dockerfile",
    REPO_ROOT / "api" / "Dockerfile.worker",
    REPO_ROOT / "docker-compose.yml",
]


def test_no_deploy_surface_mentions_the_seeder():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in DEPLOY_SURFACES
        if path.exists()
        and re.search(r"tools/seeder|remitx[-_]seeder", path.read_text())
    ]
    assert offenders == []


def test_deploys_are_not_triggered_by_seeder_changes():
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    assert '"tools/**"' not in workflow and "tools/" not in workflow


def test_the_seeder_lives_outside_every_docker_context():
    seeder = REPO_ROOT / "tools" / "seeder"
    for context in (REPO_ROOT / "api", REPO_ROOT / "frontend"):
        assert context not in seeder.parents


def test_the_ui_binds_to_localhost_only():
    from remitx_seeder.ui import app

    assert app.HOST == "127.0.0.1"
