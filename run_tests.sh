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
FIXTURE="build/gdxtest/project"

# Compatibility wrapper. The first-class CLI owns build, fixture generation,
# Godot discovery, hermetic user data, and result handling.
exec "$ROOT/gdxtest" test --godot "$GODOT" --json "$ROOT/testdata/results.json"
