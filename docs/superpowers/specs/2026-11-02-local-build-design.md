# Local Xcode build

The user requests local compilation, replacing the previous GitHub-only compile
preference. Use the existing Xcode compiler commands on macOS, with a prerequisite
check and a Finder/terminal entry. Keep GitHub as source storage and manual-only
CI. No automatic upload, signing, installation, or game execution.

## Approach

Reuse one shared module compiler from local and legacy/manual CI entries rather
than maintain two compiler implementations. A local wrapper checks macOS, full
Xcode/iPhoneOS SDK and Python 3.11+, creates a fresh output directory, and may
invoke the existing local TV packer on a supplied unsigned IPA. Archive paths
with spaces work. Failure never reports success or uses stale compiler output.

The wrapper compiles both modules; optional IPA assembly adds only the TV module
and preserves the input IPA's existing controls. Current connected Linux cannot
execute Xcode. The original IPA is unavailable, so real compilation and complete
game/HDMI/60 fps acceptance remain unverified.

## Acceptance

Local scripts pass shell checks. Prerequisite failure creates no build output;
the check-only mode does not compile. Compiler failure stops assembly. Portable
tests remain green, with the unavailable original-host test explicitly skipped.
GitHub workflow has only workflow_dispatch. Deliver a source/build ZIP without
game binaries, keys, private data or previously cloud-built libraries.
