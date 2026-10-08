import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from media_to_video import MAX_VIDEO_BYTES, collect_media


class MediaFilterTest(unittest.TestCase):
    def test_size_boundary_and_case_insensitive_prefix_only_affect_videos(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in ("large.mp4", "boundary.mp4", "Video001.MOV", "video-photo.jpg", "clip.mp4"):
                (root / name).touch()
            real_stat = Path.stat

            def stat(path, *args, **kwargs):
                if path.name == "large.mp4":
                    return SimpleNamespace(st_size=MAX_VIDEO_BYTES + 1)
                if path.name == "boundary.mp4":
                    return SimpleNamespace(st_size=MAX_VIDEO_BYTES)
                return real_stat(path, *args, **kwargs)

            # Preserve normal is_file/resolve checks while substituting only size reads.
            with (
                patch.object(Path, "is_file", return_value=True),
                patch.object(Path, "resolve", autospec=True, side_effect=lambda path: path),
                patch.object(Path, "stat", autospec=True, side_effect=stat),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                media = collect_media(root, root / "output.mp4")
            self.assertEqual([path.name for path in media], ["boundary.mp4", "clip.mp4", "video-photo.jpg"])
            self.assertIn("檔案大於 200 MB", output.getvalue())
            self.assertIn("檔名以 video 開頭", output.getvalue())

    def test_count_boundary_excludes_existing_output_before_counting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            output = root / "output.mp4"
            output.touch()
            photo = root / "photo.jpg"
            photo.touch()
            for index in range(10):
                (root / f"clip-{index:02}.mp4").touch()
            self.assertEqual(len(collect_media(root, output)), 11)
            (root / "video-extra.mp4").touch()
            with contextlib.redirect_stdout(io.StringIO()) as summary:
                self.assertEqual(collect_media(root, output), [photo])
            self.assertIn("目錄內有 11 部影片", summary.getvalue())

    def test_each_subdirectory_is_filtered_independently(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            for index in range(11):
                (first / f"clip-{index}.mp4").touch()
            video = second / "clip.mp4"
            video.touch()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(collect_media(first, root / "first.mp4"), [])
                self.assertEqual(collect_media(second, root / "second.mp4"), [video])


if __name__ == "__main__":
    unittest.main()
