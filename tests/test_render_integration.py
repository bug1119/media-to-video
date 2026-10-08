import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import main


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is required")
class RenderIntegrationTest(unittest.TestCase):
    def test_parallel_photos_and_videos_produce_ordered_playable_output(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            output = directory / "output.mp4"
            output.touch()
            summary = io.StringIO()

            def ffmpeg(*args):
                return subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                    check=True, capture_output=True,
                )

            ffmpeg(
                "-f", "lavfi", "-i", "color=red:s=320x180", "-frames:v", "1",
                str(directory / "01.jpg"),
            )
            ffmpeg(
                "-f", "lavfi", "-i", "color=blue:s=320x180:r=30",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "1", "-c:v", "libx264", "-c:a", "aac", str(directory / "02.mp4"),
            )
            ffmpeg(
                "-f", "lavfi", "-i", "color=lime:s=320x180:r=30",
                "-t", "1", "-c:v", "libx264", str(directory / "03.mp4"),
            )
            with (
                patch.object(sys, "argv", [
                    "media_to_video.py", temp, "--output", str(output),
                    "--resolution", "320x180", "--photo-duration", "1",
                ]),
                patch("media_to_video.time.perf_counter", side_effect=[100.0, 102.5]),
                contextlib.redirect_stdout(summary),
            ):
                self.assertEqual(main(), 0)

            self.assertIn("合併完成：1 張照片、2 部影片，共 3 個素材。", summary.getvalue())
            self.assertIn("總執行時間：2.50 秒。", summary.getvalue())

            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)],
                check=True, capture_output=True, text=True,
            )
            info = json.loads(probe.stdout)
            video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (320, 180))
            self.assertTrue(any(stream["codec_type"] == "audio" for stream in info["streams"]))
            self.assertAlmostEqual(float(info["format"]["duration"]), 3, delta=0.3)
            for timestamp, channel in (("0.2", 0), ("1.3", 2), ("2.3", 1)):
                pixel = ffmpeg(
                    "-ss", timestamp, "-i", str(output), "-frames:v", "1",
                    "-vf", "scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
                ).stdout
                self.assertEqual(len(pixel), 3)
                self.assertGreater(pixel[channel], 200)
                self.assertTrue(all(value < 50 for index, value in enumerate(pixel) if index != channel))


if __name__ == "__main__":
    unittest.main()
