#!/usr/bin/env python3
"""
Storage interaction module.

Handles uploading and deleting files from cloud storage (AWS S3 or compatible like Cloudflare R2).
Also manages local file cleanup.
"""

import os
import tempfile
import logging

try:
    import boto3  # Optional; required only for live storage operations
except Exception:
    boto3 = None  # type: ignore

try:
    from botocore.exceptions import ClientError as BotoClientError  # Optional
except Exception:  # pragma: no cover - fallback when botocore not present
    class BotoClientError(Exception):  # type: ignore
        """Placeholder for botocore.exceptions.ClientError if library is missing."""
        pass

import config

logger = logging.getLogger(__name__)

# Custom exception for storage errors
class ClientError(Exception):
    """Custom exception raised for storage-related errors."""
    pass

# Lazy S3 client initialization
def _get_s3_client():
    """Initializes and returns a boto3 S3 client using configured credentials.

    Returns:
        boto3.client: The configured S3 client.

    Raises:
        ClientError: If boto3 is not installed.
    """
    if boto3 is None:
        raise ClientError("boto3 is required for storage operations but is not installed.")
    endpoint_url = config.config.get(('storage', 'endpoint_url'))
    aws_access_key_id = config.config.get(('storage', 'access_key_id'))
    aws_secret_access_key = config.config.get(('storage', 'secret_access_key'))
    region_name = config.config.get(('storage', 'region'), 'auto')
    return boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name
    )

def _get_bucket():
    """Retrieves the bucket name from configuration.

    Returns:
        str: The configured bucket name.
    """
    return config.config.get(('storage', 'bucket'))

# List all files in the storage bucket
def list_storage_files():
    """Lists all files in the configured storage bucket.

    Returns:
        list: A list of filenames (keys) in the bucket.

    Raises:
        ClientError: If the S3 list operation fails.
    """
    s3 = _get_s3_client()
    bucket = _get_bucket()
    try:
        resp = s3.list_objects_v2(Bucket=bucket)
        files = [obj['Key'] for obj in resp.get('Contents', [])]
        logger.info("Listed %d files in storage bucket %s", len(files), bucket)
        return files
    except BotoClientError as e:
        logger.error("Error listing files in storage: %s", e)
        raise ClientError(str(e)) from e

# Generate a presigned URL for a file
def get_file_url(filename, expires_in=86400):
    """Generates a presigned URL for a file in storage.

    Args:
        filename (str): The name (key) of the file.
        expires_in (int): The validity duration of the URL in seconds.

    Returns:
        str | None: The presigned URL, or None if generation failed.
    """
    s3 = _get_s3_client()
    bucket = _get_bucket()
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': filename},
            ExpiresIn=expires_in
        )
        logger.info("Generated presigned URL for %s", filename)
        return url
    except BotoClientError as e:
        logger.error("Error generating file URL: %s", e)
        return None

# Delete a file from storage (supports dry_run)
def delete_from_storage(filename, dry_run=False):
    """Deletes a file from storage.

    Args:
        filename (str): The name (key) of the file to delete.
        dry_run (bool): If True, simulate deletion.

    Returns:
        bool: True if deletion was successful (or simulated), False otherwise.
    """
    s3 = _get_s3_client()
    bucket = _get_bucket()
    if dry_run:
        logger.info("[Dry Run] Would delete %s from bucket %s", filename, bucket)
        return True
    try:
        s3.delete_object(Bucket=bucket, Key=filename)
        logger.info("Deleted %s from bucket %s", filename, bucket)
        return True
    except BotoClientError as e:
        logger.error("Error deleting file %s: %s", filename, e)
        return False

# Upload a file to storage (supports dry_run)
def upload_to_storage(local_file_path, s3_key, dry_run=False):
    """Uploads a local file to storage.

    Args:
        local_file_path (str): The path to the local file.
        s3_key (str): The destination key (filename) in the bucket.
        dry_run (bool): If True, simulate upload.

    Returns:
        bool: True if upload was successful (or simulated), False otherwise.
    """
    s3 = _get_s3_client()
    bucket = _get_bucket()
    if dry_run:
        logger.info("[Dry Run] Would upload %s to %s/%s", local_file_path, bucket, s3_key)
        return True
    if not os.path.isfile(local_file_path):
        logger.error("File to upload does not exist: %s", local_file_path)
        return False
    try:
        s3.upload_file(local_file_path, bucket, s3_key)
        logger.info("Uploaded %s to %s/%s", local_file_path, bucket, s3_key)
        return True
    except BotoClientError as e:
        logger.error("Error uploading file %s: %s", local_file_path, e)
        return False

# Download a file from storage to a local temp file
def download_to_temp(filename):
    """Downloads a file from storage to a temporary local file.

    Args:
        filename (str): The name (key) of the file to download.

    Returns:
        str | None: The path to the local temporary file, or None on failure.
    """
    s3 = _get_s3_client()
    bucket = _get_bucket()
    try:
        tmp_dir = tempfile.gettempdir()
        local_path = os.path.join(tmp_dir, os.path.basename(filename))
        s3.download_file(bucket, filename, local_path)
        logger.info("Downloaded %s to temp file %s", filename, local_path)
        return local_path
    except BotoClientError as e:
        logger.error("Error downloading file %s: %s", filename, e)
        return None
