import subprocess
import unittest
from unittest.mock import patch

from media_to_video import run


class TerminalTest(unittest.TestCase):
    def test_ffmpeg_does_not_read_terminal_input(self):
        original = ["ffmpeg", "-i", "input.jpg", "output.mp4"]
        with patch("media_to_video.subprocess.run", return_value=subprocess.CompletedProcess(original, 0, "", "")) as execute:
            run(original)
        self.assertEqual(execute.call_args.args[0], ["ffmpeg", "-nostdin", *original[1:]])
        self.assertEqual(execute.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(original[1], "-i")

    def test_other_commands_also_have_isolated_stdin(self):
        command = ["sips", "-s", "format", "jpeg", "input.heic"]
        with patch("media_to_video.subprocess.run", return_value=subprocess.CompletedProcess(command, 0, "", "")) as execute:
            run(command)
        self.assertEqual(execute.call_args.args[0], command)
        self.assertEqual(execute.call_args.kwargs["stdin"], subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
