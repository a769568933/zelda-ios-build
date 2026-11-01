"""CLI orchestration only; fake Apple tools do not compile or run iOS code."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from test_external_pack import host_fixture, library_fixture

ROOT = Path(__file__).resolve().parents[1]


class LocalBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local build ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source with spaces'
        self.root.mkdir()
        shutil.copytree(ROOT / 'tools', self.root / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
        (self.root / 'SOURCE_VERSION').write_text('test-source\n')
        self.bin = Path(self.temp.name) / 'bin'
        self.bin.mkdir()
        self.tool('uname', '#!/bin/sh\nprintf "%s\\n" "${TEST_SYSTEM:-Darwin}"\n')
        self.tool('xcodebuild', '#!/bin/sh\nprintf "Xcode fixture\\nBuild fixture\\n"\n')
        self.tool('codesign', '#!/bin/sh\nexit 1\n')
        fixture = Path(self.temp.name) / 'fixture.dylib'
        fixture.write_bytes(library_fixture())
        self.tool('xcrun', '#!' + sys.executable + '\n' + '''import os, pathlib, sys
a = sys.argv[1:]
if a == ['--sdk', 'iphoneos', '--show-sdk-path']:
    if os.environ.get('TEST_NO_SDK'): sys.exit(1)
    print(os.environ['TEST_SDK'])
elif a == ['--sdk', 'iphoneos', '--find', 'clang']:
    print(sys.argv[0])
elif a and a[0] == 'clang':
    if os.environ.get('TEST_COMPILER_FAIL'): sys.exit(42)
    pathlib.Path(a[a.index('-o') + 1]).write_bytes(pathlib.Path(os.environ['TEST_LIBRARY']).read_bytes())
else: sys.exit(64)
''')
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        TEST_SDK=str(self.root), TEST_LIBRARY=str(fixture))
        # Avoid inheriting the selected runner's GitHub provenance.
        self.env.pop('GITHUB_ACTIONS', None)

    def tool(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def run_cli(self, *args, **env):
        return subprocess.run(['bash', str(self.root / 'tools/build_local.sh'), *args],
                              cwd=self.temp.name, env=dict(self.env, **env),
                              text=True, capture_output=True)

    def test_help_does_not_require_mac(self):
        result = self.run_cli('--help', TEST_SYSTEM='Linux')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--check', result.stdout)
        self.assertFalse((self.root / 'build').exists())

    def test_non_mac_fails_without_build_output(self):
        result = self.run_cli(TEST_SYSTEM='Linux')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('macOS', result.stderr)
        self.assertFalse((self.root / 'build').exists())

    def test_missing_iphone_sdk_fails_before_output(self):
        result = self.run_cli('--check', TEST_NO_SDK='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('iPhoneOS', result.stderr)
        self.assertFalse((self.root / 'build').exists())

    def test_check_does_not_invoke_compiler(self):
        result = self.run_cli('--check', TEST_COMPILER_FAIL='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'build').exists())

    def test_compiler_failure_cannot_reuse_old_metadata(self):
        old = self.root / 'build'
        old.mkdir()
        (old / 'external-display-build.json').write_text('{"compile_status":"success"}')
        result = self.run_cli(TEST_COMPILER_FAIL='1')
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertNotIn('Build complete:', result.stdout)
        self.assertEqual(list(old.glob('local.*/external-display-build.json')), [])

    def test_fresh_artifacts_and_source_id_work_without_git(self):
        for _ in range(2):
            result = self.run_cli()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Build complete:', result.stdout)
        runs = list((self.root / 'build').glob('local.*'))
        self.assertEqual(len(runs), 2)
        for run in runs:
            info = json.loads((run / 'external-display-build.json').read_text())
            self.assertEqual(info['source_commit'], 'test-source')
            self.assertEqual(info['build_mode'], 'local')
            self.assertFalse(info['full_game_execution_verified'])

    def test_missing_ipa_is_rejected_before_compilation(self):
        result = self.run_cli('missing game.ipa')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('IPA', result.stderr)
        self.assertFalse((self.root / 'build').exists())

    def test_assembly_uses_fresh_module_and_keeps_existing_controls(self):
        # Synthetic host + fake compiler: exercises real shell/metadata/IPA wiring.
        original = Path(self.temp.name) / 'input game.ipa'
        output = Path(self.temp.name) / 'output game.ipa'
        prefix = 'Payload/Test.app/'
        info = {'CFBundleExecutable': 'Test', 'CFBundleIdentifier': 'org.example.test',
                'UIApplicationSceneManifest': {'UISceneConfigurations': {
                    'UIWindowSceneSessionRoleApplication': [{'UISceneConfigurationName': 'Default'}]}}}
        with zipfile.ZipFile(original, 'w') as archive:
            archive.writestr(prefix + 'Info.plist', plistlib.dumps(info))
            archive.writestr(prefix + 'Test', host_fixture())
            archive.writestr(prefix + 'Frameworks/DmPhoneControls.dylib', b'keep existing controls')
        result = self.run_cli(original.name, output.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read(prefix + 'Frameworks/DmExternalDisplay.dylib'), library_fixture())
            self.assertEqual(archive.read(prefix + 'Frameworks/DmPhoneControls.dylib'), b'keep existing controls')
        reports = list((self.root / 'build').glob('local.*/ipa-report.json'))
        self.assertEqual(len(reports), 1)
        self.assertFalse(json.loads(reports[0].read_text())['full_game_execution_verified'])
        before = output.read_bytes()
        rejected = self.run_cli(original.name, output.name, TEST_COMPILER_FAIL='1')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('already exists', rejected.stderr)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(len(list((self.root / 'build').glob('local.*'))), 1)
