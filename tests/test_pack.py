import importlib.util
import io
import os
from pathlib import Path
import struct
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def image(kind=2, room=512):
    # A small valid ARM64 Mach-O with one regular __text section.
    command = struct.pack('<II16sQQQQiiII', 0x19, 152, b'__TEXT', 0x100000000,
                          0x4000, 0, 0x4000, 5, 5, 1, 0)
    offset = 32 + len(command) + 80 + room
    section = struct.pack('<16s16sQQIIIIIIII', b'__text', b'__TEXT',
                          0x100000000 + offset, 4, offset, 2, 0, 0, 0, 0, 0, 0)
    header = struct.pack('<IiiIIIII', 0xfeedfacf, 0x100000c, 0, kind, 1, 152, 0, 0)
    return header + command + section + bytes(room) + b'CODE'


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tools/pack_ipa.py'
        if not path.is_file():
            raise AssertionError('The safe local IPA packaging implementation is missing')
        spec = importlib.util.spec_from_file_location('packer', path)
        cls.packer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.packer)

    def test_adds_loader_without_moving_or_changing_code(self):
        before = image()
        result = self.packer.add_dylib(before)
        self.assertEqual(len(result), len(before))
        self.assertEqual(result[-4:], b'CODE')
        self.assertEqual(struct.unpack_from('<I', result, 16)[0], 2)
        commands = self.packer.commands(result)
        self.assertEqual(commands[-1][0], 0xc)
        self.assertIn(self.packer.LOAD_PATH.encode(), result)
        # Apart from the count/size fields and the added command, bytes stay identical.
        new_end = 32 + struct.unpack_from('<I', result, 20)[0]
        self.assertEqual(result[:16], before[:16])
        self.assertEqual(result[24:184], before[24:184])
        self.assertEqual(result[new_end:], before[new_end:])

    def test_rejects_double_insertion(self):
        with self.assertRaisesRegex(ValueError, 'already'):
            self.packer.add_dylib(self.packer.add_dylib(image()))

    def test_rejects_overwriting_file_backed_section(self):
        with self.assertRaisesRegex(ValueError, 'space'):
            self.packer.add_dylib(image(room=8))

    def test_rejects_nonzero_header_padding(self):
        b = bytearray(image()); b[184] = 7
        with self.assertRaisesRegex(ValueError, 'padding'):
            self.packer.add_dylib(bytes(b))

    def test_rejects_wrong_architecture(self):
        b = bytearray(image()); struct.pack_into('<I', b, 4, 0x1000007)
        with self.assertRaisesRegex(ValueError, 'ARM64'):
            self.packer.add_dylib(bytes(b))

    def test_rejects_truncated_commands(self):
        with self.assertRaises(ValueError):
            self.packer.commands(image()[:90])

    def test_rejects_unknown_host_before_patching(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            self.packer.verify_host(image())

    def test_added_library_has_portable_executable_permissions(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(self.packer.archive_entry('Frameworks/Controls.dylib'), b'fixture')
        with zipfile.ZipFile(stream) as archive:
            entry = archive.infolist()[0]
            self.assertEqual(entry.create_system, 3, 'Extractors must interpret the mode as Unix')
            self.assertEqual(entry.external_attr >> 16, 0o100755)

    @unittest.skipUnless(os.environ.get('ZELDA_ORIGINAL_IPA'), 'Original app stays local')
    def test_actual_host_exports_and_code_preservation(self):
        with zipfile.ZipFile(os.environ['ZELDA_ORIGINAL_IPA']) as archive:
            before = archive.read('Payload/DmIOS.app/DmIOS')
        self.packer.verify_host(before)
        names = self.packer.exports(before)
        self.assertTrue({'_dm_input_set', '_dm_touch_set', '_OBJC_CLASS_$_DmGamepad'} <= names)
        after = self.packer.add_dylib(before)
        end = 32 + struct.unpack_from('<I', after, 20)[0]
        self.assertEqual(after[end:], before[end:])
        self.assertEqual(len(after), len(before))


if __name__ == '__main__':
    unittest.main()
