"""Assemble a source-built touch module into one exact, locally owned IPA."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import struct
import zipfile

HOST_SHA256 = '83feb59045d1a9903890da5688ee30466029800cadb4f4b767c9246a466334c9'
LOAD_PATH = '@executable_path/Frameworks/DmPhoneControls.dylib'
APP = 'Payload/DmIOS.app/'


def commands(data):
    if len(data) < 32 or struct.unpack_from('<I', data)[0] != 0xfeedfacf:
        raise ValueError('Expected a 64-bit Mach-O image')
    if struct.unpack_from('<I', data, 4)[0] != 0x100000c:
        raise ValueError('Expected ARM64')
    count, length = struct.unpack_from('<II', data, 16)
    end = 32 + length
    if count > 10000 or end > len(data):
        raise ValueError('Truncated or invalid load commands')
    result = []; offset = 32
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError('Truncated load command')
        cmd, size = struct.unpack_from('<II', data, offset)
        if size < 8 or size % 8 or offset + size > end:
            raise ValueError('Invalid load command size')
        result.append((cmd, offset, size)); offset += size
    if offset != end:
        raise ValueError('Load-command size mismatch')
    return result


def exports(data):
    start = size = 0
    for cmd, p, _ in commands(data):
        if cmd == 0x80000033:
            start, size = struct.unpack_from('<II', data, p + 8)
        elif cmd in (0x22, 0x80000022) and not size:
            start, size = struct.unpack_from('<II', data, p + 40)
    if not size or start + size > len(data):
        raise ValueError('Missing or invalid export trie')
    trie = data[start:start + size]

    def uleb(p):
        result = shift = 0
        while p < len(trie) and shift <= 63:
            b = trie[p]; p += 1; result |= (b & 127) << shift
            if b < 128:
                return result, p
            shift += 7
        raise ValueError('Invalid export trie integer')

    names = set(); pending = [(0, '', frozenset())]; visited = 0
    while pending:
        node, prefix, parents = pending.pop(); visited += 1
        if visited > 100000 or node in parents or node >= len(trie):
            raise ValueError('Invalid export trie node')
        terminal, p = uleb(node)
        if terminal:
            names.add(prefix)
        p += terminal
        if p >= len(trie):
            raise ValueError('Truncated export trie')
        children = trie[p]; p += 1
        for _ in range(children):
            stop = trie.find(b'\0', p)
            if stop < 0:
                raise ValueError('Invalid export name')
            suffix = trie[p:stop].decode('utf-8'); p = stop + 1
            target, p = uleb(p)
            pending.append((target, prefix + suffix, parents | {node}))
    return names


def verify_host(data):
    if hashlib.sha256(data).hexdigest() != HOST_SHA256:
        raise ValueError('Unsupported host executable; use the original 20261020 Lite IPA')
    required = {'_dm_input_set', '_dm_touch_set', '_OBJC_CLASS_$_DmGamepad'}
    if not required <= exports(data):
        raise ValueError('The host does not export the required touch interface')
    if any(cmd == 0x1d for cmd, _, _ in commands(data)):
        raise ValueError('The original host must be unsigned')


def add_dylib(data):
    entries = commands(data)
    end = 32 + struct.unpack_from('<I', data, 20)[0]
    first_data = len(data)
    for cmd, p, size in entries:
        if cmd in (0xc, 0x80000018, 0x8000001f):
            relative = struct.unpack_from('<I', data, p + 8)[0]
            name = data[p + relative:p + size].split(b'\0', 1)[0]
            if name == LOAD_PATH.encode():
                raise ValueError('Touch module is already loaded')
        if cmd == 0x19:
            count = struct.unpack_from('<I', data, p + 64)[0]
            if 72 + count * 80 > size:
                raise ValueError('Invalid segment sections')
            for i in range(count):
                s = p + 72 + i * 80
                length = struct.unpack_from('<Q', data, s + 40)[0]
                offset = struct.unpack_from('<I', data, s + 48)[0]
                flags = struct.unpack_from('<I', data, s + 64)[0] & 0xff
                if length and offset and flags not in (1, 0xc, 0x12):
                    first_data = min(first_data, offset)
    name = LOAD_PATH.encode() + b'\0'; length = (24 + len(name) + 7) & ~7
    if end + length > first_data:
        raise ValueError('Insufficient header space; no executable data may move')
    if any(data[end:end + length]):
        raise ValueError('Nonzero header padding would be overwritten')
    command = struct.pack('<IIIIII', 0xc, length, 24, 0, 0x10000, 0x10000) + name
    command += bytes(length - len(command))
    result = bytearray(data); result[end:end + length] = command
    struct.pack_into('<II', result, 16, len(entries) + 1, end - 32 + length)
    return bytes(result)


def assemble(original, build_dir, output):
    original, build_dir, output = Path(original), Path(build_dir), Path(output)
    if output.exists():
        raise ValueError('Output already exists')
    library = (build_dir / 'DmPhoneControls.dylib').read_bytes()
    info = json.loads((build_dir / 'build-info.json').read_text(encoding='utf-8'))
    if info.get('device_sha256') != hashlib.sha256(library).hexdigest() or info.get('simulator_tests') != 'passed':
        raise ValueError('Missing successful simulator result or mismatched module hash')
    if struct.unpack_from('<I', library, 12)[0] != 6:
        raise ValueError('Expected a dynamic library')
    if any(cmd == 0x1d for cmd, _, _ in commands(library)):
        raise ValueError('The device module must be unsigned')
    if not {'_dm_phone_gamepad_view', '_dm_phone_gamepad_reset'} <= exports(library):
        raise ValueError('The module lacks its public control interface')
    with zipfile.ZipFile(original) as source:
        host = source.read(APP + 'DmIOS'); verify_host(host)
        plist = plistlib.loads(source.read(APP + 'Info.plist'))
        plist['CFBundleVersion'] = '1.9.2'; plist['UILaunchScreen'] = {}; plist['DMShowFPS'] = True
        manifest = dict(info, host_input_sha256=HOST_SHA256, build='iPhone-TouchControls',
                        native_scene_resolution_verified=False, sustained_60fps_verified=False,
                        display='original aspect-fit; no scene-resolution patch')
        changed = {
            APP + 'DmIOS': add_dylib(host),
            APP + 'Info.plist': plistlib.dumps(plist, fmt=plistlib.FMT_BINARY),
            APP + 'dm/env.txt': b'DM_AOC_DIR=aoc\nDM_PRESENT_LINK=1\nDM_METALFX_INTERPOLATION=0\n',
            APP + 'Frameworks/DmPhoneControls.dylib': library,
            APP + 'dm/touch-controls-build.json': json.dumps(manifest, indent=2).encode() + b'\n',
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.building.ipa')
        if temporary.exists():
            raise ValueError('An unfinished output already exists')
        try:
            with zipfile.ZipFile(temporary, 'w', allowZip64=True) as target:
                for entry in source.infolist():
                    if '/_CodeSignature/' in entry.filename or entry.filename.endswith('/embedded.mobileprovision'):
                        continue
                    content = changed.pop(entry.filename, None)
                    target.writestr(copy.copy(entry), source.read(entry) if content is None else content)
                for name, content in changed.items():
                    entry = zipfile.ZipInfo(name); entry.compress_type = zipfile.ZIP_DEFLATED
                    entry.external_attr = (0o100755 if name.endswith('.dylib') else 0o100644) << 16
                    target.writestr(entry, content)
            with zipfile.ZipFile(temporary) as check:
                bad = check.testzip()
                if bad:
                    raise ValueError('Archive CRC failed: ' + bad)
            os.replace(temporary, output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_ipa'); parser.add_argument('build_directory'); parser.add_argument('output_ipa')
    args = parser.parse_args()
    assemble(args.original_ipa, args.build_directory, args.output_ipa)
