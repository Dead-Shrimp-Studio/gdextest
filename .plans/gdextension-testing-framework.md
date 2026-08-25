# GDExtension testing framework — plan

## Goal (one sentence)

A framework that other GDExtension developers **pull into their own repo** to test their
extension inside a **headless Godot binary**: build once, run `godot --headless`, get
pass/fail on the exit code.

## Status (current)

This repo is a working reference implementation of the framework, verified green on Godot
**4.5** (Linux x86_64). The pure C++ core, sync runner, fixture project, headless execution,
docs, and the reusable consumer `SConscript` are all in place and run **15/15 tests green**
(exit 0). The build is fixed, the fixture project exists, docs are complete, plans are tracked
in git, and a CI pipeline runs the whole suite on every push.

### Delivered (M0 → M5)

| Piece | Location | Status |
| ----- | -------- | ------ |
| M0 engine-fact verification (headless quit codes, safe hook points, `user://` hermeticity) | `docs/testing/notes.md` | ✅ |
| Pure C++ test core: registry, filter/shards/shuffle, `TestContext`, assertions | `src/framework/` | ✅ self-tested |
| Sync runner: flag parsing, human + JSON output, `SceneTree::quit(code)` exit | `src/framework/runner.cpp` | ✅ |
| GDExtension entry: `EditorPlugin` shell + `gdx_test_library_init` | `src/gdx_test_entry.cpp` | ✅ |
| Host adapter pattern (trigger, bootstrap, `maybe_run`) | `src/support/adapter.cpp` | ✅ |
| Self-tests + two host suites (15 tests) | `tests/` | ✅ |
| Fixture project (project.godot, `.gdextension`, plugin wrapper) | `testdata/project/` | ✅ |
| Run script (build + wire + hermetic run) | `run_tests.sh` | ✅ |
| Reusable consumer `SConscript` | root `SConscript` | ✅ |
| Docs: README, api, cli, consumer guide, engine notes | `docs/`, `README.md` | ✅ |
| CI pipeline (build → headless run → JSON artifact) | `.github/workflows/ci.yml` | ✅ |
| Plan tracked in git | `.plans/` | ✅ |

### Verified behavior

- `scons platform=linux target=template_debug tests=true` → `bin/libgdx-test….so`
  (statically links godot-cpp, exports `gdx_test_library_init`).
- `godot --headless --editor --path testdata/project -- --gdxtest-run` → **15 passed, 0 failed**,
  exit 0. Deliberate failure → exit 1; `--gdxtest-filter=counter.*` → 4 tests;
  `--gdxtest-run --gdxtest-list` → 15 listed; JSON totals correct; repeat runs stable.
- `run_tests.sh` wires the built library into `testdata/project/addons/gdxtest/bin/`
  (the path the `.gdextension` manifest loads from) and points `XDG_DATA_HOME` at a temp dir.

## Decisions (resolved)

1. **Consumers pull the framework in as a git submodule** (`extern/gdextest`), matching the
   existing `extern/godot-cpp` pattern. The framework ships the whole repo; hosts provide the
   adapter + fixture project. The root `SConscript` resolves the framework root itself, so the
   consumer-side call inside the host's `SConstruct` is clean (see `docs/consumer-guide.md` §6).
2. **The framework core stays in `src/` in this repo** (reference host layout). Consumers
   reference the shipped files via the submodule path; the `gdxtest` exports dict selects which
   host files to compile. No separate `framework/` tree is needed.
3. **Plans are tracked in git.** `.plans/` is no longer gitignored, so this document survives a
   fresh checkout and records the rationale for each milestone.

## Near-term roadmap (next)

Each item ends with something runnable/verifiable.

- [x] **M1 — Core + sync runner**: registry, assertions, runner, `tests=true`, self + host suites.
- [x] **M2 — Fixture project + headless run**: `testdata/project/`, plugin wrapper, `run_tests.sh`.
- [x] **M3 — Docs + consumer packaging**: README, docs set, reusable `SConscript`.
- [x] **M5 — CI**: `.github/workflows/ci.yml` builds → runs headless → uploads JSON.
- [ ] **Exit code 2 (usage error)**: emit a distinct code for malformed `--gdxtest-*` flags.
- [ ] **`skip` support**: a way to mark tests skipped (timing/fixture/precondition) so JSON
      `skip` is populated.
- [ ] **Expose the live `SceneTree`/root `Node` to test bodies** so engine integration suites can
      create nodes and drive the tree directly (not just singletons).
- [ ] **Async / multi-frame tests (M2-era)**: `process_frame`-driven await for frame-dependent
      code; hooks already exist in `config.h` / `notes.md`.
- [ ] **Object leak / UAF tracking (M4-era)**: implement `TestContext::track_object` /
      `track_ref` and assert no live objects remain at teardown.
- [ ] **Fixture scaffolding generator**: emit `testdata/project/` for a host instead of
      copy-the-template.

## Explicitly out of scope for now

- Windows/macOS CI — Linux-first; keep `platform=` plumbing as-is.
- A separate runner binary — the framework compiles into the host's test build by design.
