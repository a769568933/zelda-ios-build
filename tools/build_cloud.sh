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
    -framework CoreText -framework QuartzCore -o "$out/DmPhoneControls.dylib"
}

python3 -m unittest discover -s tests -p test_pack.py -v
clang -std=c11 -Wall -Wextra -Werror tests/t_touch_motion.c -lm -o build/t_touch_motion
./build/t_touch_motion
build_module iphoneos arm64-apple-ios16.0 build/device
build_module iphonesimulator arm64-apple-ios16.0-simulator build/simulator

# Device deliverable remains unsigned. Signing below is only for an ephemeral
# simulator test host, never for the game IPA or a physical device.
codesign --remove-signature build/device/DmPhoneControls.dylib 2>/dev/null || true
cp build/device/DmPhoneControls.dylib build/DmPhoneControls.dylib
python3 tools/test_simulator.py
python3 - <<'PY'
from pathlib import Path
import hashlib, json, os, subprocess
from tools.pack_ipa import commands, exports
p = Path('build/DmPhoneControls.dylib'); data = p.read_bytes()
assert not any(c == 0x1d for c, _, _ in commands(data)), 'Device module is signed'
assert {'_dm_phone_gamepad_view', '_dm_phone_gamepad_reset'} <= exports(data)
result = json.loads(Path('build/simulator-result.json').read_text())
assert result['status'] == 'passed'
info = {'source_commit': os.environ.get('GITHUB_SHA', 'local'),
        'device_sha256': hashlib.sha256(data).hexdigest(),
        'simulator_tests': 'passed', 'simulator_checks': result['checks'],
        'xcode': subprocess.check_output(['xcodebuild', '-version'], text=True).strip(),
        'native_scene_resolution_verified': False, 'sustained_60fps_verified': False}
Path('build/build-info.json').write_text(json.dumps(info, indent=2) + '\n')
PY
