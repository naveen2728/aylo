import unittest

from aylo_app.clipboard_utils import ClipboardContentError, line_count, validate_clipboard_content


class ClipboardUtilsTests(unittest.TestCase):
    def test_counts_lines(self):
        self.assertEqual(line_count(""), 0)
        self.assertEqual(line_count("one"), 1)
        self.assertEqual(line_count("one\ntwo"), 2)

    def test_allows_exactly_100_lines(self):
        content = "\n".join(f"line {number}" for number in range(100))
        self.assertEqual(validate_clipboard_content(content), content)

    def test_rejects_more_than_100_lines(self):
        content = "\n".join(f"line {number}" for number in range(101))
        with self.assertRaisesRegex(ClipboardContentError, "101 lines"):
            validate_clipboard_content(content)


if __name__ == "__main__":
    unittest.main()
