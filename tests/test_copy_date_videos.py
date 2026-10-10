import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("copy_date_videos", Path(__file__).resolve().parents[1] / "copy_date_videos.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CopyDateVideosTest(unittest.TestCase):
    def test_first_level_videos_only_and_existing_files_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "destination"
            year = source / "2021"
            nested = year / "nested"
            nested.mkdir(parents=True)
            (year / "clip.MOV").write_bytes(b"new video")
            (year / "photo.jpg").write_bytes(b"photo")
            (nested / "hidden.mp4").write_bytes(b"nested video")
            other = source / "holiday"
            other.mkdir()
            (other / "clip.mp4").touch()
            day = source / "20240101"
            day.mkdir()
            (day / "existing.mp4").write_bytes(b"source")
            (destination / day.name).mkdir(parents=True)
            (destination / day.name / "existing.mp4").write_bytes(b"original")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main([str(source), str(destination)]), 0)
                self.assertEqual(module.copy_videos(source, destination), (0, 2))
            self.assertEqual((destination / "2021" / "clip.MOV").read_bytes(), b"new video")
            self.assertEqual((destination / day.name / "existing.mp4").read_bytes(), b"original")
            self.assertEqual(sorted(p.name for p in (destination / "2021").iterdir()), ["clip.MOV"])
            self.assertFalse((destination / "holiday").exists())

    def test_supported_date_names(self):
        for name in ("2021", "202401", "20240101", "2024-01", "2024-01-01", "2024010507"):
            self.assertTrue(module.is_date_directory(name), name)
        for name in ("holiday", "202413", "20240230", "2024.log", "2024-trip"):
            self.assertFalse(module.is_date_directory(name), name)
