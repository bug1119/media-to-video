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

from media_to_video import convert_photo_to_jpg, dimensions, main


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is required")
class RenderIntegrationTest(unittest.TestCase):
    def test_png_is_converted_to_real_jpg(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for extension in ("png",):
                source = root / f"photo.{extension}"
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                     "color=red:s=320x180", "-frames:v", "1", str(source)],
                    check=True, capture_output=True,
                )
                output = root / f"{extension}.jpg"
                with contextlib.redirect_stdout(io.StringIO()):
                    convert_photo_to_jpg(source, output)
                self.assertEqual(output.read_bytes()[:2], b"\xff\xd8")
                self.assertEqual(dimensions(output), (320, 180))
                self.assertTrue(source.exists())

    def test_batch_outputs_each_album_with_default_photo_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            music = root / "music"
            music.mkdir()
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                 "-t", "0.2", str(music / "tone.mp3")],
                check=True, capture_output=True,
            )
            for name, color in (("album-a", "red"), ("album-b", "blue")):
                album = root / name
                album.mkdir()
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                     "-f", "lavfi", "-i", f"color={color}:s=320x180", "-frames:v", "1",
                     str(album / "photo.jpg")],
                    check=True, capture_output=True,
                )
            summary = io.StringIO()
            with (
                patch.object(sys, "argv", [
                    "media_to_video.py", temp, "--resolution", "320x180", "--music", str(music),
                ]),
                contextlib.redirect_stdout(summary),
            ):
                self.assertEqual(main(), 0)
            for name in ("album-a", "album-b"):
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "json", str(root / f"{name}.mp4")],
                    check=True, capture_output=True, text=True,
                )
                self.assertAlmostEqual(float(json.loads(probe.stdout)["format"]["duration"]), 1.5, delta=0.1)
                audio = subprocess.run(
                    ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(root / f"{name}.mp4"),
                     "-t", "0.1", "-vn", "-f", "s16le", "pipe:1"],
                    check=True, capture_output=True,
                ).stdout
                self.assertTrue(audio)
                self.assertTrue(any(audio), "Looping background music must remain audible")
            self.assertIn("批次完成：輸出 2 支影片，合併 2 張照片、0 部影片，共 2 個素材。", summary.getvalue())

    def test_parallel_photos_and_videos_produce_ordered_playable_output(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            output = directory / "output.mp4"
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
