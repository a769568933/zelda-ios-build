# Local build and assemble

Local macOS compilation is the default. Requirements: full Xcode selected as
the active developer directory, its iPhoneOS SDK, and Python 3.11+. Command Line
Tools alone cannot build UIKit for iPhone. No signing credentials are needed.

From a terminal in this directory:

```sh
bash tools/build_local.sh --check
bash tools/build_local.sh
```

You may also double-click `Build-Local.command` in Finder. If executable bits
were lost during ZIP extraction, use the terminal command above. The check-only
mode performs no compilation. Each build creates a fresh `build/local.XXXXXX/`
directory; a failed run exits nonzero and never assembles using an old module.
Paths containing spaces are supported, including invocation outside this directory.

The output contains `DmPhoneControls.dylib`, `build-info.json`,
`DmExternalDisplay.dylib` and `external-display-build.json`, plus object files.
Metadata identifies the source, dirty state, compiler and module hashes. It does
not label compilation as simulator, game or hardware acceptance.

To compile and then assemble independent TV output locally:

```sh
bash tools/build_local.sh "/path/Current-Unsigned.ipa" "/path/TV16x9-Unsigned.ipa"
```

The input must be a compatible scene-based unsigned 16:9 host. The second
argument is optional; its default is `Game-TV16x9-Unsigned.ipa` in the new build
directory. Existing output files are rejected. `ipa-report.json` records resource
and archive verification. This adds the external module and preserves the input
IPA's existing controls; the separately compiled touch module is not installed
by this TV packer. No signing, installation or game execution is performed.

Portable checks (Linux or Mac) use:

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v
cc -std=c11 -Wall -Wextra -Werror -pedantic -Isrc tests/t_external_geometry.c -lm -o /tmp/t_external_geometry
/tmp/t_external_geometry
cc -std=c11 -Wall -Wextra -Werror -pedantic tests/t_touch_motion.c -lm -o /tmp/t_touch_motion
/tmp/t_touch_motion
```

Local build CLI tests substitute Apple compiler tools to test orchestration;
they do not compile iOS code. The original-host test is skipped unless the
private `ZELDA_ORIGINAL_IPA` input is supplied locally.

## Manual GitHub fallback

The workflow has only `workflow_dispatch`; source pushes no longer start builds.
Do not dispatch it for the default local workflow. `tools/build_cloud.sh` is a
compatibility alias for the local entry and contains no remote dispatch.

The optional independent TV module and its local packer are described in
[docs/EXTERNAL_DISPLAY.md](docs/EXTERNAL_DISPLAY.md). The compile artifact
includes both unsigned modules and separate compiler metadata. The TV UIKit
fixture is compiled only; no UIKit/simulator/game tests run in GitHub.

The optional manual cloud job only compiles the open-source modules. Analysis, portable
tests, compiled-component checks, packaging and validation run locally. The repository contains no game executable,
assets, keys, saves, or shaders. The device module and final game IPA are
unsigned. No simulator or private candidate validation is run in GitHub.

The module replaces initialization, layout and reset of the old exported
`DmGamepad` class with a container holding the new `DmPhoneGamepad` view.
It sends input through the existing exported `dm_input_set` and
`dm_touch_set` interfaces. The host's rendering, launch settings and shader
libraries are retained. The local packer checks the exact original host hash
and its real export trie before adding one load command in unused header
padding; no original code or game module is moved or rewritten.

For an explicitly requested manual Actions run, download `iphone-touch-controls`
and locate its `local.XXXXXX` directory with the unsigned dylibs and metadata.
The current compiler-only artifact
records simulator tests as not run; it must not be presented as simulator
validated. Validate the returned module locally before using the project's
local packer. The original public packer below describes the older
simulator-validated artifact format and rejects the new format:

```sh
python tools/pack_ipa.py ORIGINAL-20261020-Lite.ipa downloaded-artifact New-TouchControls-Unsigned.ipa
```

The packer requires the original executable SHA-256
`83feb59045d1a9903890da5688ee30466029800cadb4f4b767c9246a466334c9`.
It refuses existing output files, unknown hosts, signed device modules,
missing simulator success, changed module hashes, or insufficient header space.
It preserves the app's bundle ID and original aspect-fit rendering and adds
`UILaunchScreen` so the controls use native iPhone view geometry. The earlier
fullscreen candidate reported as stretched is not the packaging input.

This is a touch-control test build. It does not implement native 2622 x 1206
scene rendering or sustained 60 fps. Real-device input feel, controller
handoff, safe-area placement and nested-module signing by a sideloading tool
still require testing. Simulator checks use a minimal host with the same
public input interface, not the private game executable.

Sources copied from `seedds/nxnative` at
`4f0b555e75caf1f88cd84dda85c1859418e24a46`, with the owner's requested touch
changes. See LICENSE for the upstream MIT notice.

