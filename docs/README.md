# gdextest documentation

This folder is the full reference for the gdextest GDExtension testing framework. For a
5-minute getting-started read, see the [project README](../README.md) instead.

## What gdextest is

A C++ testing framework for Godot GDExtensions that runs your suites **inside a headless
Godot binary**. You compile the framework into a test-only shared object, load it through a
fixture Godot project, and run `godot --headless`. The process prints a summary (human or
JSON), and its exit code is your pass/fail signal — which is exactly what a CI pipeline
wants.

- Suites are plain C++ using googletest-style macros (`GDEX_TEST`, `GDX_EXPECT_*`).
- Pure-logic tests need no engine at all; engine-facing tests run inside a real Godot
  process. Tag a test `TAG_INTEGRATION` and include `framework/engine.h` to reach the live
  `SceneTree` from its `TestContext` — singletons, `ClassDB`, and scene-tree structure.
- The framework core is a pure C++ library with no Godot types — only the engine-boundary
  headers (`runner.h`, `engine.h`) touch Godot.

## Status

Working and verified on Godot **4.5** (Linux x86_64): framework core, sync runner, human +
JSON reporting, filtering/sharding/shuffling, usage-error exit code 2, live-engine
integration tests, **async / multi-frame tests** (`GDEX_TEST_ASYNC` + `co_await
ctx.await_frames/await_timer_ms`, driven by a `process_frame` pump with per-wait and
per-test timeouts), the reference fixture, headless execution (35 self + reference +
integration + async tests green, exit 0), and the reusable consumer `SConscript` wiring
(this repo's `SConstruct` is the reference consumer of it). Not yet built: object
leak/UAF tracking (stubs only) and flaky retry. See
[.plans/gdextension-testing-framework.md](../.plans/gdextension-testing-framework.md) for
the milestone plan.

## Doc map

| Doc | Read it to understand… |
| --- | --- |
| [architecture.md](architecture.md) | How the framework fits together: layers, execution model, design rules, lifecycle of a run |
| [api-reference.md](api-reference.md) | The complete public API: registration macros (incl. `GDEX_TEST_ASYNC`), assertions, `TestContext` (incl. `await_frames`/`await_timer_ms`), `Filter`, tags, runner entry points |
| [cli.md](cli.md) | Quickstart lifecycle, automatic config initialization, doctor preflight, invocation, flags, exit codes, and output formats |
| [consumer-guide.md](consumer-guide.md) | How another extension repo integrates gdextest (adapter, entry, fixture, build, CI) |
| [testing/notes.md](testing/notes.md) | Verified engine facts: headless quit codes, safe hook points, `user://` hermeticity, timing gotchas |

## Related

- [README](../README.md) — test-first quickstart and integration overview.
- [.plans/gdextension-testing-framework.md](../.plans/gdextension-testing-framework.md) —
  milestone plan and open questions.
