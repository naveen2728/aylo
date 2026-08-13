import base64
import json
import unittest
from unittest.mock import Mock

from aylo_app.conversation_agent import ConversationAgent


class DummyWebSocket:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(json.loads(payload))


class ConversationAgentTests(unittest.TestCase):
    def test_audio_is_queued_for_playback(self):
        on_event = Mock()
        agent = ConversationAgent("key", Mock(), on_event)
        audio = b"\x01\x02\x03\x04"

        agent._on_message(
            None,
            json.dumps(
                {
                    "type": "response.output_audio.delta",
                    "delta": base64.b64encode(audio).decode("ascii"),
                }
            ),
        )

        self.assertEqual(agent.output_queue.get_nowait(), audio)

    def test_transcript_events_include_role_and_final_state(self):
        on_event = Mock()
        agent = ConversationAgent("key", Mock(), on_event)

        agent._on_message(
            None,
            json.dumps(
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "transcript": "Hello there",
                }
            ),
        )
        agent._on_message(
            None,
            json.dumps(
                {
                    "type": "response.output_audio_transcript.delta",
                    "delta": "Hi!",
                }
            ),
        )

        self.assertIn(
            unittest.mock.call(
                "transcript",
                {"role": "user", "text": "Hello there", "final": True},
            ),
            on_event.call_args_list,
        )
        self.assertIn(
            unittest.mock.call(
                "transcript",
                {"role": "assistant", "text": "Hi!", "final": False},
            ),
            on_event.call_args_list,
        )

    def test_speech_interrupts_assistant_output(self):
        on_event = Mock()
        agent = ConversationAgent("key", Mock(), on_event)
        agent.ws = DummyWebSocket()
        agent.output_queue.put(b"old response")

        agent._on_message(None, json.dumps({"type": "input_audio_buffer.speech_started"}))

        self.assertTrue(agent.output_queue.empty())
        self.assertEqual(agent.ws.sent, [{"type": "response.cancel"}])
        on_event.assert_any_call("speech_started", None)

    def test_mute_state_is_reported(self):
        on_event = Mock()
        agent = ConversationAgent("key", Mock(), on_event)

        agent.set_muted(True)
        self.assertTrue(agent.muted.is_set())
        on_event.assert_called_with("muted", True)


if __name__ == "__main__":
    unittest.main()
