
import unittest
import os
import shutil
import tempfile
import sys
from unittest.mock import MagicMock, patch
import logging

# Ensure the module is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import storage
import config

class TestStorageLocal(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for local storage testing
        self.test_dir = tempfile.mkdtemp()
        self.local_storage_path = os.path.join(self.test_dir, "storage_data")
        os.makedirs(self.local_storage_path, exist_ok=True)

        # Patch config to use local storage
        self.config_patcher = patch('storage.config.config.get')
        self.mock_config_get = self.config_patcher.start()

        def config_side_effect(key, default=None):
            if key == ('storage', 'type'):
                return 'local'
            if key == ('storage', 'local_path'):
                return self.local_storage_path
            if key == ('storage', 'public_base_url'):
                return 'http://localhost:8000/files'
            return default

        self.mock_config_get.side_effect = config_side_effect

    def tearDown(self):
        self.config_patcher.stop()
        shutil.rmtree(self.test_dir)

    def test_upload_local(self):
        # Create a dummy file to upload
        src_file = os.path.join(self.test_dir, "test_upload.txt")
        with open(src_file, "w") as f:
            f.write("content")

        success = storage.upload_to_storage(src_file, "uploaded.txt")
        self.assertTrue(success)
        self.assertTrue(os.path.exists(os.path.join(self.local_storage_path, "uploaded.txt")))

    def test_upload_local_dry_run(self):
        src_file = os.path.join(self.test_dir, "test_dry.txt")
        with open(src_file, "w") as f:
            f.write("content")

        success = storage.upload_to_storage(src_file, "dry_uploaded.txt", dry_run=True)
        self.assertTrue(success)
        self.assertFalse(os.path.exists(os.path.join(self.local_storage_path, "dry_uploaded.txt")))

    def test_list_files_local(self):
        # Create some files
        with open(os.path.join(self.local_storage_path, "file1.txt"), "w") as f: f.write("1")
        with open(os.path.join(self.local_storage_path, "file2.txt"), "w") as f: f.write("2")

        files = storage.list_storage_files()
        self.assertIn("file1.txt", files)
        self.assertIn("file2.txt", files)
        self.assertEqual(len(files), 2)

    def test_delete_local(self):
        target = os.path.join(self.local_storage_path, "to_delete.txt")
        with open(target, "w") as f: f.write("bye")

        success = storage.delete_from_storage("to_delete.txt")
        self.assertTrue(success)
        self.assertFalse(os.path.exists(target))

    def test_get_url_local(self):
        url = storage.get_file_url("doc.pdf")
        self.assertEqual(url, "http://localhost:8000/files/doc.pdf")

    def test_download_local(self):
        target = os.path.join(self.local_storage_path, "download_me.txt")
        with open(target, "w") as f: f.write("download content")

        local_path = storage.download_to_temp("download_me.txt")
        self.assertTrue(os.path.exists(local_path))
        with open(local_path, "r") as f:
            self.assertEqual(f.read(), "download content")


class TestStorageS3(unittest.TestCase):
    def setUp(self):
        self.config_patcher = patch('storage.config.config.get')
        self.mock_config_get = self.config_patcher.start()

        def config_side_effect(key, default=None):
            if key == ('storage', 'type'):
                return 's3'
            if key == ('storage', 'bucket'):
                return 'my-bucket'
            return default
        self.mock_config_get.side_effect = config_side_effect

        self.boto3_patcher = patch('storage.boto3')
        self.mock_boto3 = self.boto3_patcher.start()
        self.mock_s3_client = MagicMock()
        self.mock_boto3.client.return_value = self.mock_s3_client

        # Ensure storage sees boto3 as not None
        # (This is already handled by patching storage.boto3, assuming it imported it)
        # Note: In storage.py:
        # try: import boto3 ... except: boto3 = None
        # Patching 'storage.boto3' should work if we do it before the test runs functionality.

    def tearDown(self):
        self.config_patcher.stop()
        self.boto3_patcher.stop()

    def test_upload_s3(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"data")
            tmp_name = tmp.name

        try:
            success = storage.upload_to_storage(tmp_name, "remote_key")
            self.assertTrue(success)
            self.mock_s3_client.upload_file.assert_called_with(tmp_name, 'my-bucket', 'remote_key')
        finally:
            os.remove(tmp_name)

    def test_upload_s3_dry_run(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"data")
            tmp_name = tmp.name

        try:
            success = storage.upload_to_storage(tmp_name, "remote_key", dry_run=True)
            self.assertTrue(success)
            self.mock_s3_client.upload_file.assert_not_called()
        finally:
            os.remove(tmp_name)

    def test_list_files_s3(self):
        self.mock_s3_client.list_objects_v2.return_value = {
            'Contents': [{'Key': 'fileA'}, {'Key': 'fileB'}]
        }
        files = storage.list_storage_files()
        self.assertEqual(files, ['fileA', 'fileB'])

    def test_delete_s3(self):
        success = storage.delete_from_storage("fileX")
        self.assertTrue(success)
        self.mock_s3_client.delete_object.assert_called_with(Bucket='my-bucket', Key='fileX')

    def test_get_url_s3(self):
        self.mock_s3_client.generate_presigned_url.return_value = "http://s3/url"
        url = storage.get_file_url("fileY")
        self.assertEqual(url, "http://s3/url")
        self.mock_s3_client.generate_presigned_url.assert_called()

    def test_download_s3(self):
        path = storage.download_to_temp("remote_file")
        self.assertTrue(path)
        self.mock_s3_client.download_file.assert_called()


if __name__ == '__main__':
    unittest.main()
