import unittest
from unittest.mock import MagicMock, patch, mock_open
import datetime
import email_sender  # noqa: E402


class TestEmailSender(unittest.TestCase):
    def setUp(self):
        # Setup common mocks
        self.config_patcher = patch("email_sender.config.config.get")
        self.mock_config_get = self.config_patcher.start()

        # Default config values
        def side_effect(key, default=None):
            if key == ("email", "sender"):
                return "sender@example.com"
            if key == ("email", "recipients"):
                return ["recipient@example.com"]
            if key == ("email", "smtp_host"):
                return "smtp.example.com"
            if key == ("email", "smtp_port"):
                return 587
            if key == ("email", "smtp_user"):
                return "user"
            if key == ("email", "smtp_pass"):
                return "pass"
            if key == ("email", "smtp_tls"):
                return 1
            if key == ("paths", "template_dir"):
                return "templates"
            return default

        self.mock_config_get.side_effect = side_effect

    def tearDown(self):
        self.config_patcher.stop()

    def test_is_valid_email(self):
        self.assertTrue(email_sender._is_valid_email("test@example.com"))
        self.assertTrue(email_sender._is_valid_email("user.name@domain.co.uk"))
        self.assertFalse(email_sender._is_valid_email("invalid"))
        self.assertFalse(email_sender._is_valid_email("user@"))
        self.assertFalse(email_sender._is_valid_email("@domain.com"))

    def test_render_email_content_fallback(self):
        # Force _get_jinja_env to return None by mocking it
        with patch("email_sender._get_jinja_env", return_value=None):
            date = datetime.date(2023, 10, 27)
            subject, body = email_sender._render_email_content(
                date, "http://url", [], "Subject {{ date }}", "template.html"
            )
            self.assertIn("Your Daily Newspaper - 2023-10-27", subject)
            self.assertIn("http://url", body)
            self.assertIn("<html>", body)

    def test_render_email_content_jinja(self):
        # Mock Jinja2 environment returned by _get_jinja_env
        mock_env = MagicMock()
        mock_template = MagicMock()
        mock_env.get_template.return_value = mock_template
        # Subject rendering
        mock_env.from_string.return_value.render.return_value = "Rendered Subject"
        # Body rendering
        mock_template.render.return_value = "<h1>Rendered Body</h1>"

        with patch("email_sender._get_jinja_env", return_value=mock_env):
            date = datetime.date(2023, 10, 27)
            subject, body = email_sender._render_email_content(
                date, "http://url", [], "Subject {{ date }}", "template.html"
            )
            self.assertEqual(subject, "Rendered Subject")
            self.assertEqual(body, "<h1>Rendered Body</h1>")

    def test_send_email_dry_run(self):
        date = datetime.date(2023, 10, 27)
        result = email_sender.send_email(date, "http://url", [], dry_run=True)
        self.assertTrue(result)

    def test_send_email_no_recipients(self):
        self.mock_config_get.side_effect = lambda k, d=None: (
            [] if k == ("email", "recipients") else d
        )
        date = datetime.date(2023, 10, 27)
        result = email_sender.send_email(date, "http://url", [])
        self.assertFalse(result)

    @patch("smtplib.SMTP")
    def test_send_email_smtp_success(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        date = datetime.date(2023, 10, 27)
        # Mock render to return simple content
        with patch("email_sender._render_email_content", return_value=("Sub", "Body")):
            result = email_sender.send_email(date, "http://url", [])

        self.assertTrue(result)
        mock_smtp.sendmail.assert_called_once()
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user", "pass")

    @patch("smtplib.SMTP")
    def test_send_email_smtp_failure(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        mock_smtp.sendmail.side_effect = Exception("SMTP Error")

        date = datetime.date(2023, 10, 27)
        with patch("email_sender._render_email_content", return_value=("Sub", "Body")):
            result = email_sender.send_email(date, "http://url", [])

        self.assertFalse(result)

    @patch("smtplib.SMTP")
    def test_send_alert_email_success(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        result = email_sender.send_alert_email("Alert", "Message")
        self.assertTrue(result)
        mock_smtp.sendmail.assert_called_once()

    def test_send_alert_email_invalid_recipient(self):
        def side_effect(key, default=None):
            if key == ("email", "alert_recipient"):
                return "invalid"
            return default

        self.mock_config_get.side_effect = side_effect

        result = email_sender.send_alert_email("Alert", "Message")
        self.assertFalse(result)

    @patch("smtplib.SMTP")
    def test_thumbnail_local_file(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        date = datetime.date(2023, 10, 27)
        with patch("email_sender._render_email_content", return_value=("Sub", "Body")):
            with patch("os.path.isfile", return_value=True):
                # Provide a fake JPEG header so MIMEImage can guess it
                fake_jpg = (
                    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
                )
                with patch("builtins.open", mock_open(read_data=fake_jpg)):
                    result = email_sender.send_email(
                        date, "http://url", [], thumbnail_path="/path/to/thumb.jpg"
                    )

        self.assertTrue(result)
        # Verify attachment logic implicitly by success or checking call args if needed
        args, _ = mock_smtp.sendmail.call_args
        msg_str = args[2]
        self.assertIn("Content-ID: <thumbnail>", msg_str)


if __name__ == "__main__":
    unittest.main()
