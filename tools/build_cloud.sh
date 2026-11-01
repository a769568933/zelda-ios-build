#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/device build/simulator

build_module() {
  local sdk=$1 triple=$2 out=$3 sysroot
  sysroot=$(xcrun --sdk "$sdk" --show-sdk-path)
  local flags=(-target "$triple" -isysroot "$sysroot" -fobjc-arc -fblocks -O2 -Iinclude -Isrc -Wno-deprecated-declarations)
  xcrun clang "${flags[@]}" -DDmGamepad=DmPhoneGamepad -Ddm_gamepad_view=dm_phone_gamepad_view \
    -Ddm_gamepad_reset=dm_phone_gamepad_reset -c src/DmGamepad.m -o "$out/gamepad.o"
  xcrun clang "${flags[@]}" -c src/InstallControls.m -o "$out/install.o"
  xcrun clang "${flags[@]}" -dynamiclib "$out/gamepad.o" "$out/install.o" \
    -Wl,-undefined,dynamic_lookup -Wl,-no_fixup_chains \
    -Wl,-install_name,@rpath/DmPhoneControls.dylib \
    -framework UIKit -framework Foundation -framework GameController -framework CoreMotion \
    -framework CoreText -framework QuartzCore -framework CoreGraphics -o "$out/DmPhoneControls.dylib"
}

build_module iphoneos arm64-apple-ios16.0 build/device

# Independent TV output uses runtime lookup for the host classes and iOS 27's
# scene accessory, so it has no unresolved imports from a private game binary.
device_sdk=$(xcrun --sdk iphoneos --show-sdk-path)
external_flags=(-target arm64-apple-ios16.0 -isysroot "$device_sdk" -fobjc-arc -fblocks -O2 -Isrc -Wno-deprecated-declarations)
xcrun clang "${external_flags[@]}" -dynamiclib src/DmExternalDisplay.m \
  -Wl,-no_fixup_chains -Wl,-install_name,@rpath/DmExternalDisplay.dylib \
  -framework UIKit -framework Foundation -framework QuartzCore -framework CoreGraphics \
  -o build/DmExternalDisplay.dylib
codesign --remove-signature build/DmExternalDisplay.dylib 2>/dev/null || true
# Compile the local UIKit fixture for interface checking only. Never execute it
# or a simulator/game in this GitHub job.
xcrun clang "${external_flags[@]}" -c tests/ExternalDisplayHarness.m -o build/device/external-harness.o

# Both device libraries are delivered unsigned.
codesign --remove-signature build/device/DmPhoneControls.dylib 2>/dev/null || true
cp build/device/DmPhoneControls.dylib build/DmPhoneControls.dylib
python3 - <<'PY'
from pathlib import Path
import hashlib, json, os, struct, subprocess
def require_unsigned(path):
    data = Path(path).read_bytes()
    if len(data) < 32 or struct.unpack_from('<II', data) != (0xfeedfacf, 0x100000c):
        raise RuntimeError('Unexpected device Mach-O architecture')
    count, size = struct.unpack_from('<II', data, 16)
    cursor = 32
    for _ in range(count):
        command, length = struct.unpack_from('<II', data, cursor)
        if length < 8 or cursor + length > 32 + size:
            raise RuntimeError('Invalid device load command')
        if command == 0x1d:
            raise RuntimeError('Device library is still signed')
        cursor += length
    if cursor != 32 + size:
        raise RuntimeError('Invalid device load-command size')
require_unsigned('build/DmPhoneControls.dylib')
require_unsigned('build/DmExternalDisplay.dylib')
p = Path('build/DmPhoneControls.dylib'); data = p.read_bytes()
info = {'source_commit': os.environ.get('GITHUB_SHA', 'local'),
        'device_sha256': hashlib.sha256(data).hexdigest(),
        'compile_status': 'success', 'simulator_tests': 'not_run', 'simulator_checks': 0,
        'control_mode': 'dual-locked-sticks-v1',
        'xcode': subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
        'native_scene_resolution_verified': False, 'sustained_60fps_verified': False}
Path('build/build-info.json').write_text(json.dumps(info, indent=2) + '\n')
p = Path('build/DmExternalDisplay.dylib')
external = {'source_commit': os.environ.get('GITHUB_SHA', 'local'),
            'device_sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
            'compile_status': 'success', 'unsigned': True, 'simulator_tests': 'not_run',
            'uikit_lifecycle_harness': 'compiled_not_run',
            'tv_aspect': [16, 9], 'tv_drawable_limit': [1920, 1080],
            'hdmi_device_verified': False, 'full_game_execution_verified': False,
            'sustained_60fps_verified': False, 'xcode': info['xcode']}
Path('build/external-display-build.json').write_text(json.dumps(external, indent=2) + '\n')
PY

