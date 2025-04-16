import unittest
import email_sender
from datetime import date

class TestEmailSender(unittest.TestCase):
    def test_send_email_dry_run(self):
        result = email_sender.send_email(
            target_date=date.today(),
            today_paper_url='http://example.com/paper.pdf',
            past_papers=[],
            thumbnail_path=None,
            dry_run=True
        )
        self.assertTrue(result)

if __name__ == "__main__":
    unittest.main()
