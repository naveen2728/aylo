import base64
import os
import tempfile
import unittest
from datetime import datetime, timezone

from aylo_app.gmail_index import GmailIndex, build_gmail_answer_prompt, build_gmail_reply_prompt, normalize_gmail_message


def encoded(text):
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8").rstrip("=")


class GmailIndexTests(unittest.TestCase):
    def test_normalizes_gmail_message(self):
        raw = {
            "id": "m1",
            "threadId": "t1",
            "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
            "snippet": "urgent invoice",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Client <client@example.com>"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Subject", "value": "Invoice approval"},
                    {"name": "Date", "value": "Mon, 01 Jun 2026 10:00:00 +0000"},
                ],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": encoded("Please approve the invoice today.")}},
                ],
            },
        }
        message = normalize_gmail_message(raw)
        self.assertEqual(message.message_id, "m1")
        self.assertTrue(message.unread)
        self.assertTrue(message.important)
        self.assertIn("approve the invoice", message.body)

    def test_indexes_and_ranks_important_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            index = GmailIndex(os.path.join(directory, "gmail.sqlite3"))
            important = normalize_gmail_message(
                {
                    "id": "important",
                    "threadId": "t1",
                    "labelIds": ["UNREAD", "IMPORTANT"],
                    "snippet": "urgent payment deadline",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Boss <boss@example.com>"},
                            {"name": "Subject", "value": "Payment deadline"},
                            {"name": "Date", "value": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")},
                        ],
                        "body": {"data": encoded("This payment approval is urgent.")},
                        "mimeType": "text/plain",
                    },
                }
            )
            casual = normalize_gmail_message(
                {
                    "id": "casual",
                    "threadId": "t2",
                    "labelIds": [],
                    "snippet": "newsletter",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "News <news@example.com>"},
                            {"name": "Subject", "value": "Weekly news"},
                            {"name": "Date", "value": "Mon, 01 Jun 2026 10:00:00 +0000"},
                        ],
                        "body": {"data": encoded("Here is the weekly digest.")},
                        "mimeType": "text/plain",
                    },
                }
            )
            index.upsert_messages([casual, important])
            results = index.search("any important mails today")
            self.assertEqual(results[0]["message_id"], "important")
            self.assertIn("unread", results[0]["reason"])
            self.assertTrue(results[0]["important"])
            self.assertEqual(results[0]["sender"], "Boss")
            casual_result = next(result for result in results if result["message_id"] == "casual")
            self.assertFalse(casual_result["important"])
            stored = index.get_message("important")
            self.assertEqual(stored.subject, "Payment deadline")

    def test_cleans_html_and_entities_for_display(self):
        message = normalize_gmail_message(
            {
                "id": "m1",
                "threadId": "t1",
                "labelIds": [],
                "snippet": "Hello&nbsp;there",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Client & Co <client@example.com>"},
                        {"name": "Subject", "value": "Project&nbsp;Update"},
                        {"name": "Date", "value": "Mon, 01 Jun 2026 10:00:00 +0000"},
                    ],
                    "parts": [
                        {"mimeType": "text/html", "body": {"data": encoded("<p>Hello&nbsp;<b>there</b></p><p>Thanks</p>")}},
                    ],
                },
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            index = GmailIndex(os.path.join(directory, "gmail.sqlite3"))
            index.upsert_messages([message])
            result = index.search("project update")[0]
        self.assertEqual(result["subject"], "Project Update")
        self.assertIn("Hello there", result["content"])
        self.assertNotIn("<b>", result["content"])

    def test_prompt_uses_only_supplied_snippets(self):
        prompt = build_gmail_answer_prompt(
            "Any important mails?",
            [{"sender": "A", "subject": "S", "date": "D", "reason": "urgent", "content": "Body", "score": 1}],
        )
        self.assertIn("USER QUESTION: Any important mails?", prompt)
        self.assertIn("Sender: A", prompt)
        self.assertIn("Do not invent", prompt)

    def test_reply_prompt_uses_email_context(self):
        message = normalize_gmail_message(
            {
                "id": "m1",
                "threadId": "t1",
                "snippet": "hello",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Client <client@example.com>"},
                        {"name": "Subject", "value": "Project update"},
                    ],
                    "body": {"data": encoded("Can you check the project today?")},
                    "mimeType": "text/plain",
                },
            }
        )
        prompt = build_gmail_reply_prompt("Say I will check today", message)
        self.assertIn("USER INSTRUCTION: Say I will check today", prompt)
        self.assertIn("Project update", prompt)
        self.assertIn("Return only the reply body", prompt)


if __name__ == "__main__":
    unittest.main()
