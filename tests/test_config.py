import unittest
import config

class TestConfig(unittest.TestCase):
    def test_load(self):
        self.assertTrue(config.config.load())
        self.assertIsNotNone(config.config.get(('newspaper', 'url')))

if __name__ == "__main__":
    unittest.main()
