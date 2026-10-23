# Build and assemble

The cloud job only compiles the open-source touch module. Analysis, portable
tests, compiled-component checks, packaging and validation run locally. It contains no game executable,
assets, keys, saves, or shaders. The device module and final game IPA are
unsigned. No simulator or private candidate validation is run in GitHub.

The module replaces initialization, layout and reset of the old exported
`DmGamepad` class with a container holding the new `DmPhoneGamepad` view.
It sends input through the existing exported `dm_input_set` and
`dm_touch_set` interfaces. The host's rendering, launch settings and shader
libraries are retained. The local packer checks the exact original host hash
and its real export trie before adding one load command in unused header
padding; no original code or game module is moved or rewritten.

After a successful Actions run, download `iphone-touch-controls` and unpack
the unsigned dylib and compiler metadata. The current compiler-only artifact
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
