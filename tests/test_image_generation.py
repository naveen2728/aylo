import unittest

from aylo_app.image_generation import image_prompt_from_request, is_image_generation_request


class ImageGenerationTests(unittest.TestCase):
    def test_detects_image_generation_request(self):
        self.assertTrue(is_image_generation_request("generate a picture of a cyberpunk city"))
        self.assertTrue(is_image_generation_request("make an image for my app logo"))

    def test_ignores_regular_chat(self):
        self.assertFalse(is_image_generation_request("what is on my screen"))

    def test_extracts_prompt_from_request(self):
        self.assertEqual(
            image_prompt_from_request("generate a picture of a cyberpunk city"),
            "a cyberpunk city",
        )


if __name__ == "__main__":
    unittest.main()
