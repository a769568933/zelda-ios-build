"""Local-only independent TV configuration and IPA assembly."""
import copy
import math
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import struct
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pack_ipa import add_dylib, archive_entry, commands, exports

TV_ROLE = 'UIWindowSceneSessionRoleExternalDisplayNonInteractive'
LEGACY_TV_ROLE = 'UIWindowSceneSessionRoleExternalDisplay'
TV_DELEGATE = 'DmExternalSceneDelegate'
TV_CONFIGURATION = 'DMExternalTV'
TV_LOAD_PATH = '@executable_path/Frameworks/DmExternalDisplay.dylib'


def configure_tv(info):
    result = copy.deepcopy(info)
    manifest = result.get('UIApplicationSceneManifest')
    if not isinstance(manifest, dict):
        raise ValueError('A scene-based host is required')
    scenes = manifest.get('UISceneConfigurations')
    if not isinstance(scenes, dict) or not scenes.get('UIWindowSceneSessionRoleApplication'):
        raise ValueError('The application scene configuration is missing')
    for role in (TV_ROLE, LEGACY_TV_ROLE):
        configurations = scenes.get(role, [])
        if not isinstance(configurations, list) or any(
                not isinstance(c, dict) or c.get('UISceneDelegateClassName') != TV_DELEGATE
                for c in configurations):
            raise ValueError('An existing external display configuration must be preserved')
    scenes[TV_ROLE] = [{'UISceneConfigurationName': TV_CONFIGURATION,
                        'UISceneClassName': 'UIWindowScene',
                        'UISceneDelegateClassName': TV_DELEGATE}]
    result['DMExternalDisplayEnabled'] = True
    result['DMExternalDisplayVersion'] = '1.0'
    return result


def check_aspect(manifest):
    for key in ('requested_scene_pixels', 'default_handheld_scene_pixels'):
        if key not in manifest:
            continue
        value = manifest[key]
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError('Invalid 16:9 source dimensions')
        try:
            w, h = map(float, value)
        except (ValueError, TypeError):
            raise ValueError('Invalid 16:9 source dimensions') from None
        if not math.isfinite(w) or not math.isfinite(h) or w <= 0 or h <= 0 or abs(w / h - 16 / 9) > 1e-5:
            raise ValueError('A 16:9 source game profile is required; widescreen patches must be reverted first')
    if 'active_camera_native_aspect' in manifest:
        try:
            aspect = float(manifest['active_camera_native_aspect'])
        except (ValueError, TypeError):
            raise ValueError('Invalid 16:9 camera aspect') from None
        if not math.isfinite(aspect) or abs(aspect - 16 / 9) > 1e-5:
            raise ValueError('A 16:9 camera profile is required')


def add_external_loader(binary):
    entries = commands(binary)
    if any(command == 0x1d for command, _, _ in entries):
        raise ValueError('An unsigned host is required; use the unsigned source IPA')
    found = 0
    for command, offset, length in entries:
        if command in (0xc, 0x80000018, 0x8000001f):
            relative = struct.unpack_from('<I', binary, offset + 8)[0]
            if not 24 <= relative < length:
                raise ValueError('Invalid library load command')
            name = binary[offset + relative:offset + length].split(b'\0', 1)[0]
            found += name == TV_LOAD_PATH.encode()
    if found > 1:
        raise ValueError('The TV module is loaded more than once')
    return binary if found else add_dylib(binary, load_path=TV_LOAD_PATH)


def check_host(binary):
    if struct.unpack_from('<I', binary, 12)[0] != 2:
        raise ValueError('An ARM64 host executable is required')
    names = set()
    for command, offset, length in commands(binary):
        if command != 0x19:
            continue
        count = struct.unpack_from('<I', binary, offset + 64)[0]
        if 72 + count * 80 > length:
            raise ValueError('Invalid host sections')
        for i in range(count):
            section = offset + 72 + i * 80
            if binary[section:section + 16].split(b'\0', 1)[0] != b'__objc_classname':
                continue
            size = struct.unpack_from('<Q', binary, section + 40)[0]
            start = struct.unpack_from('<I', binary, section + 48)[0]
            if start + size > len(binary):
                raise ValueError('Invalid Objective-C class-name section')
            names.update(binary[start:start + size].split(b'\0'))
    if not {b'App', b'DmRootVC', b'DmGameView'} <= names:
        raise ValueError('Unsupported host; the App/DmRootVC/DmGameView interface is required')
    if b'DmTVSceneDelegate' in names:
        raise ValueError('The host already includes an independent TV adapter')


