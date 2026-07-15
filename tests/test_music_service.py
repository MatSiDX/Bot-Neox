import unittest
from unittest.mock import patch

try:
    from services.music_service import FFmpegNotFoundError, resolve_ffmpeg_executable
except ModuleNotFoundError as exc:
    if exc.name in {"discord", "yt_dlp"}:
        raise unittest.SkipTest("discord.py o yt-dlp no estan instalados") from exc
    raise


class MusicServiceTests(unittest.TestCase):
    def test_resolve_ffmpeg_executable_uses_path_by_default(self):
        with patch("services.music_service.shutil.which", return_value="/usr/bin/ffmpeg") as which:
            self.assertEqual(resolve_ffmpeg_executable(), "/usr/bin/ffmpeg")

        which.assert_called_once_with("ffmpeg")

    def test_resolve_ffmpeg_executable_uses_configured_path(self):
        with patch("services.music_service.shutil.which", return_value="/custom/bin/ffmpeg") as which:
            self.assertEqual(resolve_ffmpeg_executable("/custom/bin/ffmpeg"), "/custom/bin/ffmpeg")

        which.assert_called_once_with("/custom/bin/ffmpeg")

    def test_resolve_ffmpeg_executable_raises_clear_error_when_missing_from_path(self):
        with patch("services.music_service.shutil.which", return_value=None):
            with self.assertRaises(FFmpegNotFoundError) as raised:
                resolve_ffmpeg_executable()

        self.assertIn("PATH", str(raised.exception))

    def test_resolve_ffmpeg_executable_raises_clear_error_for_invalid_configured_path(self):
        with patch("services.music_service.shutil.which", return_value=None):
            with self.assertRaises(FFmpegNotFoundError) as raised:
                resolve_ffmpeg_executable("/missing/ffmpeg")

        message = str(raised.exception)
        self.assertIn("FFMPEG_PATH", message)
        self.assertIn("/missing/ffmpeg", message)


if __name__ == "__main__":
    unittest.main()
