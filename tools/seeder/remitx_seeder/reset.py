"""Reset: throw the target's data away and rebuild it empty.

In order:

1. Delete the Clerk users the seeder made (`private_metadata.remitx_seed`).
   Your testers' own Clerk accounts stay; their RemitX rows come back on their
   next sign-in, through just-in-time provisioning.
2. Empty the target's KYC document bucket.
3. Drop the `public` schema and recreate it.
4. `alembic upgrade head`: the schema, and every row the migrations own
   (countries, KYC rules, roles and permissions, the platform accounts).

Role grants are not restored: grant your testers theirs again on the Access
page.

Step 4 runs the API's own Alembic as a subprocess from `api/`, exactly as a
developer would, so a reset can never build a different schema than a deploy.
"""

from __future__ import annotations

import os
import subprocess
import sys

from remitx_seeder.clerk import ClerkGateway
from remitx_seeder.context import Emit
from remitx_seeder.settings import REPO_ROOT

API_DIR = REPO_ROOT / "api"


def confirmation_phrase(target: str) -> str:
    return f"reset {target}"


def delete_seeded_clerk_users(clerk: ClerkGateway, emit: Emit) -> int:
    ids = clerk.seeded_user_ids()
    for clerk_user_id in ids:
        clerk.delete_user(clerk_user_id)
    emit(
        {
            "type": "log",
            "level": "info",
            "message": f"Deleted {len(ids)} seeded Clerk users.",
        }
    )
    return len(ids)


def empty_bucket(emit: Emit) -> int:
    """Delete every object in the target's KYC bucket. The bucket name was
    checked against targets.json before this runs."""
    import boto3
    from botocore.config import Config as BotoConfig
    from remitx_api.config import Config

    config = Config()
    if not (config.OBJECT_STORAGE_ACCESS_KEY_ID and config.OBJECT_STORAGE_ENDPOINT_URL):
        emit(
            {
                "type": "log",
                "level": "warning",
                "message": "No bucket credentials: bucket left as it is.",
            }
        )
        return 0
    client = boto3.client(
        "s3",
        endpoint_url=config.OBJECT_STORAGE_ENDPOINT_URL,
        region_name=config.OBJECT_STORAGE_REGION,
        aws_access_key_id=config.OBJECT_STORAGE_ACCESS_KEY_ID,
        aws_secret_access_key=config.OBJECT_STORAGE_SECRET_ACCESS_KEY,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    bucket = config.OBJECT_STORAGE_BUCKET
    deleted = 0
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=item["Key"])
            deleted += 1
    emit(
        {
            "type": "log",
            "level": "info",
            "message": f"Deleted {deleted} objects from {bucket}.",
        }
    )
    return deleted


def recreate_schema(database_url: str, emit: Emit) -> None:
    """Drop and recreate `public` as the connection's own role (the owner in
    every environment), never as the row-security role the app adopts."""
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    emit(
        {
            "type": "log",
            "level": "info",
            "message": "Dropped and recreated the public schema.",
        }
    )


def _run(command: list[str], emit: Emit) -> None:
    emit({"type": "log", "level": "info", "message": "$ " + " ".join(command)})
    process = subprocess.run(
        command,
        cwd=API_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    for line in (process.stdout + process.stderr).splitlines():
        if line.strip():
            emit({"type": "log", "level": "debug", "message": line})
    if process.returncode != 0:
        raise RuntimeError(f"{command[0]} exited {process.returncode}")


def rebuild(emit: Emit) -> None:
    _run([sys.executable, "-m", "alembic", "upgrade", "head"], emit)


def reset(
    target: str, confirmation: str, clerk: ClerkGateway | None, emit: Emit
) -> dict:
    if confirmation != confirmation_phrase(target):
        raise ValueError(f'Type "{confirmation_phrase(target)}" to confirm.')
    from remitx_api.config import Config

    clerk_deleted = delete_seeded_clerk_users(clerk, emit) if clerk else 0
    objects_deleted = empty_bucket(emit)
    recreate_schema(Config.DATABASE_URL, emit)
    rebuild(emit)
    emit({"type": "log", "level": "info", "message": f"{target} is reset."})
    return {"clerk_users_deleted": clerk_deleted, "objects_deleted": objects_deleted}
