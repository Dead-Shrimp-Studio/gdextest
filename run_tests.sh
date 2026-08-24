#!/usr/bin/env bash
# Build the gdextest library, wire it into the fixture project, and run the
# suites headless (plan §2/§3). Exit code: 0 = all pass, 1 = failures.
#
# Usage:
#   ./run_tests.sh                 # uses $GODOT, then `godot` on PATH
#   GODOT=/path/to/godot ./run_tests.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

GODOT="${GODOT:-godot}"
PLATFORM=linux
TARGET=template_debug
ARCH=x86_64
LIB="bin/libgdx-test.${PLATFORM}.${TARGET}.${ARCH}.so"
FIXTURE="testdata/project"

# 1. Build the test library (godot-cpp static lib is reused when unchanged).
scons platform="$PLATFORM" target="$TARGET" tests=true -j"$(nproc)" >/dev/null

# 2. Wire the built library into the fixture's res://bin/.
mkdir -p "$FIXTURE/bin"
ln -sf "../../../$LIB" "$FIXTURE/bin/$(basename "$LIB")"

# 3. Hermetic user:// for the run (docs/testing/notes.md §3.1).
export XDG_DATA_HOME="$(mktemp -d)"

# 4. Run headless in editor mode (the extension hooks EditorPlugin::_ready();
#    autoloads hang under --editor — see notes.md §3.3). Flags after "--" arrive
#    as user args, where the runner parses them.
"$GODOT" --headless --editor --path "$FIXTURE" -- \
    --gdxtest-run --gdxtest-json="$ROOT/testdata/results.json"
