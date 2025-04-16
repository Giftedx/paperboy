#!/usr/bin/env python3
"""
Storage interaction module
Handles uploading and deleting files from cloud storage (AWS S3 or compatible like Cloudflare R2).
Also manages local file cleanup.
"""

import os
import tempfile
import logging
import boto3
from botocore.exceptions import ClientError as BotoClientError
import config

logger = logging.getLogger(__name__)

# Custom exception for storage errors
class ClientError(Exception):
    pass

# Lazy S3 client initialization
def _get_s3_client():
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

# List all files in the storage bucket
def list_storage_files():
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