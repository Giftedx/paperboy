#!/usr/bin/env python3
"""
Storage interaction module
Handles uploading and deleting files from cloud storage (AWS S3 or compatible like Cloudflare R2).
Also manages local file cleanup and local storage backend.
"""

import os
import shutil
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
        pass

import config

logger = logging.getLogger(__name__)

# Custom exception for storage errors
class ClientError(Exception):
    pass

# Lazy S3 client initialization
def _get_s3_client():
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
    return config.config.get(('storage', 'bucket'))

def _get_storage_type():
    return config.config.get(('storage', 'type'), 's3').lower()

def _get_local_storage_path():
    # Use 'storage_data' as default local storage directory
    path = config.config.get(('storage', 'local_path'), 'storage_data')
    os.makedirs(path, exist_ok=True)
    return path

# List all files in the storage bucket
def list_storage_files():
    stype = _get_storage_type()
    if stype == 'local':
        local_path = _get_local_storage_path()
        try:
            files = [f for f in os.listdir(local_path) if os.path.isfile(os.path.join(local_path, f))]
            logger.info("Listed %d files in local storage %s", len(files), local_path)
            return files
        except OSError as e:
            logger.error("Error listing files in local storage: %s", e)
            return []

    # S3 Fallback
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
    stype = _get_storage_type()
    if stype == 'local':
        # Return a public URL if configured, otherwise None.
        # This is crucial for emails. If local, the user must provide a way to reach it (e.g., Nginx, or just a file path if internal).
        public_base = config.config.get(('storage', 'public_base_url'))
        if public_base:
            return f"{public_base.rstrip('/')}/{filename}"
        # If no public base is set, we can't give a URL.
        logger.warning("Local storage used but 'storage.public_base_url' not set. No URL generated for %s", filename)
        return None

    # S3 Fallback
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
    stype = _get_storage_type()
    if stype == 'local':
        local_path = _get_local_storage_path()
        target = os.path.join(local_path, filename)
        if dry_run:
            logger.info("[Dry Run] Would delete %s", target)
            return True
        try:
            if os.path.exists(target):
                os.remove(target)
                logger.info("Deleted local file %s", target)
                return True
            return False
        except OSError as e:
            logger.error("Error deleting local file %s: %s", target, e)
            return False

    # S3 Fallback
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
    if not os.path.isfile(local_file_path):
        logger.error("File to upload does not exist: %s", local_file_path)
        return False

    stype = _get_storage_type()
    if stype == 'local':
        dest_dir = _get_local_storage_path()
        dest_path = os.path.join(dest_dir, s3_key)

        # Ensure parent directory exists for nested keys
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        except OSError as e:
            logger.error("Error creating directory for local storage: %s", e)
            return False

        if dry_run:
            logger.info("[Dry Run] Would copy %s to %s", local_file_path, dest_path)
            return True
        try:
            shutil.copy2(local_file_path, dest_path)
            logger.info("Copied %s to local storage %s", local_file_path, dest_path)
            return True
        except OSError as e:
            logger.error("Error copying file to local storage: %s", e)
            return False

    # S3 Fallback
    s3 = _get_s3_client()
    bucket = _get_bucket()
    if dry_run:
        logger.info("[Dry Run] Would upload %s to %s/%s", local_file_path, bucket, s3_key)
        return True
    try:
        s3.upload_file(local_file_path, bucket, s3_key)
        logger.info("Uploaded %s to %s/%s", local_file_path, bucket, s3_key)
        return True
    except BotoClientError as e:
        logger.error("Error uploading file %s: %s", local_file_path, e)
        return False

# Download a file from storage to a local temp file
def download_to_temp(filename):
    stype = _get_storage_type()
    if stype == 'local':
        src_dir = _get_local_storage_path()
        src_path = os.path.join(src_dir, filename)
        if not os.path.exists(src_path):
            logger.error("File not found in local storage: %s", src_path)
            return None
        try:
            tmp_dir = tempfile.gettempdir()
            local_path = os.path.join(tmp_dir, os.path.basename(filename))
            shutil.copy2(src_path, local_path)
            logger.info("Copied %s to temp file %s", src_path, local_path)
            return local_path
        except OSError as e:
            logger.error("Error copying from local storage: %s", e)
            return None

    # S3 Fallback
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
