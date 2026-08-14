from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import subprocess
import tempfile

import boto3
from botocore.client import Config


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    database_url = require_env("DATABASE_URL")
    account_id = require_env("R2_ACCOUNT_ID")
    bucket_name = require_env("R2_BUCKET_NAME")
    access_key_id = require_env("R2_ACCESS_KEY_ID")
    secret_access_key = require_env("R2_SECRET_ACCESS_KEY")
    retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

    timestamp = datetime.now(UTC)
    filename = f"ase-{timestamp.strftime('%Y-%m-%dT%H-%M-%SZ')}.dump"
    key = f"backups/postgres/{filename}"

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        dump_path = Path(temporary_directory) / filename
        subprocess.run(
            [
                "pg_dump",
                "--dbname",
                database_url,
                "--format=custom",
                "--file",
                str(dump_path),
            ],
            check=True,
        )
        client.upload_file(
            str(dump_path),
            bucket_name,
            key,
            ExtraArgs={"ContentType": "application/octet-stream"},
        )
        print(f"Uploaded {key} ({dump_path.stat().st_size} bytes)")

    cutoff = timestamp - timedelta(days=retention_days)
    old_keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name, Prefix="backups/postgres/"):
        for item in page.get("Contents", []):
            if item["Key"] != key and item["LastModified"] < cutoff:
                old_keys.append(item["Key"])

    for start in range(0, len(old_keys), 1000):
        client.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": [{"Key": old_key} for old_key in old_keys[start : start + 1000]]},
        )
    if old_keys:
        print(f"Deleted {len(old_keys)} backups older than {retention_days} days")


if __name__ == "__main__":
    main()
