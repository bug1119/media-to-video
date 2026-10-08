import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import directory_date, main


class MonthlyTest(unittest.TestCase):
    def test_valid_calendar_dates_only(self):
        self.assertEqual(str(directory_date("20260101")), "2026-01-01")
        self.assertEqual(str(directory_date("2026-01-15")), "2026-01-15")
        for name in ("20260230", "20261301", "202601", "trip", "2026-1-1"):
            self.assertIsNone(directory_date(name))

    def test_monthly_groups_and_direct_date_selection(self):
        for direct in (False, True):
            with self.subTest(direct=direct), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source = root / "picture"
                source.mkdir()
                for name in ("20260101", "2026-01-15", "20260201", "trip"):
                    folder = source / name
                    folder.mkdir()
                    (folder / "b.jpg").touch()
                    (folder / "a.PNG").touch()
                    (folder / "clip.mp4").touch()
                output = root / "monthly.mp4" if direct else root / "rendered"
                target = source / "20260101" if direct else source
                with (
                    patch.object(sys, "argv", [
                        "media_to_video.py", str(target), "--output", str(output),
                        "--audio-mode", "original",
                    ]),
                    patch("media_to_video.shutil.which", return_value="ffmpeg"),
                    patch("media_to_video.render_directory", return_value=(4, 0)) as render,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(), 0)
                first_media, first_output = render.call_args_list[0].args[:2]
                self.assertEqual(first_media, [
                    source / day / filename
                    for day in ("20260101", "2026-01-15") for filename in ("a.PNG", "b.jpg")
                ])
                self.assertEqual(first_output, output if direct else output / "202601.mp4")
                self.assertEqual(render.call_count, 1 if direct else 3)
                if not direct:
                    self.assertEqual(render.call_args_list[1].args[1], output / "202602.mp4")
                    self.assertIn(source / "trip" / "clip.mp4", render.call_args_list[2].args[0])

    def test_existing_month_output_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in ("20260101", "20260102"):
                (root / name).mkdir()
                (root / name / "photo.jpg").touch()
            (root / "202601.mp4").write_bytes(b"existing")
            with (
                patch.object(sys, "argv", ["media_to_video.py", temp, "--audio-mode", "original"]),
                patch("media_to_video.shutil.which", return_value="ffmpeg"),
                patch("media_to_video.render_directory") as render,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            render.assert_not_called()
            self.assertEqual((root / "202601.mp4").read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
