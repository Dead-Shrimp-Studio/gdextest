#!/usr/bin/env bash
# End-to-end consumer-flow check (interop regression guard).
#
# Copies this framework into a scratch consumer repo and drives both documented
# flows exactly as a real GDExtension would, against the real Godot binary:
#   1. Unwired repo: `gdextest test` builds through a temporary injected
#      SConstruct (scons -f SConstruct.gdextest) and cleans up afterwards.
#   2. `gdextest scaffold --apply` (patches SConstruct, generates entry) then
#      `gdextest test` through the permanently wired build.
# Catches contract regressions like the env-var mismatch, TOML values being
# ignored, or the include/path handling — the class of bugs that only show up
# when the framework is used as a dependency.
#
# Usage:
#   ./tests/consumer_smoke.sh                 # uses $GODOT, then `godot` on PATH
#   GODOT=/path/to/godot ./tests/consumer_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-godot}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "consumer smoke: staging consumer repo in $TMP"
mkdir -p "$TMP/extern"
# A plain copy keeps the consumer hermetic (no symlinks into the framework repo).
cp -r "$ROOT" "$TMP/extern/gdextest"
rm -rf \
    "$TMP/extern/gdextest/.git" \
    "$TMP/extern/gdextest/bin" \
    "$TMP/extern/gdextest/build" \
    "$TMP/extern/gdextest/.sconsign.dblite" \
    "$TMP/extern/gdextest/__pycache__" \
    "$TMP/extern/gdextest/tools/__pycache__" \
    "$TMP/extern/gdextest/extern/godot-cpp/.build"

# Minimal consumer SConstruct: wires godot-cpp (from the framework's nested
# self-test-only submodule) but NOT gdextest — scaffold --apply adds that.
#
# CPPPATH/LIBPATH are deliberately root-relative strings with a name-based
# godot-cpp LIBS entry — the hand-rolled-consumer pattern. The framework
# SConscript must rebase these to the project root, or the test build's link
# fails with `cannot find -lgodot-cpp...` (SCons resolves relative paths
# against extern/gdextest/ otherwise).
cat > "$TMP/SConstruct" <<'EOF'
cpp_root = "#extern/gdextest/extern/godot-cpp"
env = Environment(tools=["default"])
env.SConscript(cpp_root + "/SConstruct",
               variant_dir="extern/godot-cpp/.build", duplicate=0,
               exports={"env": env})
suffix = env.get("suffix", "")
if not suffix:
    suffix = (f".{ARGUMENTS.get('platform', 'linux')}."
              f"{ARGUMENTS.get('target', 'template_debug')}."
              f"{ARGUMENTS.get('arch', 'x86_64')}")
env.Append(CPPPATH=[
    "extern/gdextest/extern/godot-cpp/gen/include",
    "extern/gdextest/extern/godot-cpp/include",
])
env.Append(LIBPATH=["extern/gdextest/extern/godot-cpp/bin"])
env["LIBS"] = ["godot-cpp" + suffix]
EOF

cd "$TMP"
python3 extern/gdextest/tools/gdextest.py init

# A hand-written suite so the unwired (injection) pass has a test to run;
# scaffold's own suite generation is exercised by the wired pass below.
mkdir -p tests
cat > tests/smoke.cpp <<'EOF'
#include "gdextest/assert.h"
#include "gdextest/registry.h"

GDEX_TEST(smoke, framework_is_wired) {
    GDEX_EXPECT(true);
}
EOF

# 1) Unwired repo: `gdextest test` must build through a temporary injected
#    SConstruct and pass without touching the real SConstruct.
python3 extern/gdextest/tools/gdextest.py test --godot "$GODOT" --json results-injected.json

# 2) `scaffold --apply` wires the real SConstruct permanently (keeps the
#    existing suite, generates testsupport/entry.cpp), then the wired flow runs.
python3 extern/gdextest/tools/gdextest.py scaffold --apply --godot "$GODOT"
python3 extern/gdextest/tools/gdextest.py test --godot "$GODOT" --json results.json --junit results.xml

python3 - "$GODOT" <<'PYEOF'
import json
import sys
from pathlib import Path

godot = sys.argv[1]


def check(document, label):
    totals = document["totals"]
    if totals["fail"] or totals["crashed"]:
        print(f"consumer smoke: FAILED {label} totals {totals}", file=sys.stderr)
        for result in document["results"]:
            if result["status"] in ("fail", "crashed"):
                print(f"  {result['suite']}.{result['name']}: {result['failures']}", file=sys.stderr)
        sys.exit(1)


injected = json.loads(Path("results-injected.json").read_text(encoding="utf-8"))
check(injected, "injected")
assert not Path("SConstruct.gdextest").exists(), \
    "temporary injected SConstruct must be cleaned up"
wired = json.loads(Path("results.json").read_text(encoding="utf-8"))
check(wired, "wired")
assert (Path("SConstruct").read_text(encoding="utf-8")
        .count("extern/gdextest/SConscript") >= 1), \
    "scaffold must have wired the real SConstruct"
junit = Path("results.xml").read_text(encoding="utf-8")
assert f'tests="{wired["totals"]["pass"] + wired["totals"]["skip"]}"' in junit, "JUnit counts mismatch"
print(f"consumer smoke: OK (injected {injected['totals']['pass']} passed, "
      f"wired {wired['totals']['pass']} passed) against {godot}")
PYEOF
