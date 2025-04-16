import unittest
import storage

class TestStorageDryRun(unittest.TestCase):
    def test_upload_dry_run(self):
        # Should not raise or actually upload
        result = storage.upload_to_storage("fakefile.txt", "fakefile.txt", dry_run=True)
        self.assertTrue(result)

    def test_delete_dry_run(self):
        # Should not raise or actually delete
        result = storage.delete_from_storage("fakefile.txt", dry_run=True)
        self.assertTrue(result)

if __name__ == "__main__":
    unittest.main()
