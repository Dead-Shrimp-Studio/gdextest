# gdextest documentation

This folder is the full reference for the gdextest GDExtension testing framework. For a
5-minute getting-started read, see the [project README](../README.md) instead.

## What gdextest is

A C++ testing framework for Godot GDExtensions that runs your suites **inside a headless
Godot binary**. You compile the framework into a test-only shared object, load it through a
fixture Godot project, and run `godot --headless`. The process prints a summary (human or
JSON), and its exit code is your pass/fail signal — which is exactly what a CI pipeline
wants.

- Suites are plain C++ using googletest-style macros (`GDX_TEST`, `GDX_EXPECT_*`).
- Pure-logic tests need no engine at all; engine-facing tests run inside a real Godot
  process with live singletons and your extension's registered classes. (Test bodies
  receive only a `TestContext&`; scene-tree access is not exposed to bodies yet.)
- The framework core is a pure C++ library with no Godot types — only the runner touches
  the engine boundary.

## Status

Working and verified on Godot **4.5** (Linux x86_64): framework core, sync runner, human +
JSON reporting, filtering/sharding/shuffling, the reference fixture, headless execution
(15 self + reference tests green, exit 0), and the reusable consumer `SConscript` wiring
(this repo's `SConstruct` is the reference consumer of it). Not yet built: async/multi-frame
tests and object leak/UAF tracking (stubs only). See
[.plans/gdextension-testing-framework.md](../.plans/gdextension-testing-framework.md) for
the milestone plan.

## Doc map

| Doc | Read it to understand… |
| --- | --- |
| [architecture.md](architecture.md) | How the framework fits together: layers, execution model, design rules, lifecycle of a run |
| [api-reference.md](api-reference.md) | The complete public API: registration macros, assertions, `TestContext`, `Filter`, tags, runner entry points |
| [cli.md](cli.md) | Invocation, `--gdxtest-*` flags, exit codes, and the human/JSON output formats |
| [consumer-guide.md](consumer-guide.md) | How another extension repo integrates gdextest (adapter, entry, fixture, build, CI) |
| [testing/notes.md](testing/notes.md) | Verified engine facts: headless quit codes, safe hook points, `user://` hermeticity, timing gotchas |

## Related

- [README](../README.md) — quickstart.
- [.plans/gdextension-testing-framework.md](../.plans/gdextension-testing-framework.md) —
  milestone plan and open questions.