def checked_module(artifact):
    artifact = Path(artifact)
    binary = (artifact / 'DmExternalDisplay.dylib').read_bytes()
    info = json.loads((artifact / 'external-display-build.json').read_text())
    digest = hashlib.sha256(binary).hexdigest()
    if info.get('compile_status') != 'success' or info.get('device_sha256') != digest:
        raise ValueError('Missing compiler success or external module hash mismatch')
    entries = commands(binary)
    if struct.unpack_from('<I', binary, 12)[0] != 6 or any(c == 0x1d for c, _, _ in entries):
        raise ValueError('The external module must be an unsigned ARM64 dylib')
    if '_dm_external_display_install' not in exports(binary):
        raise ValueError('Missing external display installation interface')
    if not any(c == 0x32 and struct.unpack_from('<I', binary, p + 8)[0] == 2 for c, p, _ in entries):
        raise ValueError('An iPhoneOS device module is required, not a simulator or Mac library')
    return binary, info


def assemble_external(original, artifact, output, build_version=None):
    original, output = Path(original), Path(output)
    if output.exists():
        raise ValueError('Output already exists')
    module, compiler = checked_module(artifact)
    if build_version is not None and not re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,2}', build_version):
        raise ValueError('Invalid numeric build version')
    with zipfile.ZipFile(original) as source:
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate IPA entries are not supported')
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('Invalid IPA entry path')
        plists = [name for name in names if name.startswith('Payload/') and
                  name.endswith('.app/Info.plist') and name.count('/') == 2]
        if len(plists) != 1:
            raise ValueError('Exactly one top-level game app is required')
        plist_path = plists[0]; prefix = plist_path[:-len('Info.plist')]
        info = plistlib.loads(source.read(plist_path))
        executable = info.get('CFBundleExecutable')
        if not isinstance(executable, str) or not executable or '/' in executable or '\\' in executable or executable in ('.', '..'):
            raise ValueError('Invalid app executable name')
        host_path = prefix + executable
        host = source.read(host_path)
        check_host(host)
        for manifest in ('dm/touch-controls-build.json', 'dm/native-render-build.json'):
            if prefix + manifest in names:
                check_aspect(json.loads(source.read(prefix + manifest)))
        configured = configure_tv(info)
        if build_version is not None:
            configured['CFBundleVersion'] = build_version
        patched = add_external_loader(host)
        record = dict(compiler, host_before_sha256=hashlib.sha256(host).hexdigest(),
                      host_after_sha256=hashlib.sha256(patched).hexdigest(),
                      tv_aspect=[16, 9], tv_drawable_limit=[1920, 1080],
                      phone_controls_preserved=True, game_resolution_modified=False,
                      hdmi_device_verified=False, full_game_execution_verified=False,
                      sustained_60fps_verified=False)
        changes = {host_path: patched,
                   plist_path: plistlib.dumps(configured, fmt=plistlib.FMT_BINARY),
                   prefix + 'Frameworks/DmExternalDisplay.dylib': module,
                   prefix + 'dm/external-display-build.json': json.dumps(record, indent=2).encode() + b'\n'}
        changed_names = set(changes)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.building.ipa')
        if temporary.exists():
            raise ValueError('An unfinished output already exists')
        retained = 0
        try:
            with zipfile.ZipFile(temporary, 'w', allowZip64=True) as target:
                for entry in source.infolist():
                    if '/_CodeSignature/' in entry.filename or entry.filename.endswith('/embedded.mobileprovision'):
                        continue
                    content = changes.pop(entry.filename, None)
                    target.writestr(copy.copy(entry), source.read(entry) if content is None else content)
                for name, content in changes.items():
                    target.writestr(archive_entry(name), content)
            with zipfile.ZipFile(temporary) as check:
                if check.testzip() is not None:
                    raise ValueError('Archive CRC failed')
                for entry in source.infolist():
                    if '/_CodeSignature/' in entry.filename or entry.filename.endswith('/embedded.mobileprovision'):
                        continue
                    if entry.filename not in changed_names:
                        if source.read(entry) != check.read(entry.filename):
                            raise ValueError('An original resource changed: ' + entry.filename)
                        retained += 1
            os.replace(temporary, output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(status='passed', candidate=output.name, bytes=output.stat().st_size,
                sha256=digest,
                source_commit=compiler.get('source_commit'), unchanged_entries=retained,
                unsigned=True, hdmi_device_verified=False, full_game_execution_verified=False,
                sustained_60fps_verified=False, game_resolution_modified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_ipa'); parser.add_argument('compiled_artifact'); parser.add_argument('output_ipa')
    parser.add_argument('--build-version'); parser.add_argument('--report')
    args = parser.parse_args()
    result = assemble_external(args.source_ipa, args.compiled_artifact, args.output_ipa, args.build_version)
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
