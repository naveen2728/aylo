import json
import unittest
from unittest.mock import patch

from aylo_app import gmail_auth


class GmailAuthTests(unittest.TestCase):
    def test_load_token_reads_credential_json(self):
        with patch("aylo_app.gmail_auth._migrate_credential", return_value='{"token": "abc"}'):
            self.assertEqual(gmail_auth.load_token(), {"token": "abc"})

    def test_load_token_ignores_invalid_json(self):
        with patch("aylo_app.gmail_auth._migrate_credential", return_value="{broken"):
            self.assertIsNone(gmail_auth.load_token())

    def test_save_token_writes_json_to_credential_manager(self):
        with patch("aylo_app.gmail_auth.write_credential") as write:
            gmail_auth.save_token({"token": "abc"})
        target, value = write.call_args.args
        self.assertEqual(target, gmail_auth.GMAIL_TOKEN_TARGET)
        self.assertEqual(json.loads(value), {"token": "abc"})

    def test_delete_token_deletes_credential(self):
        with patch("aylo_app.gmail_auth.delete_credential") as delete:
            gmail_auth.delete_token()
        delete.assert_called_once_with(gmail_auth.GMAIL_TOKEN_TARGET)

    def test_scopes_include_read_and_compose(self):
        self.assertIn("https://www.googleapis.com/auth/gmail.readonly", gmail_auth.SCOPES)
        self.assertIn("https://www.googleapis.com/auth/gmail.compose", gmail_auth.SCOPES)
        self.assertIn("https://www.googleapis.com/auth/gmail.send", gmail_auth.SCOPES)

    def test_is_connected_requires_all_scopes(self):
        with patch("aylo_app.gmail_auth.load_token", return_value={"scopes": ["https://www.googleapis.com/auth/gmail.readonly"]}):
            self.assertFalse(gmail_auth.is_connected())
        with patch("aylo_app.gmail_auth.load_token", return_value={"scopes": gmail_auth.SCOPES}):
            self.assertTrue(gmail_auth.is_connected())


if __name__ == "__main__":
    unittest.main()
