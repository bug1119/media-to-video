import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import main


class BadPhotoTest(unittest.TestCase):
    def test_bad_photos_and_empty_files_are_skipped_with_correct_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in ("01-good.jpg", "02-bad.jpg", "03-bad.png", "04-render.jpg"):
                (root / name).write_bytes(b"fixture")
            (root / "05-empty.jpg").touch()
            (root / "06-empty.mp4").touch()
            summary = io.StringIO()

            def measure(path):
                if path.name == "02-bad.jpg":
                    raise ValueError("cannot determine dimensions")
                return 320, 180

            def render(source, *args):
                if source.name == "04-render.jpg":
                    raise subprocess.CalledProcessError(1, ["ffmpeg"])

            with (
                patch.object(sys, "argv", [
                    "media_to_video.py", temp, "--resolution", "320x180",
                    "--output", str(root / "output.mp4"), "--audio-mode", "original",
                ]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.dimensions", side_effect=measure),
                patch("media_to_video.convert_photo_to_jpg", side_effect=subprocess.CalledProcessError(1, ["ffmpeg"])),
                patch("media_to_video.render_photo", side_effect=render),
                patch("media_to_video.render_video") as video,
                patch("media_to_video.concat_segments") as concat,
                patch("media_to_video.shutil.copy2"),
                contextlib.redirect_stdout(summary),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(len(concat.call_args.args[0]), 1)
            video.assert_not_called()
            self.assertEqual(summary.getvalue().count("跳過壞圖"), 3)
            self.assertEqual(summary.getvalue().count("檔案大小為 0 bytes"), 2)
            self.assertIn("合併完成：1 張照片、0 部影片，共 1 個素材", summary.getvalue())

    def test_all_invalid_album_does_not_stop_next_album(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in ("a", "b"):
                (root / name).mkdir()
            (root / "a" / "empty.jpg").touch()
            (root / "b" / "good.jpg").write_bytes(b"fixture")
            with (
                patch.object(sys, "argv", ["media_to_video.py", temp, "--resolution", "320x180", "--audio-mode", "original"]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.dimensions", return_value=(320, 180)),
                patch("media_to_video.render_photo"),
                patch("media_to_video.concat_segments") as concat,
                patch("media_to_video.shutil.copy2"),
                contextlib.redirect_stdout(io.StringIO()) as summary,
            ):
                self.assertEqual(main(), 0)
            concat.assert_called_once()
            self.assertIn("批次完成：輸出 1 支影片", summary.getvalue())


if __name__ == "__main__":
    unittest.main()
