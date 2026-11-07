"""Where the ORIGINAL PDF files are kept. Which place depends on APP_MODE.

    local  -> a folder on your disk:      .meridian/uploads/
    cloud  -> an Amazon S3 bucket:        s3://<S3_BUCKET_NAME>/<S3_PREFIX>

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
        return f"s3://{settings.S3_BUCKET_NAME}/{settings.S3_PREFIX}"
    return settings.local_upload_dir


def _s3():
    if not settings.S3_BUCKET_NAME:
        raise ConfigurationError("APP_MODE=cloud needs S3_BUCKET_NAME.")
    import boto3  # only needed (and imported) in cloud mode

    return boto3.client("s3", region_name=settings.AWS_REGION)


def save(local_path: str, filename: str) -> str:
    """Keep a copy of the uploaded PDF. Returns where it was stored."""
    filename = os.path.basename(filename)
    if settings.is_cloud:
        key = f"{settings.S3_PREFIX}{filename}"
        _s3().upload_file(local_path, settings.S3_BUCKET_NAME, key, ExtraArgs={"ContentType": "application/pdf"})
        stored_at = f"s3://{settings.S3_BUCKET_NAME}/{key}"
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
            s3 = _s3()
            for page in s3.get_paginator("list_objects_v2").paginate(
                Bucket=settings.S3_BUCKET_NAME, Prefix=settings.S3_PREFIX
            ):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not key.lower().endswith(".pdf"):
                        continue
                    path = os.path.join(tmp_dir, os.path.basename(key))
                    s3.download_file(settings.S3_BUCKET_NAME, key, path)
                    yield path, f"s3://{settings.S3_BUCKET_NAME}/{key}"

        yield _download()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
