import unittest
import main
from datetime import date

class TestMainPipeline(unittest.TestCase):
    def test_main_dry_run(self):
        result = main.main(target_date_str=date.today().strftime('%Y-%m-%d'), dry_run=True, force_download=False)
        self.assertTrue(result)

if __name__ == "__main__":
    unittest.main()
