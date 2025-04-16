import unittest
import storage

class TestStorage(unittest.TestCase):
    def test_list_files(self):
        try:
            files = storage.list_storage_files()
            self.assertIsInstance(files, list)
        except Exception as e:
            self.fail(f"list_storage_files raised: {e}")

    def test_get_file_url(self):
        # This test assumes at least one file exists in storage
        files = storage.list_storage_files()
        if files:
            url = storage.get_file_url(files[0])
            self.assertTrue(url.startswith('http'))

if __name__ == "__main__":
    unittest.main()
