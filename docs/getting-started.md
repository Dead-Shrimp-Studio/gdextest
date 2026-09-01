# Getting started

This page walks you from an empty repository to a green test run.

## Prerequisites

| Tool | Notes |
| --- | --- |
| Godot 4.5 binary | Any 4.5 build. The CLI discovers it automatically. Pass `--godot` to be explicit. |
| SCons | The build system. Install with `python3 -m pip install scons`. |
| C++20 toolchain | GCC, Clang, or MSVC. Coroutines need C++20. |
| Python 3 | Runs the `gdextest` CLI. |

Your repository already vendors `godot-cpp` (every GDExtension does). The framework reuses your copy. The framework submodule's own nested `godot-cpp` is used only by the framework's self-tests.

## 1. Add the framework

```bash
git submodule add <this-repo-url> extern/gdextest
git submodule update --init
```

Run every command in this guide from your repository root. The CLI is the `gdextest` script inside the submodule.

## 2. Write your first suite

Create `tests/smoke.cpp`:

```cpp
#include "gdextest/assert.h"
#include "gdextest/registry.h"

GDEX_TEST(smoke, framework_is_wired) {
    GDEX_EXPECT(true);
}
```

Suites are plain C++ files. Every test body receives a `TestContext&` named `ctx`, so the assertion macros find it by name. See [Writing tests](writing-tests.md) for the full macro set.

## 3. Run the tests

```bash
./extern/gdextest/gdextest test
```

One command does everything:

1. Writes `.gdextest.toml` when the file does not exist. It never overwrites an existing config.
2. Runs the doctor preflight: config validity, Godot, SCons, godot-cpp version, and test source discovery.
3. Builds the test library with SCons. When your `SConstruct` does not call the framework SConscript yet, the build runs through a temporary injected copy. Your build file is never modified.
4. Generates the fixture Godot project and warms its cache on the first run.
5. Launches Godot headless, runs the suites, prints the summary, and quits.
6. Removes the disposable fixture. Only the test library and your result files remain.

Exit codes: `0` all tests passed, `1` at least one failed or crashed, `2` usage or environment error.

Add `--json=results.json` for machine-readable results. See [CLI reference](cli.md).

## 4. Wire your build permanently (optional)

`gdextest test` works without touching your `SConstruct`. Two commands make the wiring permanent and generate a starting entry point:

```bash
./extern/gdextest/gdextest scaffold --apply
```

This patches `SConstruct` (a `.bak` backup is written first) and generates `testsupport/entry.cpp` plus a smoke suite from your config values. Run plain `gdextest scaffold` first to preview the changes without applying them.

## 5. Add CI

```bash
./extern/gdextest/gdextest init --ci
```

This writes `.github/workflows/gdextest.yml`. The workflow installs SCons, downloads Godot 4.5, and runs `gdextest test`. For parallel runs use shards and merge the results:

```bash
./extern/gdextest/gdextest test --shard=0/4 --json=shard0.json
./extern/gdextest/gdextest report 'shard*.json' --json=merged.json --junit=merged.xml
```

`report` exits `1` when any merged test failed, so the merge step is also a gate. See [CLI reference](cli.md) for the complete flag list and [Consumer guide](consumer-guide.md) for CI recipes.

## Where to go next

- [Writing tests](writing-tests.md) — assertions, tags, teardowns, and resource tracking.
- [Async tests](async-tests.md) — suspend a test across engine frames.
- [Engine integration](engine-integration.md) — reach the live engine and monitor signals.
- [Consumer guide](consumer-guide.md) — build wiring, adapters, custom entry points and fixtures.
