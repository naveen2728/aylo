import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import release


class ReleaseTests(unittest.TestCase):
    def test_sha256_is_uppercase(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"Aylo")
            self.assertEqual(
                release.sha256(path),
                "FA158A4D5EF1E32017E5537FAA20F32D1BB293F9CDD3FD5BF3A37482490F3E39",
            )

    def test_find_inno_setup_uses_configured_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ISCC.exe"
            path.write_bytes(b"")
            with patch.dict(os.environ, {"AYLO_ISCC": str(path)}, clear=False), patch("release.shutil.which", return_value=None):
                self.assertEqual(release.find_inno_setup(), str(path))

    def test_sign_is_optional_without_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(release.sign(Path("Aylo.exe")))

    def test_find_inno_setup_supports_user_local_install(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Programs" / "Inno Setup 6" / "ISCC.exe"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"")
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}, clear=True), patch("release.shutil.which", return_value=None):
                self.assertEqual(release.find_inno_setup(), str(path))


if __name__ == "__main__":
    unittest.main()
