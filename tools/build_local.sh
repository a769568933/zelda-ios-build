#!/bin/bash
# Works with the Bash 3.2 shipped with macOS. No download or GitHub API calls.
set -euo pipefail

fail() { printf '%s\n' "$*" >&2; exit 1; }
usage() {
  printf '%s\n' 'Usage: bash tools/build_local.sh [--check | INPUT.ipa [OUTPUT.ipa]]' \
    'No IPA: compile both unsigned modules locally.' \
    'With IPA: also assemble the independent 16:9 TV adapter; keep existing controls.'
}
check_only=false
case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  --check) [ "$#" -eq 1 ] || { usage >&2; exit 2; }; check_only=true ;;
  --*) usage >&2; exit 2 ;;
esac
[ "$#" -le 2 ] || { usage >&2; exit 2; }
[ "$(uname -s)" = Darwin ] || fail 'Local iOS compilation requires macOS with full Xcode.'
for tool in xcrun xcodebuild codesign python3; do
  command -v "$tool" >/dev/null 2>&1 || fail "Missing prerequisite: $tool"
done
xcodebuild -version >/dev/null 2>&1 || fail 'Select a full Xcode installation (Command Line Tools alone is insufficient).'
sdk=$(xcrun --sdk iphoneos --show-sdk-path 2>/dev/null) || fail 'Xcode iPhoneOS SDK is unavailable.'
[ -d "$sdk" ] || fail 'Xcode iPhoneOS SDK path does not exist.'
xcrun --sdk iphoneos --find clang >/dev/null 2>&1 || fail 'Xcode iPhoneOS clang is unavailable.'
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail 'Python 3.11 or newer is required.'
if "$check_only"; then
  printf '%s\n' 'Local build prerequisites passed. No compilation was performed.'
  exit 0
fi

# Resolve arguments against the caller directory before entering the source tree.
source_ipa=''
output_ipa=''
if [ "$#" -ge 1 ]; then
  source_ipa=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$1")
  [ -f "$source_ipa" ] || fail "Input IPA does not exist: $source_ipa"
fi
if [ "$#" -eq 2 ]; then
  output_ipa=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$2")
  [ ! -e "$output_ipa" ] || fail "Output IPA already exists: $output_ipa"
fi
repo=$(cd "$(dirname "$0")/.." && pwd -P)
cd "$repo"
source_commit=local-source
source_dirty=false
if command -v git >/dev/null 2>&1 && [ "$(git rev-parse --show-toplevel 2>/dev/null || true)" = "$repo" ]; then
  source_commit=$(git rev-parse HEAD)
  [ -z "$(git status --porcelain)" ] || source_dirty=true
elif [ -f SOURCE_VERSION ]; then
  source_commit=$(cat SOURCE_VERSION)
fi
mkdir -p build
artifact=$(mktemp -d "$repo/build/local.XXXXXX")
printf 'Local build output: %s\n' "$artifact"
mode=local
[ "${GITHUB_ACTIONS:-false}" != true ] || mode=github_manual
DM_BUILD_DIR="$artifact" DM_SOURCE_COMMIT="$source_commit" DM_SOURCE_DIRTY="$source_dirty" \
  DM_BUILD_MODE="$mode" bash tools/build_modules.sh
if [ -n "$source_ipa" ]; then
  [ -n "$output_ipa" ] || output_ipa="$artifact/Game-TV16x9-Unsigned.ipa"
  python3 tools/pack_external.py "$source_ipa" "$artifact" "$output_ipa" --report "$artifact/ipa-report.json"
  printf 'Unsigned IPA: %s\n' "$output_ipa"
fi
printf 'Build complete: %s\n' "$artifact"
printf '%s\n' 'Compilation does not verify gameplay, HDMI output or sustained 60 fps.'
