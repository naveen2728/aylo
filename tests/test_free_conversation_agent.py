import unittest
from unittest.mock import Mock

from aylo_app.free_conversation_agent import FreeConversationAgent


class FreeConversationAgentTests(unittest.TestCase):
    def test_one_turn_transcribes_replies_speaks_and_keeps_context(self):
        events = Mock()
        spoken = []
        agent = None

        def speak(text):
            spoken.append(text)
            agent.stop()

        agent = FreeConversationAgent(
            record_turn=lambda _stop, _muted: [b"audio"],
            transcribe=lambda _frames: "How are you?",
            generate_reply=lambda messages: f"Reply to: {messages[-1]['content']}",
            speak=speak,
            log_error=Mock(),
            on_event=events,
        )

        agent._run()

        self.assertEqual(spoken, ["Reply to: How are you?"])
        self.assertEqual(
            agent.messages,
            [
                {"role": "user", "content": "How are you?"},
                {"role": "assistant", "content": "Reply to: How are you?"},
            ],
        )
        events.assert_any_call(
            "transcript",
            {"role": "user", "text": "How are you?", "final": True},
        )
        events.assert_any_call(
            "transcript",
            {"role": "assistant", "text": "Reply to: How are you?", "final": True},
        )

    def test_mute_sets_shared_recording_signal(self):
        events = Mock()
        agent = FreeConversationAgent(Mock(), Mock(), Mock(), Mock(), Mock(), events)

        agent.set_muted(True)

        self.assertTrue(agent.muted.is_set())
        events.assert_called_with("muted", True)


if __name__ == "__main__":
    unittest.main()
