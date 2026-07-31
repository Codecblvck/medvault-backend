"""
S3-compatible object storage client.

Points at a local MinIO instance for development. Since MinIO speaks the
same API as AWS S3, this same code works against real AWS S3 later by
changing only the config values, not this file.
"""

import boto3
from botocore.exceptions import ClientError
from flask import current_app
from app.config import Config


def get_s3_client():
    """
    Build and return a boto3 S3 client pointed at the configured endpoint.

    The endpoint_url is the one thing that differs from a real AWS setup.
    Pointed at MinIO now, pointed at nothing (removed) for real AWS later.
    """
    return boto3.client(
        "s3",
        endpoint_url=Config.S3_ENDPOINT,
        aws_access_key_id=Config.S3_ACCESS_KEY,
        aws_secret_access_key=Config.S3_SECRET_KEY,
    )


def upload_file(file_obj, object_key):
    """
    Upload a file-like object to the configured bucket under object_key.

    file_obj: the file object straight from Flask's request.files, e.g.
              request.files["file"]
    object_key: the path/name to store it under in the bucket, e.g.
                "records/<record_id>/<original_filename>"

    Returns True on success, raises on failure so the caller's route
    can decide how to respond (and can choose not to write a DB row
    if this fails).
    """
    client = get_s3_client()

    try:
        client.upload_fileobj(file_obj, Config.S3_BUCKET_NAME, object_key)
    except ClientError as e:
        raise RuntimeError(f"File upload to storage failed: {e}")

    return True


def get_file_url(object_key, expires_in=3600):
    """
    Generate a temporary, signed URL for retrieving a private object.

    expires_in is in seconds, default 1 hour. This is how an authorized
    user gets the file itself without the bucket ever being public.
    """
    client = get_s3_client()

    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": Config.S3_BUCKET_NAME, "Key": object_key},
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        raise RuntimeError(f"Could not generate file access link: {e}")

    return url


def delete_file(object_key):
    """
    Delete an object from the bucket. Not currently wired into any
    route, but here for completeness, e.g. if a record is later
    permanently purged rather than just deactivated.
    """
    client = get_s3_client()

    bucket_name = current_app.config.get("S3_BUCKET_NAME")

    try:
        client.delete_object(Bucket=bucket_name, Key=object_key)
    except ClientError as e:
        raise RuntimeError(f"File deletion failed: {e}")

    return True
