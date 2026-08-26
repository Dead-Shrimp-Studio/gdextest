#!/usr/bin/env bash
# End-to-end consumer-flow check (interop regression guard).
#
# Copies this framework into a scratch consumer repo and drives the documented
# flow exactly as a real GDExtension would: `gdextest init` -> `gdextest scaffold
# --apply` (patches SConstruct, generates entry + smoke suite) -> `gdextest test`
# against the real Godot binary. Catches contract regressions like the env-var
# mismatch or TOML values being ignored — the class of bugs that only show up
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
cat > "$TMP/SConstruct" <<'EOF'
cpp_root = "#extern/gdextest/extern/godot-cpp"
env = Environment(tools=["default"])
env.SConscript(cpp_root + "/SConstruct",
               variant_dir="extern/godot-cpp/.build", duplicate=0,
               exports={"env": env})
env.Append(CPPPATH=[Dir(cpp_root + "/gen/include"), Dir(cpp_root + "/include")])
EOF

cd "$TMP"
python3 extern/gdextest/tools/gdextest.py init
python3 extern/gdextest/tools/gdextest.py scaffold --apply --godot "$GODOT"
python3 extern/gdextest/tools/gdextest.py test --godot "$GODOT" --json results.json --junit results.xml

python3 - "$GODOT" <<'PYEOF'
import json
import sys
from pathlib import Path

godot = sys.argv[1]
document = json.loads(Path("results.json").read_text(encoding="utf-8"))
totals = document["totals"]
if totals["fail"] or totals["crashed"]:
    print(f"consumer smoke: FAILED totals {totals}", file=sys.stderr)
    for result in document["results"]:
        if result["status"] in ("fail", "crashed"):
            print(f"  {result['suite']}.{result['name']}: {result['failures']}", file=sys.stderr)
    sys.exit(1)
junit = Path("results.xml").read_text(encoding="utf-8")
assert f'tests="{totals["pass"] + totals["skip"]}"' in junit, "JUnit counts mismatch"
print(f"consumer smoke: OK ({totals['pass']} passed, {totals['skip']} skipped) "
      f"against {godot}; JSON + JUnit written")
PYEOF
