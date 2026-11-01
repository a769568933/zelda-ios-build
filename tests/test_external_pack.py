import copy
import importlib.util
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
import zipfile

from test_pack import image

ROOT = Path(__file__).resolve().parents[1]


class _ExternalToolsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tools/pack_external.py'
        if not path.is_file():
            raise AssertionError('Independent TV packer implementation is missing')
        spec = importlib.util.spec_from_file_location('external_packer', path)
        cls.p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.p)

    def phone_info(self):
        return {'CFBundleIdentifier': 'org.example.game',
                'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': False,
                    'UISceneConfigurations': {'UIWindowSceneSessionRoleApplication': [
                        {'UISceneConfigurationName': 'Default', 'UISceneDelegateClassName': 'SceneDelegate'}]}}}

class ExternalConfigurationTests(_ExternalToolsBase):
    def test_tv_configuration_preserves_the_phone_scene(self):
        original = self.phone_info(); saved = copy.deepcopy(original)
        result = self.p.configure_tv(original)
        self.assertEqual(original, saved)
        scenes = result['UIApplicationSceneManifest']['UISceneConfigurations']
        self.assertEqual(scenes['UIWindowSceneSessionRoleApplication'],
                         saved['UIApplicationSceneManifest']['UISceneConfigurations']['UIWindowSceneSessionRoleApplication'])
        self.assertEqual(scenes[self.p.TV_ROLE][0]['UISceneDelegateClassName'], 'DmExternalSceneDelegate')
        self.assertFalse(result['UIApplicationSceneManifest']['UIApplicationSupportsMultipleScenes'])
        self.assertTrue(result['DMExternalDisplayEnabled'])

    def test_non_scene_host_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'scene'):
            self.p.configure_tv({'CFBundleIdentifier': 'old'})

    def test_existing_upstream_tv_configuration_is_not_overwritten(self):
        value = self.phone_info()
        value['UIApplicationSceneManifest']['UISceneConfigurations'][self.p.TV_ROLE] = [
            {'UISceneConfigurationName': 'TV', 'UISceneDelegateClassName': 'DmTVSceneDelegate'}]
        with self.assertRaisesRegex(ValueError, 'external'):
            self.p.configure_tv(value)

    def test_our_configuration_can_be_upgraded_idempotently(self):
        first = self.p.configure_tv(self.phone_info())
        self.assertEqual(self.p.configure_tv(first), first)

    def test_known_widescreen_game_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '16:9'):
            self.p.check_aspect({'requested_scene_pixels': [2622, 1206]})
        self.p.check_aspect({'requested_scene_pixels': [2144, 1206]})
        self.p.check_aspect({'default_handheld_scene_pixels': [1280, 720]})

    def test_external_loader_preserves_an_existing_touch_loader(self):
        self.assertTrue(callable(getattr(self.p, 'add_external_loader', None)),
                        'Independent external load command is missing')
        from tools.pack_ipa import add_dylib, commands
        source = add_dylib(image())
        result = self.p.add_external_loader(source)
        self.assertEqual(len(source), len(result))
        self.assertEqual(result[-4:], b'CODE')
        self.assertEqual(len(commands(result)), 3)
        self.assertEqual(self.p.add_external_loader(result), result)
        self.assertIn(self.p.TV_LOAD_PATH.encode(), result)

    def test_external_loader_rejects_a_signed_host(self):
        self.assertTrue(callable(getattr(self.p, 'add_external_loader', None)))
        signed = bytearray(image())
        struct.pack_into('<IIII', signed, 184, 0x1d, 16, 0, 0)
        struct.pack_into('<II', signed, 16, 2, 168)
        with self.assertRaisesRegex(ValueError, 'unsigned'):
            self.p.add_external_loader(bytes(signed))


def host_fixture(kind=2):
    names = b'App\0DmRootVC\0DmGameView\0'
    length = 4096
    segment = struct.pack('<II16sQQQQiiII', 0x19, 232, b'__TEXT', 0x100000000,
                          length, 0, length, 5, 5, 2, 0)
    def section(name, offset, size, flags):
        return struct.pack('<16s16sQQIIIIIIII', name, b'__TEXT',
                           0x100000000 + offset, size, offset, 0, 0, 0, flags, 0, 0, 0)
    body = segment + section(b'__text', 1024, 4, 0) + section(b'__objc_classname', 1028, len(names), 2)
    header = struct.pack('<IiiIIIII', 0xfeedfacf, 0x100000c, 0, kind, 1, len(body), 0, 0)
    result = bytearray(header + body + bytes(length - len(header) - len(body)))
    result[1024:1028] = b'CODE'; result[1028:1028 + len(names)] = names
    return bytes(result)


def library_fixture():
    result = bytearray(host_fixture(6))
    name = b'_dm_external_display_install\0'
    offset = 2 + len(name) + 1
    trie = bytes([0, 1]) + name + bytes([offset, 2, 0, 0, 0])
    end = len(result); result += trie
    struct.pack_into('<IIII', result, 264, 0x80000033, 16, end, len(trie))
    struct.pack_into('<IIIIII', result, 280, 0x32, 24, 2, 0x100000, 0x1a0000, 0)
    struct.pack_into('<II', result, 16, 3, 272)
    return bytes(result)


class ExternalAssemblyTests(_ExternalToolsBase):
    def test_local_assembly_preserves_game_resources_and_existing_controls(self):
        self.assertTrue(callable(getattr(self.p, 'assemble_external', None)),
                        'Independent TV assembly implementation is missing')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); original = root / 'input.ipa'; output = root / 'output.ipa'
            artifact = root / 'artifact'; artifact.mkdir()
            module = library_fixture()
            (artifact / 'DmExternalDisplay.dylib').write_bytes(module)
            (artifact / 'external-display-build.json').write_text(json.dumps({
                'compile_status': 'success', 'device_sha256': hashlib.sha256(module).hexdigest(),
                'source_commit': '1' * 40, 'simulator_tests': 'not_run'}))
            prefix = 'Payload/DmIOS.app/'
            info = self.phone_info(); info['CFBundleExecutable'] = 'DmIOS'
            unchanged = {'dm/env.txt': b'DM_KEEP=1\n', 'romfs/fixture.bin': b'game fixture bytes',
                         'Frameworks/DmPhoneControls.dylib': b'existing controls fixture'}
            with zipfile.ZipFile(original, 'w') as z:
                z.writestr(prefix + 'Info.plist', plistlib.dumps(info))
                z.writestr(prefix + 'DmIOS', host_fixture())
                for path, content in unchanged.items(): z.writestr(prefix + path, content)
            report = self.p.assemble_external(original, artifact, output)
            self.assertTrue(report['unsigned'])
            self.assertFalse(report['hdmi_device_verified'])
            with zipfile.ZipFile(output) as z:
                for path, content in unchanged.items(): self.assertEqual(z.read(prefix + path), content)
                after = plistlib.loads(z.read(prefix + 'Info.plist'))
                self.assertEqual(after['CFBundleIdentifier'], info['CFBundleIdentifier'])
                self.assertEqual(z.read(prefix + 'Frameworks/DmExternalDisplay.dylib'), module)
                self.assertIsNone(z.testzip())
            with self.assertRaisesRegex(ValueError, 'exists'):
                self.p.assemble_external(original, artifact, output)


if __name__ == '__main__': unittest.main()
