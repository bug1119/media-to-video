import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import main


class LoggingTest(unittest.TestCase):
    def test_log_is_beside_output_for_single_and_batch_modes(self):
        for batch in (False, True):
            with self.subTest(batch=batch), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                media = root / "202601"
                media.mkdir()
                source = media / "album" if batch else media
                source.mkdir(exist_ok=True)
                (source / "photo.jpg").touch()
                destination = root / "rendered"
                output = destination if batch else destination / "renamed.mp4"
                with (
                    patch.object(sys, "argv", ["media_to_video.py", str(media), "--output", str(output)]),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_directory", return_value=(1, 0)),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(), 0)
                self.assertTrue((destination / "202601.log").is_file())
                self.assertFalse((media / "202601.log").exists())

    def test_default_log_records_progress_exclusions_summary_and_appends(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "photo.jpg").touch()
            (root / "video-ignore.mp4").touch()
            log = root / f"{root.name}.log"
            for _ in range(2):
                with (
                    patch.object(sys, "argv", [
                        "media_to_video.py", temp, "--resolution", "320x180",
                        "--output", str(root / "output.mp4"),
                        "--audio-mode", "original",
                    ]),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_photo"),
                    patch("media_to_video.concat_segments"),
                    patch("media_to_video.shutil.copy2"),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(), 0)
            text = log.read_text(encoding="utf-8")
            self.assertIn("[INFO]", text)
            self.assertIn("排除影片：", text)
            self.assertIn("[1/1] photo.jpg", text)
            self.assertEqual(text.count("合併完成：1 張照片、0 部影片"), 2)
            self.assertIn("總執行時間：", text)

    def test_custom_log_records_ffmpeg_stderr_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            media = root / "media"
            media.mkdir()
            (media / "photo.jpg").touch()
            log = root / "logs" / "run.log"
            with (
                patch.object(sys, "argv", [
                    "media_to_video.py", str(media), "--resolution", "320x180", "--log-file", str(log),
                ]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.subprocess.run", return_value=subprocess.CompletedProcess(
                    ["ffmpeg"], 1, "", "encoding failed\n",
                )),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                main()
            text = log.read_text(encoding="utf-8")
            self.assertIn("執行指令：", text)
            self.assertIn("encoding failed", text)
            self.assertIn("執行失敗", text)
            self.assertNotIn("合併完成", text)


if __name__ == "__main__":
    unittest.main()
