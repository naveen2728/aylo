import json
import os
import tempfile
import unittest
from unittest.mock import patch

from voiceflow_app import config
from voiceflow_app.config import AppSettings, load_settings


class ConfigTests(unittest.TestCase):
    def test_creates_default_settings_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            settings = load_settings(path)
            self.assertEqual(settings, AppSettings())
            self.assertTrue(settings.mouse_side_button_mic)
            self.assertEqual(settings.mouse_forward_action, "command")
            self.assertFalse(settings.ai_features_enabled)
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            self.assertEqual(stored["samplerate"], 16000)
            self.assertTrue(stored["mouse_side_button_mic"])
            self.assertEqual(stored["mouse_forward_action"], "command")
            self.assertFalse(stored["ai_features_enabled"])

    def test_preserves_valid_values_and_ignores_unknown_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"mic_device": 3, "max_record_seconds": 45, "mouse_forward_action": "command", "unknown": True}, handle)
            settings = load_settings(path)
            self.assertEqual(settings.mic_device, 3)
            self.assertEqual(settings.max_record_seconds, 45)
            self.assertEqual(settings.mouse_forward_action, "command")
            with open(path, "r", encoding="utf-8") as handle:
                self.assertNotIn("unknown", json.load(handle))

    def test_invalid_values_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "samplerate": -1,
                        "silence_rms_threshold": "loud",
                        "first_run_complete": "yes",
                        "mouse_side_button_mic": "yes",
                        "mouse_forward_action": "bad-action",
                        "ai_features_enabled": "yes",
                    },
                    handle,
                )
            settings = load_settings(path)
            self.assertEqual(settings.samplerate, AppSettings().samplerate)
            self.assertEqual(settings.silence_rms_threshold, AppSettings().silence_rms_threshold)
            self.assertEqual(settings.first_run_complete, AppSettings().first_run_complete)
            self.assertEqual(settings.mouse_side_button_mic, AppSettings().mouse_side_button_mic)
            self.assertEqual(settings.mouse_forward_action, AppSettings().mouse_forward_action)
            self.assertEqual(settings.ai_features_enabled, AppSettings().ai_features_enabled)

    def test_migrates_legacy_normal_sensitivity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"silence_rms_threshold": 0.002}, handle)
            settings = load_settings(path)
            self.assertEqual(settings.silence_rms_threshold, AppSettings().silence_rms_threshold)

    def test_migrates_previous_quiet_microphone_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"silence_rms_threshold": 0.00005}, handle)
            settings = load_settings(path)
            self.assertEqual(settings.silence_rms_threshold, AppSettings().silence_rms_threshold)

    def test_load_api_key_uses_existing_environment_value(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "from-environment"}, clear=False), patch("voiceflow_app.config._read_credential") as read:
            self.assertEqual(config.load_api_key(), "from-environment")
        read.assert_not_called()

    def test_load_api_key_migrates_legacy_plain_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.env")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("GROQ_API_KEY=legacy-secret\n")
            with patch.dict(os.environ, {}, clear=True), patch("voiceflow_app.config._read_credential", return_value=None), patch("voiceflow_app.config._write_credential") as write:
                self.assertEqual(config.load_api_key(path), "legacy-secret")
                self.assertEqual(os.environ["GROQ_API_KEY"], "legacy-secret")
            write.assert_called_once_with("legacy-secret")
            self.assertFalse(os.path.exists(path))

    def test_save_api_key_uses_credential_manager_and_removes_legacy_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.env")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("GROQ_API_KEY=old-secret\n")
            with patch.dict(os.environ, {}, clear=True), patch("voiceflow_app.config._write_credential") as write:
                config.save_api_key("new-secret", path)
                self.assertEqual(os.environ["GROQ_API_KEY"], "new-secret")
            write.assert_called_once_with("new-secret")
            self.assertFalse(os.path.exists(path))

    def test_write_credential_uses_windows_credential_manager(self):
        with patch("win32cred.CredWrite") as cred_write:
            config._write_credential("secret")
        credential, flags = cred_write.call_args.args
        self.assertEqual(flags, 0)
        self.assertEqual(credential["TargetName"], config.CREDENTIAL_TARGET)
        self.assertEqual(credential["CredentialBlob"], "secret")

    def test_missing_windows_credential_is_treated_as_not_configured(self):
        missing = RuntimeError("Element not found.")
        missing.winerror = 1168
        with patch("win32cred.CredRead", side_effect=missing):
            self.assertIsNone(config._read_credential())


if __name__ == "__main__":
    unittest.main()
