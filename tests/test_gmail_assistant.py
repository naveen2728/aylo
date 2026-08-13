import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from aylo_app.gmail_assistant import answer_gmail_question, is_gmail_question, is_open_gmail_command
from aylo_app.gmail_index import GmailIndex, GmailMessage


class GmailAssistantTests(unittest.TestCase):
    def test_detects_gmail_questions(self):
        self.assertTrue(is_gmail_question("Any important mails today?"))
        self.assertTrue(is_gmail_question("Find emails from Rahul about the app"))
        self.assertFalse(is_gmail_question("Write an email asking for leave"))

    def test_detects_open_gmail_command(self):
        self.assertTrue(is_open_gmail_command("open gmail"))
        self.assertTrue(is_open_gmail_command("open my inbox"))
        self.assertTrue(is_open_gmail_command("open the gmail"))
        self.assertTrue(is_open_gmail_command("open Gmail."))
        self.assertTrue(is_open_gmail_command("open g mail"))
        self.assertTrue(is_open_gmail_command("open gee mail"))
        self.assertTrue(is_open_gmail_command("show my emails"))
        self.assertTrue(is_open_gmail_command("display mail"))
        self.assertFalse(is_open_gmail_command("open important gmail messages"))

    def test_answers_without_ai_using_local_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            index = GmailIndex(os.path.join(directory, "gmail.sqlite3"))
            index.upsert_messages(
                [
                    GmailMessage(
                        message_id="m1",
                        thread_id="t1",
                        sender="Client <client@example.com>",
                        recipients="me@example.com",
                        subject="Urgent approval",
                        date="2026-06-01T10:00:00+00:00",
                        snippet="approval needed",
                        body="Please approve this today.",
                        labels=("UNREAD",),
                        unread=True,
                        starred=False,
                        important=False,
                    )
                ]
            )
            answer = answer_gmail_question("Any important mails?", index=index)
            self.assertIn("Important Gmail messages", answer)
            self.assertIn("Urgent approval", answer)

    def test_uses_ai_when_client_is_available(self):
        with tempfile.TemporaryDirectory() as directory:
            index = GmailIndex(os.path.join(directory, "gmail.sqlite3"))
            index.upsert_messages(
                [
                    GmailMessage(
                        message_id="m1",
                        thread_id="t1",
                        sender="Client",
                        recipients="Me",
                        subject="Invoice",
                        date="2026-06-01T10:00:00+00:00",
                        snippet="invoice",
                        body="Invoice payment due.",
                        labels=("IMPORTANT",),
                        unread=False,
                        starred=False,
                        important=True,
                    )
                ]
            )
            with patch("aylo_app.ai_client.generate", return_value="AI summary") as generate:
                answer = answer_gmail_question("Any important emails?", ai_client=Mock(), index=index)
            self.assertEqual(answer, "AI summary")
            self.assertIn("EMAIL SNIPPETS", generate.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
