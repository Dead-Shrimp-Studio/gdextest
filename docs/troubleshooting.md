---
title: "Troubleshooting"
description: "Known failure modes and their fixes."
order: 100
sidebar: "Reference"
draft: false
---

# Troubleshooting

Known failure modes and their fixes. Run `gdextest doctor` first for most of these; it names the broken piece.

## Build and link problems

### `undefined symbol: ...` when Godot loads the test library

Your suite calls code that is not compiled into the test build. The dynamic linker only complains when Godot opens the `.so`, but the CLI runs `ldd -r` right after the build and fails fast with the symbol list.

1. Check the source patterns in `.gdextest.toml`. `gdextest doctor` prints every pattern with its match count, for example `test sources: 2 (tests/**/*.cpp -> 1, src/**/*.cpp -> 0)`.
2. Patterns are repo-root relative. `src/**/*.cpp` reaches nothing when the sources live in a subdirectory; spell the path from the repository root.
3. Vendored C dependencies (`.c` files) need their own pattern. A `*.cpp` glob does not match `.c` files; use `**/*.c` or list the directory.
4. A TOML typo can silently shrink the pattern set. A missing closing quote is now a parse error with `file:line` context, so check the doctor output for parse errors too.

### `Two environments with different actions were specified for the same target`

Your own `SConstruct` compiles the same sources the test library compiles, and the object paths collided. Current framework versions compile every test-library object under `build/gdextest/obj/`, mirroring the source layout. Update the `extern/gdextest` submodule to pick this up.

### `cannot find -lgodot-cpp...`

Your `SConstruct` sets `CPPPATH` / `LIBPATH` with root-relative strings. The framework SConscript rebases those paths to your project root automatically. If you compile the framework sources yourself (bypassing the SConscript), anchor the paths with `#` (`#extern/godot-cpp/bin`, `#src`), the godot-cpp convention, so they resolve from any directory.

### Link errors about exceptions (`-fno-exceptions`)

The SConscript adds `-fexceptions` (or `/EHsc` on MSVC) to the test target. If you compile the framework sources without the SConscript, add the flag to the test target's `CXXFLAGS` yourself.

## Configuration problems

### `sources pattern matched no C++ files`

A configured pattern matched nothing. This is a hard error before the build. Fix the pattern, or remove it. See the undefined-symbol section above for the common causes.

### TOML parse errors (`unterminated string`, `unterminated array`)

The parser rejects malformed values with `file:line` context instead of guessing. Close the quote or bracket. Arrays may span multiple lines; `#` comments are honored outside quoted strings.

### Configuration key ignored

Check the key name against [Configuration](/projects/gdextest/docs/configuration). Flat legacy keys still work, but the structured sections are the documented form. Remember the precedence order: SConscript export, then CLI environment variables, then the TOML, then defaults.

## Editor and fixture problems

### Editor hangs on `--headless --editor`

The run never triggered. Check, in order:

1. `--gdextest-run` is present after `--`, or `GDX_RUN_TESTS` is set in the environment.
2. The fixture enables the plugin: `[editor_plugins]` in the fixture's `project.godot` (generated; check with `--keep-fixture`).
3. The `.gdextension` manifest's `entry_symbol` matches your entry function.

### Editor crashes on shutdown

The run started before the editor's first filesystem scan finished. The generated plugin script already waits for `is_scanning()`. If you maintain a custom fixture, keep that wait (see [Consumer guide](/projects/gdextest/docs/consumer-guide#10-create-a-custom-fixture-project-optional)).

### Godot errors about a manifest or library name you no longer use

Stale generated files from an older config. Current versions recreate the fixture fresh each run and remove stale files defensively. Run `gdextest clean` to clear the remaining build output.

### `Script inherits from native type ... can't be assigned to EditorPlugin`

The plugin script must extend `EditorPlugin` directly, not your native plugin class. The fixture generator emits the right script; only custom fixtures hit this.

### Random abort on the very first run in a fresh checkout

Godot 4.5's first headless-editor run on a cold project cache can abort during shutdown. The CLI detects the cold cache and runs one warmup pass first, so this should not reach you. If you invoke Godot manually against a fresh fixture, run it once with `--quit-after 2` before the real run.

## Test behavior problems

### `gdextest list` prints nothing

Listing needs a run trigger. The CLI's `list` command builds and starts Godot, but the runner stays idle without `--gdextest-run`:

```bash
./extern/gdextest/gdextest list --gdextest-run
# or
GDX_RUN_TESTS=1 ./extern/gdextest/gdextest list
```

### Where did my test output go?

`gdextest test` captures everything the Godot process prints, renders the GoogleTest-style report after the engine exits, and discards Godot's own chatter (banner, import and load messages) by default. If you expected engine output:

1. `--verbose` echoes the full captured engine output after the report.
2. `--gdextest-raw-log=<path>` (or `[gdextest.test]` `raw_log` in `.gdextest.toml`) writes it verbatim to a file.
3. A failed run appends the last engine lines as `gdextest: godot output (tail)` automatically.
4. Driving Godot directly bypasses all of this: the runner's lines appear with a `GDX_TEST_OUTPUT:` prefix, with no CLI report.

### Exit code `2` with a message about an option

Usage errors exit `2`: a malformed value (`--gdextest-shard=xyz`), a shard outside `[0, n)`, or an unknown `--gdextest-*` option. The message names the offending option. Check the flag spelling against [CLI reference](/projects/gdextest/docs/cli).

### Async test fails with `timed out`

The wait never resolved within its deadline. Either the awaited condition never happens (fix the test), or the budget is too small for the machine (raise `[gdextest.test] timeout_ms` or `isolate_timeout_sec` in `.gdextest.toml`).

### Async test fails with `isolate`

The whole test exceeded the per-test budget while each wait stayed under the per-wait timeout. Shorten the waits or raise `isolate_timeout_sec`.

### `co_await ... used outside an async test run`

The body awaits in a plain `GDEX_TEST`, or no pump is active. Register with `GDEX_TEST_ASYNC` and end the body with `co_return;`.

### A compiler error inside a test body mentions `return` in a coroutine

Coroutine bodies must use `co_return;`. A bare `return;` does not compile.

### Skipped tests show up as `pass` in a naive CI summary

Read the JSON `totals` (`pass`, `fail`, `skip`, `crashed`) instead of the exit code alone, or use the JUnit output, which marks skips explicitly.

### Retried test still fails after `flaky_retries` attempts

`TAG_FLAKY` retries paper over timing, not real bugs. The JSON `retries` field shows the attempts used. Fix the test or drop the tag so the failure stays visible.

## Debugging tools

- `gdextest doctor --godot /path/to/Godot` — environment diagnostics without a build.
- `gdextest test --keep-fixture` — keep the generated fixture when the run fails, so you can open or re-run it.
- `--json=results.json` — exact per-test status, duration, retries, and failure file/line/message.
- `--gdextest-raw-log=godot.log` — Godot's captured output verbatim, for debugging the engine side of a run.
- `godot --headless --editor --path build/gdextest/project -- --gdextest-run` — re-run the kept fixture by hand with full engine output.
