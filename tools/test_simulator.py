"""Compile a disposable UIKit host and exercise the module on Apple's simulator."""
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.pack_ipa import add_dylib


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


app = ROOT / 'build/TouchHarness.app'
(app / 'Frameworks').mkdir(parents=True, exist_ok=True)
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
executable = app / 'TouchHarness'
run(['xcrun', 'clang', '-target', 'arm64-apple-ios16.0-simulator', '-isysroot', sdk,
     '-fobjc-arc', '-fblocks', '-O1', '-Iinclude', '-framework', 'UIKit',
     '-framework', 'Foundation', '-Wl,-export_dynamic', '-Wl,-headerpad,0x1000',
     'tests/SimulatorHost.m', '-o', str(executable)], cwd=ROOT)
run(['codesign', '--remove-signature', str(executable)], stdout=subprocess.DEVNULL)
executable.write_bytes(add_dylib(executable.read_bytes()))
shutil.copyfile(ROOT / 'build/simulator/DmPhoneControls.dylib', app / 'Frameworks/DmPhoneControls.dylib')
identifier = 'org.nxnative.touch-harness'
with (app / 'Info.plist').open('wb') as out:
    plistlib.dump({'CFBundleExecutable': 'TouchHarness', 'CFBundleIdentifier': identifier,
                  'CFBundleName': 'TouchHarness', 'CFBundlePackageType': 'APPL',
                  'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0',
                  'MinimumOSVersion': '16.0', 'UIDeviceFamily': [1],
                  'CFBundleSupportedPlatforms': ['iPhoneSimulator'],
                  'LSRequiresIPhoneOS': True, 'UILaunchScreen': {}}, out)
run(['codesign', '--force', '--sign', '-', str(app / 'Frameworks/DmPhoneControls.dylib')])
run(['codesign', '--force', '--sign', '-', str(app)])

inventory = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], text=True))
candidates = [d for runtime, devices in sorted(inventory['devices'].items(), reverse=True)
              if 'iOS' in runtime for d in devices if 'iPhone' in d['name'] and d.get('isAvailable')]
if not candidates:
    raise RuntimeError('No installed iPhone simulator runtime')
device = next((d for d in candidates if d['state'] == 'Booted'), candidates[0])
udid = device['udid']
if device['state'] != 'Booted':
    run(['xcrun', 'simctl', 'boot', udid])
run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=300)
run(['xcrun', 'simctl', 'install', udid, str(app)])
run(['xcrun', 'simctl', 'launch', '--console', '--terminate-running-process', udid, identifier], timeout=120)
container = subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid, identifier, 'data'], text=True).strip()
result = Path(container) / 'Documents/touch-result.json'
data = json.loads(result.read_text())
if data.get('status') != 'passed' or data.get('checks', 0) < 19:
    raise RuntimeError('Simulator integration checks failed')
shutil.copyfile(result, ROOT / 'build/simulator-result.json')
print(json.dumps(data))
