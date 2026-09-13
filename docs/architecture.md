---
title: Architecture
description: Design goals, layering rules, the adapter system, and the life of a run.
order: 60
sidebar: Reference
draft: false
---

# Architecture

This page explains how gdextest is built and why. Read it when you want to change the framework, write a custom adapter or entry point, or understand what happens during a run.

## Design goals

- **One command, one signal.** A consumer runs `gdextest test` and reads an exit code. No runner binary, no second build system, no output parsing to decide pass/fail.
- **Tests run inside the engine.** Engine behavior (singletons, scene tree, signals) is testable directly, because the suites execute in the engine's own process and thread.
- **No footprint in release.** The framework, the entry point, and the suites compile only when `GDEXTEST_ENABLED` is defined. Release builds never include them.
- **Simple to adopt.** The framework rides in as a submodule, reuses the consumer's `godot-cpp`, and works without modifying the consumer's `SConstruct`.

## The execution model

Suites register themselves in a static registry when the test shared object loads. The fixture Godot project enables an editor plugin that instantiates a native host node. The adapter checks for a run trigger, bootstraps host services, and hands the live tree node to the runner. The runner parses the `--gdextest-*` options, selects tests, runs them (sync bodies inline, async bodies through a frame pump), writes the JSON results document, reports a marker-prefixed summary (`GDX_TEST_OUTPUT:` lines — quiet by default, `--gdextest-report=pretty` restores the human layout), and quits the engine with a status code. The CLI renders the human report from the JSON after the engine exits.

```text
your suites -> framework core (registry, asserts) -> runner (engine-facing)
                                                        ^
                 adapter calls run_all_and_quit(node) --+

godot binary --headless <- fixture project (plugin enables) <- adapter + entry
```

## Layering rules

1. **No Godot types in static initializers.** The registry, the test model, and the coroutine machinery are pure C++ (`std::string`, `std::vector`, function-local statics). Registration happens at library load time, and Godot objects must not be touched before initialization.
2. **Godot types stay in a small engine boundary.** The core (`registry.cpp`, `context.h`, `assert.h`, `async.h`, `config.h`) is plain C++. Godot types appear only in the engine-boundary files: `runner.h` with `runner.cpp`, `engine.h`, `strings.h`, `signals.h` with `signals.cpp`, `adapter.h`, and the entry/adapter sources.
3. **The core speaks `std::string`.** Failures, skip reasons, and value formatting are `std::string` end to end. `godot::String` converts to UTF-8 at the boundary (`strings.h`) and nowhere else.
4. **Assertions record; they do not throw.** A failing expectation appends a `Failure` to the test's `TestContext` and execution continues. Only `GDEX_ABORT_TEST` and `GDEX_SKIP` throw private exception types, and the runner catches both inside its own frame. Nothing crosses an engine callback boundary.
5. **The runner is single-threaded.** Sync tests run inline, one after another. Async tests are coroutines resumed by a `process_frame` pump, one test at a time in declaration order.

## The adapter system

Adapters are extension-specific hooks around the test run. The framework supports any number of them.

### The `ExtensionAdapter` interface

```cpp
struct MyAdapter : public gdextest::ExtensionAdapter {
    void on_initialize(godot::ModuleInitializationLevel level) override;
    void on_uninitialize(godot::ModuleInitializationLevel level) override;
    void on_ready(godot::Node *tree_node) override;
};

GDEX_REGISTER_ADAPTER(MyAdapter)
```

All three callbacks default to no-ops, so an adapter overrides only what it needs.

### Dispatch points

| Callback | Fired by | When |
| --- | --- | --- |
| `on_initialize` | `AdapterRegistry::dispatch_initialize` | Each GDExtension initialization level, in registration order. |
| `on_uninitialize` | `AdapterRegistry::dispatch_uninitialize` | Each uninitialization level, in reverse order (LIFO). |
| `on_ready` | `AdapterRegistry::dispatch_ready` | Once, right before a triggered run starts, with the host node. |

### The run trigger path

The reference adapter in `src/support/adapter.cpp` implements the contract `gdextest_adapter::maybe_run(godot::Node*)`:

1. Check the trigger: the `GDX_RUN_TESTS` environment variable, or `--gdextest-run` in either of Godot's two command-line argument lists.
2. Without a trigger, return immediately. The extension loads but nothing runs.
3. With a trigger, dispatch `on_ready` to all adapters, call `bootstrap_host()` (the `gdextest/host.h` callbacks), and call `run_all_and_quit(tree_node)`.

Replace the adapter through the SConscript's `adapter` export when your extension needs different startup. The declaration in `adapter.h` keeps the contract compile-checked.

## Lifecycle of a test run

From a consumer repository, `gdextest test` performs a CLI preflight before the engine lifecycle ever starts:

