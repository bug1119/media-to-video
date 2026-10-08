import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from media_to_video import auto_resolution, main, parse_resolution


class ResolutionTest(unittest.TestCase):
    def choose(self, sizes):
        paths = [Path(f"item-{index}") for index in range(len(sizes))]
        with patch("media_to_video.dimensions", side_effect=sizes):
            return auto_resolution(paths)

    def test_selects_4k_when_every_source_qualifies(self):
        self.assertEqual(self.choose([(3840, 2160), (2160, 3840), (7680, 4320)]), (3840, 2160))

    def test_falls_back_to_2k_for_mixed_4k_and_2k(self):
        self.assertEqual(self.choose([(3840, 2160), (1440, 2560)]), (2560, 1440))

    def test_falls_back_to_1080p(self):
        self.assertEqual(self.choose([(2560, 1440), (1920, 1080)]), (1920, 1080))

    def test_uses_1080p_when_a_source_requires_upscaling(self):
        self.assertEqual(self.choose([(1280, 720), (1920, 1080)]), (1920, 1080))

    def test_manual_and_auto_resolution_parsing(self):
        self.assertIsNone(parse_resolution("auto"))
        self.assertEqual(parse_resolution("3840x2160"), (3840, 2160))

    def test_mixed_media_uses_only_video_dimensions(self):
        media = [Path("small.jpg"), Path("4k.MOV"), Path("2k.mp4")]
        with patch("media_to_video.dimensions", side_effect=[(3840, 2160), (2560, 1440)]) as measure:
            self.assertEqual(auto_resolution(media), (2560, 1440))
        self.assertEqual([call.args[0] for call in measure.call_args_list], media[1:])

    def test_high_resolution_photos_do_not_raise_video_resolution(self):
        media = [Path("4k.jpg"), Path("1080p.mp4")]
        with patch("media_to_video.dimensions", return_value=(1920, 1080)) as measure:
            self.assertEqual(auto_resolution(media), (1920, 1080))
        measure.assert_called_once_with(media[1])

    def test_photo_only_uses_all_photo_dimensions(self):
        media = [Path("4k.jpg"), Path("2k.png")]
        with patch("media_to_video.dimensions", side_effect=[(3840, 2160), (2560, 1440)]) as measure:
            self.assertEqual(auto_resolution(media), (2560, 1440))
        self.assertEqual([call.args[0] for call in measure.call_args_list], media)

    def test_no_arguments_prints_examples(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["media_to_video.py"]), contextlib.redirect_stderr(output):
            self.assertEqual(main(), 2)
        self.assertIn("examples:", output.getvalue())
        self.assertIn("--music music.mp3", output.getvalue())
        self.assertIn("--resolution 3840x2160", output.getvalue())


if __name__ == "__main__":
    unittest.main()
