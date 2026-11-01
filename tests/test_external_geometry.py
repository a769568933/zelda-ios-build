from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExternalGeometryTests(unittest.TestCase):
    def test_tv_output_fits_16_by_9_and_preserves_pixel_budget(self):
        self.assertTrue((ROOT / 'src/DmExternalGeometry.h').is_file(),
                        'Independent TV geometry implementation is missing')
        with tempfile.TemporaryDirectory() as directory:
            exe = str(Path(directory) / 'geometry')
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-pedantic', '-Isrc', 'tests/t_external_geometry.c',
                            '-lm', '-o', exe], cwd=ROOT, check=True)
            result = subprocess.run([exe], check=True, text=True, capture_output=True)
            self.assertIn('20 external display geometry cases passed', result.stdout)


if __name__ == '__main__': unittest.main()
