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
        message = smtp.send_message.call_args.args[0]
        self.assertIn(test_username, str(message["From"]))
        self.assertEqual(message["Reply-To"], test_username)

    def test_gmail_sender_is_always_authenticated_account(self):
        environment = {
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "authenticated@example.invalid",
            "SMTP_PASSWORD": "x" * 16,
            "SMTP_FROM": "different@example.invalid",
            "SMTP_USE_TLS": "true",
        }
        with patch.dict(os.environ, environment, clear=False):
            status = mail_service.get_mail_status()
            with patch("services.mail_service.smtplib.SMTP") as smtp_class:
                smtp = smtp_class.return_value.__enter__.return_value
                result = mail_service.send_email(
                    "customer@example.com",
                    "Test",
                    "İçerik",
                )

        self.assertTrue(result.success)
        self.assertEqual(status["sender"], "authenticated@example.invalid")
        self.assertTrue(status["sender_matches_login"])
        message = smtp.send_message.call_args.args[0]
        self.assertIn("authenticated@example.invalid", str(message["From"]))

    def test_gmail_authentication_error_is_safe(self):
        environment = {
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "authenticated@example.invalid",
            "SMTP_PASSWORD": "x" * 16,
            "SMTP_FROM": "authenticated@example.invalid",
            "SMTP_USE_TLS": "true",
        }
        with patch.dict(os.environ, environment, clear=False):
            with patch("services.mail_service.smtplib.SMTP") as smtp_class:
                smtp = smtp_class.return_value.__enter__.return_value
                smtp.login.side_effect = mail_service.smtplib.SMTPAuthenticationError(
                    535,
                    b"Username and Password not accepted",
                )
                result = mail_service.send_email(
                    "customer@example.com",
                    "Test",
                    "İçerik",
                )

        self.assertFalse(result.success)
        self.assertIn("App Password", result.detail)
        self.assertNotIn("xxxxxxxxxxxxxxxx", result.detail)

    def test_gmail_uses_ssl_465_when_starttls_connection_fails(self):
        environment = {
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "authenticated@example.invalid",
            "SMTP_PASSWORD": "x" * 16,
            "SMTP_FROM": "authenticated@example.invalid",
            "SMTP_USE_TLS": "true",
        }
        with patch.dict(os.environ, environment, clear=False):
            with patch(
                "services.mail_service.smtplib.SMTP",
                side_effect=TimeoutError("connection timed out"),
            ):
                with patch("services.mail_service.smtplib.SMTP_SSL") as ssl_class:
                    ssl_smtp = ssl_class.return_value.__enter__.return_value
                    result = mail_service.send_email(
                        "customer@example.com",
                        "Test",
                        "İçerik",
                    )

        self.assertTrue(result.success)
        ssl_class.assert_called_once()
        self.assertEqual(ssl_class.call_args.args[:2], ("smtp.gmail.com", 465))
        ssl_smtp.login.assert_called_once_with(
            "authenticated@example.invalid",
            "x" * 16,
        )
        ssl_smtp.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
