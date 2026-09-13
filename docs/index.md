---
title: gdextest
description: A C++ testing framework for Godot GDExtensions: tests run inside a real, headless Godot process.
order: 1
sidebar: Basics
draft: false
---

# gdextest

Welcome to the gdextest documentation. gdextest is a C++ testing framework for Godot GDExtensions.

It runs your test suites **inside a real, headless Godot process**. You compile the framework together with your suites into one test-only shared object. A generated fixture project loads that object. The process prints a summary and exits with a pass/fail code that a CI pipeline consumes directly.

## Highlights

- **Plain C++ tests.** googletest-style registration and assertion macros (`GDEX_TEST`, `GDEX_EXPECT_EQ`, ...). No DSL and no scripting layer.
- **Real engine access.** Pure-logic tests need no engine. Tag a test `TAG_INTEGRATION` to reach singletons, `ClassDB`, and the live scene tree.
- **Async tests.** C++20 coroutines suspend across engine frames: `co_await ctx.await_frames(2)`.
- **Signal monitoring.** Watch any object's signals, count emissions, and inspect the arguments of every emission.
- **Resource checks.** Track Godot objects and `RefCounted` references. The framework fails the test when they leak.
- **One command.** `gdextest test` builds, generates the fixture, launches Godot, and returns `0` or `1`.
- **CI-friendly output.** JSON and JUnit XML, plus a clean GoogleTest-style console report rendered after the engine exits. Filtering, sharding, and shard merging are built in.
- **Zero footprint in release.** The framework compiles only into the test build. Release builds never see it.

## A 60-second example

```bash
git submodule add <this-repo-url> extern/gdextest
git submodule update --init
```

```cpp
// tests/smoke.cpp
#include "gdextest/assert.h"
#include "gdextest/registry.h"

GDEX_TEST(smoke, framework_is_wired) {
    GDEX_EXPECT(true);
}
```

```bash
./extern/gdextest/gdextest test
```

The command writes a starter config when none exists, checks the environment, builds the test library, and runs it headless. Exit code `0` means all tests passed. Exit code `1` means at least one test failed. See [Getting started](/projects/gdextest/docs/getting-started) for the full walkthrough.

## Documentation map

| Page | Read it to learn ... |
| --- | --- |
| [Getting started](/projects/gdextest/docs/getting-started) | Install the framework, write a first suite, run it, wire CI |
| [Writing tests](/projects/gdextest/docs/writing-tests) | Registration macros, tags, every assertion, teardowns, skipping, resource tracking |
| [Async tests](/projects/gdextest/docs/async-tests) | Multi-frame tests with `co_await`, waits, timeouts, and budgets |
| [Engine integration](/projects/gdextest/docs/engine-integration) | Live-engine tests and the `SignalMonitor` API |
| [Architecture](/projects/gdextest/docs/architecture) | Design goals, layering rules, the adapter system, the life of a run |
| [CLI reference](/projects/gdextest/docs/cli) | Every command and flag, exit codes, and output formats |
| [Configuration](/projects/gdextest/docs/configuration) | The full `.gdextest.toml` reference |
| [Consumer guide](/projects/gdextest/docs/consumer-guide) | End-to-end integration in another repository: build, entry, adapter, fixtures |
| [API reference](/projects/gdextest/docs/api-reference) | The complete public API, header by header |
| [Troubleshooting](/projects/gdextest/docs/troubleshooting) | Known failure modes and their fixes |

## Repository layout

| Path | Role |
| --- | --- |
| `include/gdextest/` | Public headers. This directory is the whole API surface. |
| `src/framework/` | Core implementation: registry, runner, host, signals. |
| `src/gdextest_entry.cpp` | GDExtension entry point and editor-plugin shell for the test build. |
| `src/support/adapter.cpp` | Reference adapter: trigger detection and run startup. |
| `tools/` | The `gdextest` CLI, config loading, and the fixture generator. |
| `tests/` | The framework's own suites and the consumer smoke test. |
| `gdextest` | The CLI wrapper script. |

## Requirements

- Godot **4.5**. The framework uses 4.5-only GDExtension APIs.
- SCons and a C++20 toolchain. Coroutines need C++20.
- Python 3 for the CLI.

## License

See [LICENSE](https://github.com/Dead-Shrimp-Studio/gdextension-test-framework/blob/main/LICENSE) in the repository root.
