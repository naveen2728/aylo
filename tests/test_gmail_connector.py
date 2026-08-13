import unittest
from unittest.mock import Mock, patch

from aylo_app.gmail_connector import create_gmail_draft, gmail_status, send_gmail_message, sender_email, sync_gmail_knowledge, sync_recent_gmail


class GmailConnectorTests(unittest.TestCase):
    def test_status_reports_connection_and_index_count(self):
        index = Mock()
        index.count_messages.return_value = 3
        index.latest_sync.return_value = "2026-06-01T10:00:00+00:00"
        with patch("aylo_app.gmail_connector.is_connected", return_value=True):
            status = gmail_status(index)
        self.assertIn("connected", status)
        self.assertIn("3 messages", status)

    def test_sync_recent_gmail_indexes_messages(self):
        service = Mock()
        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {"messages": [{"id": "m1"}]}
        service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "id": "m1",
            "threadId": "t1",
            "labelIds": ["INBOX"],
            "snippet": "hello",
            "payload": {"headers": [{"name": "Subject", "value": "Hello"}]},
        }
        index = Mock()
        with patch("aylo_app.gmail_connector.get_credentials", return_value=object()), patch("aylo_app.gmail_connector._build_service", return_value=service):
            count = sync_recent_gmail(index=index)
        self.assertEqual(count, 1)
        index.upsert_messages.assert_called_once()

    def test_sync_gmail_knowledge_dedupes_multiple_queries(self):
        service = Mock()
        service.users.return_value.messages.return_value.list.return_value.execute.side_effect = [
            {"messages": [{"id": "m1"}, {"id": "m2"}]},
            {"messages": [{"id": "m1"}]},
        ]
        service.users.return_value.messages.return_value.get.return_value.execute.side_effect = [
            {
                "id": "m1",
                "threadId": "t1",
                "labelIds": ["IMPORTANT"],
                "snippet": "important",
                "payload": {"headers": [{"name": "Subject", "value": "Important"}]},
            },
            {
                "id": "m2",
                "threadId": "t2",
                "labelIds": ["STARRED"],
                "snippet": "starred",
                "payload": {"headers": [{"name": "Subject", "value": "Starred"}]},
            },
        ]
        index = Mock()
        queries = [("important", "is:important", 10), ("starred", "is:starred", 10)]
        with patch("aylo_app.gmail_connector.get_credentials", return_value=object()), patch("aylo_app.gmail_connector._build_service", return_value=service):
            count = sync_gmail_knowledge(index=index, queries=queries)
        self.assertEqual(count, 2)
        indexed_messages = [
            message
            for call_args in index.upsert_messages.call_args_list
            for message in call_args.args[0]
        ]
        self.assertEqual({message.message_id for message in indexed_messages}, {"m1", "m2"})

    def test_sender_email_extracts_address(self):
        self.assertEqual(sender_email("Client <client@example.com>"), "client@example.com")

    def test_create_gmail_draft_calls_gmail_api(self):
        service = Mock()
        service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {"id": "draft-1"}
        with patch("aylo_app.gmail_connector.get_credentials", return_value=object()), patch("aylo_app.gmail_connector._build_service", return_value=service):
            draft_id = create_gmail_draft("client@example.com", "Hello", "Draft body", thread_id="thread-1")
        self.assertEqual(draft_id, "draft-1")
        body = service.users.return_value.drafts.return_value.create.call_args.kwargs["body"]
        self.assertEqual(body["message"]["threadId"], "thread-1")
        self.assertIn("raw", body["message"])

    def test_send_gmail_message_calls_gmail_api(self):
        service = Mock()
        service.users.return_value.messages.return_value.send.return_value.execute.return_value = {"id": "sent-1"}
        with patch("aylo_app.gmail_connector.get_credentials", return_value=object()), patch("aylo_app.gmail_connector._build_service", return_value=service):
            sent_id = send_gmail_message("client@example.com", "Hello", "Reply body", thread_id="thread-1")
        self.assertEqual(sent_id, "sent-1")
        body = service.users.return_value.messages.return_value.send.call_args.kwargs["body"]
        self.assertEqual(body["threadId"], "thread-1")
        self.assertIn("raw", body)


if __name__ == "__main__":
    unittest.main()
