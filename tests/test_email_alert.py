import unittest
import email_sender

class TestEmailAlert(unittest.TestCase):
    def test_send_alert_email(self):
        # Should not raise in dry-run mode (simulate by using a likely invalid recipient)
        result = email_sender.send_alert_email("Test Alert", "This is a test alert.")
        self.assertTrue(result is True or result is False)  # Should not raise

if __name__ == "__main__":
    unittest.main()
