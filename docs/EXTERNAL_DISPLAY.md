# Independent HDMI / TV output

The optional `DmExternalDisplay.dylib` presents the existing Metal game view
in a separate, noninteractive 16:9 TV scene. The phone keeps its controls and
keyboard ownership. Disconnecting restores the same renderer and layer to
the phone. A TV can connect before the game view is created.

The drawable is capped at 1920x1080. A 4K TV scales this output; displays of
other shapes receive an aspect-fit picture. Game internal resolution and the
phone's current rendering profile are preserved. This does not provide a
native 4K game renderer or certify sustained 60 FPS.

The adapter uses the original host's `App`, `DmRootVC` and `DmGameView`
Objective-C interfaces. It registers a scene accessory on iOS 27 through
runtime selectors, including when compiled with an older SDK. On earlier iOS
versions the added external scene configuration supplies the entry point.
The existing application scene configuration remains intact. Hosts already
containing upstream's `DmTVSceneDelegate` are rejected; use their native TV
support instead of installing a second adapter.

## Build and package

The default is local macOS/Xcode compilation (see [BUILD.md](../BUILD.md)).
GitHub automatic builds are disabled. Compile and assemble in one command:

```sh
bash tools/build_local.sh Current-Unsigned.ipa Zelda-TV16x9-Unsigned.ipa
```

Alternatively compile without arguments, then use the new build directory
with the Python 3.11+ packer:

```sh
python3 tools/pack_external.py Current-Unsigned.ipa build/local.ABCDEF Zelda-TV16x9-Unsigned.ipa --report tv-package-report.json
```

The packer accepts a compatible scene-based 16:9 source IPA. It preserves the
bundle identifier, primary scene, existing controls, game data and render
configuration. It adds the external library/load command and scene config,
checks resource identity and ZIP CRC, and refuses signed hosts/modules,
known widescreen profiles, conflicting native TV configuration, nonzero
header padding and existing output files. An existing installation of this
adapter can be upgraded without adding another load command. The optional
`--build-version` changes only `CFBundleVersion`.

The original public touch-only packer still expects its older simulator
metadata; use `pack_external.py` for this compile-only external artifact.

## Validation scope

Portable geometry and Python packaging tests run locally. The included
`ExternalDisplayHarness.m` checks session-level UIKit reparenting, same-layer
identity, scale restoration, control placement and zero-size targets on a
local Apple UIKit host. The build scripts compile that fixture without executing it.
It does not cover a physical cable/TV, real iOS 27 scene activation, the full
swizzled-host lifecycle or GPU frame pacing. Those require device acceptance.

No existing game IPA is stored in this repository. A compiled adapter and
passing synthetic packaging tests are not a newly assembled game IPA.
