"""Where the ORIGINAL PDF files are kept. Which place depends on APP_MODE.

    local  -> a folder on your disk:      .meridian/uploads/
    cloud  -> an Amazon S3 bucket:         s3://<S3_BUCKET_NAME>/<S3_PREFIX>

Two operations are all the app needs:
    save(local_path, filename)  keep a copy of an uploaded PDF
    pdfs()                      yield (local_path, source_name) for every stored PDF
"""
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from config.settings import settings
from exceptions import ConfigurationError
from logger import GLOBAL_LOGGER as log


def location() -> str:
    """Human-readable location, shown on the System Status tab."""
    if settings.is_cloud:
        return f"s3://{settings.s3_bucket_name}/{settings.s3_prefix}"
    return settings.local_upload_dir


def _bucket():
    if not settings.s3_bucket_name:
        raise ConfigurationError("APP_MODE=cloud needs S3_BUCKET_NAME.")
    import boto3

    return boto3.client("s3", region_name=settings.aws_region)


def save(local_path: str, filename: str) -> str:
    """Keep a copy of the uploaded PDF. Returns where it was stored."""
    filename = os.path.basename(filename)
    if settings.is_cloud:
        object_name = f"{settings.s3_prefix}{filename}"
        _bucket().upload_file(local_path, settings.s3_bucket_name, object_name, ExtraArgs={"ContentType": "application/pdf"})
        stored_at = f"s3://{settings.s3_bucket_name}/{object_name}"
    else:
        os.makedirs(settings.local_upload_dir, exist_ok=True)
        stored_at = os.path.join(settings.local_upload_dir, filename)
        shutil.copyfile(local_path, stored_at)
    log.info("Original file stored", filename=filename, stored_at=stored_at)
    return stored_at


@contextmanager
def pdfs() -> Iterator[Iterator[tuple[str, str]]]:
    """Yield (local_path, source) for every stored PDF.

    Used as a context manager because cloud files are downloaded to a temp folder
    that must be cleaned up afterwards.
    """
    if not settings.is_cloud:
        folder = settings.local_upload_dir
        os.makedirs(folder, exist_ok=True)
        yield (
            (os.path.join(folder, name), f"local://{name}")
            for name in sorted(os.listdir(folder))
            if name.lower().endswith(".pdf")
        )
        return

    tmp_dir = tempfile.mkdtemp()
    try:
        def _download() -> Iterator[tuple[str, str]]:
            client = _bucket()
            pages = client.get_paginator("list_objects_v2").paginate(
                Bucket=settings.s3_bucket_name, Prefix=settings.s3_prefix
            )
            for page in pages:
                for item in page.get("Contents", []):
                    name = item["Key"]
                    if not name.lower().endswith(".pdf"):
                        continue
                    path = os.path.join(tmp_dir, os.path.basename(name))
                    client.download_file(settings.s3_bucket_name, name, path)
                    yield path, f"s3://{settings.s3_bucket_name}/{name}"

        yield _download()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
