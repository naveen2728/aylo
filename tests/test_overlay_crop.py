import unittest
from unittest.mock import Mock, patch

from PIL import Image

from aylo_app.overlay import copy_image_to_clipboard, looks_like_screen_question, render_screenshot_annotations, scaled_crop_box, screenshot_editor_preview_limits


class OverlayCropTests(unittest.TestCase):
    def test_scaled_crop_box_maps_preview_selection_to_original_image(self):
        self.assertEqual(
            scaled_crop_box(20, 30, 120, 90, 0.5, 400, 300),
            (40, 60, 240, 180),
        )

    def test_scaled_crop_box_rejects_tiny_selection(self):
        self.assertIsNone(scaled_crop_box(10, 10, 12, 12, 1.0, 400, 300))

    def test_screenshot_editor_uses_a_large_preview(self):
        self.assertEqual(screenshot_editor_preview_limits(1920, 1080), (1280, 720))
        self.assertEqual(screenshot_editor_preview_limits(1366, 768), (1280, 528))

    def test_detects_short_screen_follow_up_questions(self):
        self.assertTrue(looks_like_screen_question("what is it"))
        self.assertTrue(looks_like_screen_question("explain this"))
        self.assertTrue(looks_like_screen_question("what is on this screen?"))
        self.assertFalse(looks_like_screen_question("write an email to Rahul"))

    def test_regular_follow_up_can_use_active_screen_context(self):
        self.assertFalse(looks_like_screen_question("what do you think"))

    def test_renders_shapes_after_cropping_and_repositions_them(self):
        image = Image.new("RGB", (200, 120), "white")
        annotations = [
            {
                "kind": "rectangle",
                "x1": 50,
                "y1": 30,
                "x2": 150,
                "y2": 90,
                "color": "#ef4444",
                "width": 5,
            }
        ]
        result = render_screenshot_annotations(image, annotations, (40, 20, 170, 100))
        self.assertEqual(result.size, (130, 80))
        self.assertEqual(result.getpixel((10, 10)), (239, 68, 68))

    def test_renders_blue_text_note(self):
        image = Image.new("RGB", (240, 100), "black")
        result = render_screenshot_annotations(
            image,
            [{"kind": "text", "x1": 20, "y1": 20, "text": "Check this", "color": "#2563eb", "font_size": 20}],
        )
        self.assertIsNotNone(result.crop((15, 15, 160, 65)).getbbox())

    def test_renders_thin_red_arrow(self):
        image = Image.new("RGB", (220, 120), "white")
        result = render_screenshot_annotations(
            image,
            [{"kind": "arrow", "x1": 20, "y1": 60, "x2": 180, "y2": 60, "color": "#ef4444", "width": 2}],
        )
        self.assertEqual(result.getpixel((100, 60)), (239, 68, 68))
        self.assertEqual(result.getpixel((180, 60)), (239, 68, 68))
        self.assertEqual(result.getpixel((100, 63)), (255, 255, 255))

    def test_copies_image_as_windows_dib(self):
        clipboard = Mock()
        clipboard.CF_DIB = 8
        with patch.dict("sys.modules", {"win32clipboard": clipboard}):
            copy_image_to_clipboard(Image.new("RGB", (10, 10), "blue"))
        clipboard.OpenClipboard.assert_called_once_with()
        clipboard.EmptyClipboard.assert_called_once_with()
        clipboard.SetClipboardData.assert_called_once()
        self.assertEqual(clipboard.SetClipboardData.call_args.args[0], 8)
        clipboard.CloseClipboard.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
