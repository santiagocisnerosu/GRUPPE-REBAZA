import json
import math
import re
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.audio import normalize_audio


class WildcardMasteringTests(unittest.TestCase):
    def test_retry_adjusts_gain_and_measured_peak_independently(self):
        # Start with the observed Dutch measurements. The second encode lands
        # exactly on the excluded peak boundary, the third inside both limits.
        readings = iter([(-26.34, -3.46), (-18.60, -0.07), (-16.85, -1), (-16.75, -1.23)])
        filters = []

        def ffmpeg(args, **kwargs):
            stdout = stderr = b""
            if args[-2:] == ["null", "-"]:
                loudness, peak = next(readings)
                stderr = json.dumps(dict(input_i=loudness, input_tp=peak, input_lra=11,
                                         input_thresh=-30, target_offset=0)).encode()
            elif args[-2:] == ["s16le", "-"]:
                stdout = bytes(100)
            else:
                filters.append(args[args.index("-af") + 1])
                Path(args[-1]).write_bytes(bytes([len(filters)]))
            return CompletedProcess(args, 0, stdout, stderr)

        with TemporaryDirectory() as folder, patch("src.audio.subprocess.run", side_effect=ffmpeg):
            target = Path(folder) / "briefing.mp3"
            normalize_audio(b"source", target, wildcard=True)
            self.assertEqual(target.read_bytes(), bytes([3]))
        self.assertIn("volume=2.60dB", filters[1])
        ceiling = float(re.search(r"alimiter=limit=([\d.]+)", filters[1])[1])
        self.assertAlmostEqual(20 * math.log10(ceiling), -3.08, places=2)
