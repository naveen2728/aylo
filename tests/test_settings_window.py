import unittest

from aylo_app.settings_window import sensitivity_label


class SettingsWindowTests(unittest.TestCase):
    def test_uses_nearest_sensitivity_label(self):
        self.assertEqual(sensitivity_label(0.0002), "High - quieter speech")
        self.assertEqual(sensitivity_label(0.0008), "Normal")
        self.assertEqual(sensitivity_label(0.002), "Low - noisy rooms")


if __name__ == "__main__":
    unittest.main()
