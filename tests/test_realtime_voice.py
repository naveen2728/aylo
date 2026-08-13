import base64
import json
import unittest
from unittest.mock import Mock

from aylo_app.realtime_voice import RealtimeVoiceAgent


class DummyWebSocket:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(json.loads(payload))


class RealtimeVoiceAgentTests(unittest.TestCase):
    def test_audio_delta_is_queued_for_playback(self):
        agent = RealtimeVoiceAgent("key", Mock())
        audio = b"\x01\x02\x03\x04"
        agent._on_message(None, json.dumps({"type": "response.output_audio.delta", "delta": base64.b64encode(audio).decode("ascii")}))
        self.assertEqual(agent.output_queue.get_nowait(), audio)

    def test_user_speech_interrupt_clears_audio_and_cancels_response(self):
        agent = RealtimeVoiceAgent("key", Mock())
        agent.ws = DummyWebSocket()
        agent.output_queue.put(b"old audio")

        agent._on_message(None, json.dumps({"type": "input_audio_buffer.speech_started"}))

        self.assertTrue(agent.output_queue.empty())
        self.assertEqual(agent.ws.sent, [{"type": "response.cancel"}])


if __name__ == "__main__":
    unittest.main()
