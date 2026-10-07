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

    def test_no_arguments_prints_examples(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["media_to_video.py"]), contextlib.redirect_stderr(output):
            self.assertEqual(main(), 2)
        self.assertIn("examples:", output.getvalue())
        self.assertIn("--music music.mp3", output.getvalue())
        self.assertIn("--resolution 3840x2160", output.getvalue())


if __name__ == "__main__":
    unittest.main()