1. **Preflight.** Write the starter config when `.gdextest.toml` is missing. Run the doctor checks. A failed check returns `2` before SCons starts.
2. **Build.** Run SCons (`tests=true`, plus `[gdextest.build] args`). The framework core, the entry point, the adapter, and all configured suite sources compile into one shared object with `GDEXTEST_ENABLED` defined. When the consumer's `SConstruct` does not call the framework SConscript, the build runs through a temporary injected copy (`SConstruct.gdextest`) that is deleted afterwards. On Linux an `ldd -r` pass reports unresolved symbols before Godot ever loads the library.
3. **Load.** The fixture project's `project.godot` lists the test library under `[native_extensions]`. Godot loads it and calls the entry symbol, which registers the editor plugin class and `SignalMonitor` at the editor initialization level.
4. **Enable.** The fixture enables the plugin. The generated plugin script waits for `EditorFileSystem.is_scanning()` to become false, then instantiates the native plugin node. Quitting during the first scan races the scan thread and can crash the editor, so the wait is mandatory.
5. **Trigger.** The native plugin's `_ready()` calls `gdextest_adapter::maybe_run(self)`. The adapter checks the trigger, dispatches `on_ready`, bootstraps the host, and calls the runner.
6. **Run.** The runner parses the `--gdextest-*` options from the user argument list, applies the runtime budgets, and selects tests (filter, shard, shuffle). Sync bodies run inline with a fresh `TestContext` each. Async bodies suspend and resume across `process_frame` ticks.
7. **Report.** After the last test, the runner prints the human summary, writes the JSON document when `--gdextest-json=` was given, and calls `shutdown_host()`.
8. **Exit.** `SceneTree::quit(code)` maps to the process exit code: `0` all passed, `1` any failure or crash, `2` usage error.
9. **Clean up.** The CLI removes the disposable fixture project and resets the hermetic `user://` directory for the next run.

## Determinism and time bounds

- Tests run in declaration order unless `--gdextest-shuffle` is set. Shuffling uses a seeded LCG with Fisher-Yates, so a fixed seed reproduces the order.
- Sharding hashes `suite` and `name` (FNV-1a), so a test always lands in the same shard. Shards are disjoint and complete.
- Async tests run one at a time. The pump never interleaves two bodies.
- Every async wait carries a deadline; every test carries an isolate budget. A stalled test fails with a message; it never hangs the run.
- `user://` is hermetic: the CLI points `XDG_DATA_HOME` at a wiped per-run directory, because Godot 4.5 has no user-data-dir flag.

## Key design decisions

| Decision | Rationale |
| --- | --- |
| `TestContext&` injected into every body | No global state for suites; the runner owns the context, and abort/skip still reach the active context through a framework-internal pointer. |
| Failures recorded, not thrown | One test reports all failing checks. Nothing propagates across engine callbacks. |
| Static registration in a pure C++ registry | Registry order never depends on engine state. Godot objects are untouchable at load time. |
| `Filter` mirrors googletest glob grammar | Familiar globs with negatives; matches `suite.name`, the suite, or the name. |
| Stable-hash sharding | The same test always lands in the same shard. CI parallelism stays reproducible. |
| Seeded shuffle | Reproducible randomized order for finding order-dependent bugs. |
| `TAG_FLAKY` retries | Explicitly tagged tests get up to `flaky_retries` extra attempts; ordinary failures stay visible. |
| Resource tracking by instance ID and refcount | Leaks fail the test at teardown without dereferencing stale pointers. |
| Coroutines instead of threads for async tests | Bodies suspend on the main thread and resume on engine frames. No locks, no off-thread engine calls. |
| Teardowns before leak checks | A teardown can free what `track_object` watches, so cleanup order is never a trap. |
| Disposable fixture project | The fixture is generated per run and removed after. Stale manifests and libraries from earlier configs cannot linger. |

## Verified engine facts the framework leans on

The design depends on these behaviors, all exercised continuously by the framework's own suites:

- `SceneTree::quit(code)` propagates to the process exit code under `--headless`.
- `OS::set_exit_code` is not exposed by godot-cpp 4.5, so `quit()` is the only exit path.
- Trigger detection must check both `OS::get_cmdline_args()` (before `--`) and `OS::get_cmdline_user_args()` (after `--`).
- `user://` hermeticity needs `XDG_DATA_HOME`; Godot 4.5 has no user-data-dir flag.
- The editor plugin's `_ready()` fires before the first filesystem scan finishes. The run must wait for `is_scanning()` to become false.
- `SceneTree.process_frame` fires under both `--headless` and `--headless --editor` and carries no arguments. The async pump drives on it.
- Godot 4.5's first headless-editor run on a cold project cache can abort during shutdown. The import finishes before the abort, so one warmup pass makes the following run deterministic.

## Repository layout

| Path | Role |
| --- | --- |
| `include/gdextest/` | Public headers. Suites include only these. |
| `src/framework/` | Core implementation: `registry.cpp`, `runner.cpp`, `host.cpp`, `signals.cpp`. |
| `src/gdextest_entry.cpp` | GDExtension entry point plus the editor-plugin shell (test build only). |
| `src/support/adapter.cpp` | Reference adapter: trigger check, adapter dispatch, run start. |
| `tools/gdextest.py` | The CLI: commands, doctor, build driving, result merging. |
| `tools/gdextest_config.py` | TOML loading, source discovery, Godot discovery, validation. |
| `tools/generate_fixture.py` | Fixture project generator (editor and runtime host modes). |
| `SConscript` | Reusable build wiring consumers call from their `SConstruct`. |
| `tests/` | The framework's own suites, plus the consumer smoke test. |
| `run_tests.sh` | Compatibility wrapper around `gdextest test` for this repository. |
