# GDExtension testing framework — plan

## Goal (one sentence)

A framework that other GDExtension developers **pull into their own repo** to test their
extension inside a **headless Godot binary**: build once, run `godot --headless`, get
pass/fail on the exit code.

## Current state (evaluation)

The repo has a real, working core and a pile of scaffolding that drifted from the plan it
was built against. The original plan doc (referenced as `plan §N` in code comments and in
`docs/testing/notes.md`) is **gone** — `.plans/` is empty. Code was written against that
missing doc, then reorganized without updating the build.

### What already exists (good)

| Piece | Location | Status |
| ----- | -------- | ------ |
| Pure C++ test core: registry, filter/shards/shuffle, `TestContext`, assertion macros | `src/framework/` | ✅ complete, self-tested |
| Runner: flag parsing, human + JSON output, `SceneTree::quit(code)` exit | `src/framework/runner.cpp` | ✅ complete (sync only) |
| GDExtension entry: `EditorPlugin` shell + `gdx_test_library_init` | `src/gdx_test_entry.cpp` | ✅ |
| Host adapter pattern (trigger detection, bootstrap, `maybe_run`) | `src/support/adapter.cpp` | ✅ |
| Self-tests + two host suites | `tests/*.cpp` | ✅ |
| M0 engine-fact verification (headless quit codes, editor hook point, `user://` hermeticity) | `docs/testing/notes.md` | ✅ — the one doc that survived |

### Where it went off the rails

1. **`SConstruct` points at files that don't exist.** It builds `tests/framework/registry.cpp`,
   `tests/framework/runner.cpp`, and `tests/support/adapter.cpp` — the real files are
   `src/framework/*` and `src/support/*`. **The build is broken as committed.**
