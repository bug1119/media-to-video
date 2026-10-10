import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("videos_by_time", Path(__file__).resolve().parents[1] / "videos_by_time.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VideosByTimeTest(unittest.TestCase):
    def test_no_arguments_displays_parameter_descriptions_and_examples(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(module.main([]), 2)
        help_text = output.getvalue()
        for text in ("使用範例", "--resolution 4k", "--list-only", "--time-source mtime",
                     "輸出每秒影格數", "每部影片的編碼執行緒數"):
            self.assertIn(text, help_text)

    def test_metadata_precedes_mtime_and_invalid_metadata_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clip.mp4"
            path.touch()
            os.utime(path, (100, 100))
            for value, expected, source in [("2024-01-01T08:00:00+08:00", 1704067200, "creation_time"),
                                             ("invalid", 100, "mtime")]:
                probe = subprocess.CompletedProcess([], 0, json.dumps({
                    "streams": [{"codec_type": "video"}], "format": {"tags": {"creation_time": value}}}))
                with patch.object(module.subprocess, "run", return_value=probe):
                    self.assertEqual(module.video_timestamp(path, "recorded"), (expected, source))
                    self.assertEqual(module.video_timestamp(path, "mtime"), (100, "mtime"))

    def test_recursive_time_order_no_video_filters_and_output_exclusion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            nested = root / "nested"
            nested.mkdir()
            late = root / "VIDEO_late.mp4"
            early = nested / "early.mov"
            output = root / "joined.mp4"
            for path in [late, early, output]:
                path.touch()
            (root / "photo.jpg").touch()
            (root / "link").symlink_to(nested, target_is_directory=True)
            with patch.object(module, "video_timestamp", side_effect=lambda p, _: (20 if p == late else 10, "mtime")):
                self.assertEqual([p for _, p, _ in module.collect_videos(root, output, "mtime")], [early, late])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_real_merge_with_audio_and_silent_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root / "nested"
            nested.mkdir()
            early = nested / "early.mp4"
            late = root / "VIDEO_late.mp4"
            common = ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi"]
            subprocess.run(common + ["-i", "color=c=red:s=64x64:r=10", "-t", "0.5",
                                     "-c:v", "libx264", "-metadata", "creation_time=2024-01-01T00:00:00Z", str(early)], check=True)
            subprocess.run(common + ["-i", "color=c=blue:s=64x64:r=10", "-f", "lavfi", "-i", "sine=frequency=440",
                                     "-t", "0.5", "-c:v", "libx264", "-c:a", "aac",
                                     "-metadata", "creation_time=2024-01-02T00:00:00Z", str(late)], check=True)
            output = root / "joined.mp4"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main([str(root), "--output", str(output), "--resolution", "64x64", "--fps", "10", "--threads", "1"]), 0)
            info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]))
            self.assertEqual({s["codec_type"] for s in info["streams"]}, {"audio", "video"})
            self.assertGreater(float(info["format"]["duration"]), .8)
            pixel = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(output),
                                             "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])
            self.assertGreater(pixel[0], pixel[2])
