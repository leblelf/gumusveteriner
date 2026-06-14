import os
import unittest
from unittest.mock import patch

from services import mail_service


class GmailSmtpServiceTests(unittest.TestCase):
    def test_gmail_smtp_uses_tls_and_app_password(self):
        test_username = "smtp-test@example.invalid"
        test_password = "x" * 16
        environment = {
            "MAIL_PROVIDER": "smtp",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": test_username,
            "SMTP_PASSWORD": test_password,
            "SMTP_FROM": test_username,
            "SMTP_USE_TLS": "true",
        }
        with patch.dict(os.environ, environment, clear=False):
            with patch("services.mail_service.smtplib.SMTP") as smtp_class:
                smtp = smtp_class.return_value.__enter__.return_value
                result = mail_service.send_email(
                    "customer@example.com",
                    "Test",
                    "Gmail SMTP test içeriği",
                )

        self.assertTrue(result.success)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with(test_username, test_password)
        smtp.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