2. **No fixture Godot project.** The whole execution model (headless run, plugin-enabled
   `project.godot`, loading `libgdx-test.so` via a `.gdextension` file) has nothing to run —
   no `testdata/project.godot`, no `.gdextension` manifest. The design assumes it ("only
   testdata/project loads", per SConstruct comment) but it was never created.
3. **No consumer story.** Nothing says how another repo "pulls this in" (submodule? vendored
   copy? which files?). The framework core is mixed with host-specific bits under `src/`, so
   there's no clean boundary to package.
4. **Zero docs.** `README.md` is empty. No quickstart, no CI invocation recipe (plan §11
   referenced one), no usage of the `--gdxtest-*` flags anywhere a newcomer would find it.
5. **Repo hygiene:** no commits yet, `.plans/` is gitignored (plan docs won't be tracked),
   a stray `tests/framework_self_tests.os` build artifact, `bin/` never produced.

### What "distributable" means here (target shape)

A consumer's repo would:

1. Pull in this repo (git submodule is the natural fit — matches the existing `extern/godot-cpp`
   pattern) or vendor `framework/` + `entry/` + a small `SConscript`.
2. Include the framework headers, write their own adapter (their extension's real bootstrap +
   which services to start), and register suites with `GDX_TEST(...)`.
3. Build with `scons tests=true` → produces `libgdxtest.<platform>.<target>.so`.
4. Run headless against their fixture project:
   `godot --headless --path <project> --gdxtest-run` (or `GDX_RUN_TESTS=1`), read the exit code
   (0 pass / 1 fail / 2 usage), consume `--gdxtest-json=results.json` in CI.

The framework ships the **core + entry + runner + reporting**; the **adapter + fixture
project** stay per-host. This repo doubles as the reference consumer (its own tests).

## Near-term plan (simple, ordered)

Each step ends with something runnable/verifiable.

1. **Fix the build; reconcile layout.** ✅ done
   - `SConstruct` now points at the real files (`src/framework/*`, `src/support/adapter.cpp`),
     adds `src` to the include path, enables `-fexceptions` (godot-cpp defaults to
     `-fno-exceptions`), fixes the 4.5 entry API, and appends `.so` to the artifact name.
   - Framework/ vs host split kept: pure-C++ core in `src/framework/` (ships), entry +
     adapter in `src/support/` + `src/gdx_test_entry.cpp` (ships), suites under `tests/`.
   - `scons platform=linux target=template_debug tests=true` builds
     `bin/libgdx-test.linux.template_debug.x86_64.so` (3.1 MB, exports
     `gdx_test_library_init`, statically links godot-cpp). Compile+link verified;
     running the suite headless waits on step 2 (fixture project).

2. **Create the fixture project (`testdata/project/`).** ✅ done
   - `project.godot` (plugin enabled via `[editor_plugins]`), `libgdxtest.gdextension`
     (entry symbol + `linux.debug.x86_64` → `res://bin/` symlink to the built `.so`),
     `addons/gdxtest/plugin.cfg` + `plugin.gd`.
   - `plugin.gd` extends `EditorPlugin` (the manager rejects scripts extending the native
     class) and defers the run until `EditorFileSystem.is_scanning()` is false — quitting
     earlier races the scan thread and intermittently crashes the editor (see notes.md §5).
   - Verified headless: `godot --headless --editor --path testdata/project -- --gdxtest-run`
     → `15 passed, 0 failed`, exit 0; deliberate failure → exit 1; `--gdxtest-filter=counter.*`
     runs 4 tests; `--gdxtest-run --gdxtest-list` lists 15; JSON totals correct; 3/3 repeat
     runs stable. Wrapper script: `./run_tests.sh` (build + wire + hermetic `XDG_DATA_HOME`).
   - Quirk: `--gdxtest-list` alone doesn't trigger (runner requires a trigger flag first).

3. **Write the run script + CI recipe.**
   - `run_tests.sh` (or `scons test` alias): build → run headless → map exit code to CI.
   - Document the `--gdxtest-*` flags (`--filter`, `--shard`, `--json`, `--list`) in README.
   - `Done:` one command runs the whole suite in CI; JSON artifact produced.

4. **Consumer packaging.** ✅ done
   - `SConscript` at the repo root: call it from your `SConstruct` after godot-cpp with an
     `exports={"env", "gdxtest": {enabled, entry, adapter, suites, out_dir, out_name}}`
     dict. It clones the env, adds `GDX_TESTS_ENABLED` + framework include paths +
     `-fexceptions`, resolves host paths against the project root, and builds
     `<out_dir>/<out_name><suffix>.so` (absolute target so it lands outside the variant dir).
   - This repo's `SConstruct` is the reference consumer of it (entry/adapter/suites passed
     through the same `gdxtest` dict); `scons tests=true` produces the identical
     `bin/libgdx-test.linux.template_debug.x86_64.so` and 15/15 still pass headless.
   - Docs: `docs/consumer-guide.md` §6 shows the copy-paste call.
   - Still open: fixture scaffolding (copy `testdata/project/` by hand).

5. **Docs pass.**
   - Fill `README.md`: what it is, quickstart, flags, exit codes, CI, FAQ (editor vs runtime
     extensions, hermetic `user://`).
   - `Done:` a newcomer can go from clone → green run in < 10 minutes following the README.

## Explicitly out of scope for now

- Async / multi-frame tests (`process_frame`-driven await, plan's M2) — note the hooks exist
  in `config.h`/`notes.md` but don't build it yet.
- Object leak / UAF tracking (`track_object`/`track_ref` stubs) — M4-era, stubbed only.
- Windows/macOS CI — Linux-first; keep `platform=` plumbing as-is.

## Open questions

- Submodule vs vendored copy for consumers? (Leaning submodule: matches `extern/godot-cpp`.)
- Should the framework core live in this repo's `src/` (reference host) or a separate
  `framework/` tree that consumers copy wholesale? This determines how clean the SConscript
  fragment in step 4 is.
- Keep `.plans/` gitignored, or track plans? (Currently ignored — plan docs would vanish again.)
