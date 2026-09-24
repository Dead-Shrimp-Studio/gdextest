#!/usr/bin/env bash
# Build the gdextest library, wire it into the fixture project, and run the
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
LIB="bin/libgdextest.${PLATFORM}.${TARGET}.${ARCH}.so"
FIXTURE="build/gdextest/project"

# Compatibility wrapper. The first-class CLI owns build, fixture generation,
# Godot discovery, hermetic user data, and result handling.
exec "$ROOT/gdextest" test --godot "$GODOT" --json "$ROOT/testdata/results.json"
