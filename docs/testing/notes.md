# M0 spike — engine facts for the GDExtension test framework

> Output of the M0 milestone in [`.plans/gdextension-testing-framework.md`](../../.plans/gdextension-testing-framework.md).
> Goal: settle every engine-level assumption the framework leans on **before** writing framework
> code. Each row is verified against the vendored `extern/godot-cpp` 4.5 submodule in this repo
> and/or a live `Godot_v4.5-stable_linux.x86_64` run.

- Submodule: `extern/godot-cpp` at `4.5` branch (commit `60b5a4196de8442b43b32ba68ebe1e79cfcb762f`).
- Generated headers: `extern/godot-cpp/gen/include/godot_cpp/...`.
- Live binary: `Godot_v4.5.stable.official.876b29033` (Linux x86_64).

## 1. Static verification (binding API surface)

| # | Need (plan §3 / risk) | API in this build | Status | Evidence |
| - | --------------------- | ----------------- | ------ | -------- |
| 1 | Exit with code            | `SceneTree::quit(int32_t p_exit_code = 0)` | ✅ declared | `scene_tree.hpp:92` |
| 2 | `OS::set_exit_code` availability | **not exposed** by godot-cpp 4.5 → use `quit(code)` only | ✅ confirmed absent | `os.hpp` (only `set_restart_on_exit`) |
| 3 | Trigger detection (env)   | `OS::has_environment`, `OS::get_environment` | ✅ | `os.hpp:121–122` |
| 4 | Trigger detection (args)  | `OS::get_cmdline_args()` **and** `OS::get_cmdline_user_args()` (both must be checked — see §3) | ✅ | `os.hpp:129–130` |
| 5 | UAF / dead-object check   | `Object::get_instance_id()` + `godot::utility_functions::instance_from_id(id)` | ✅ (`ObjectDB` is engine-internal; binding path is `instance_from_id`) | `object.hpp:77`; `utility_functions.hpp:308` |
| 6 | RefCounted leak check     | `RefCounted::get_reference_count()` | ✅ | `ref_counted.hpp:51` |
| 7 | Frame scheduling (timer)  | `SceneTree::create_timer(...)` | ✅ | `scene_tree.hpp:87` |
| 8 | `process_frame` is a real signal | yes — in `SceneTree` signals | ✅ | `extension_api.json` → `SceneTree.signals` includes `process_frame`, `physics_frame` |
| 9 | Frame fallbacks           | `MainLoop::_process`, `Node::_process`, `Node::_ready` (virtuals) | ✅ | `main_loop.hpp:60`; `node.hpp:330,333` |
| 10 | Editor-plugin entry class | `EditorPlugin : public Node` (so `_ready()` is reachable) | ✅ | `editor_plugin.hpp:75` |
| 11 | Tree access from a Node   | `Node::get_tree() const -> SceneTree*` | ✅ | `node.hpp:244` |

## 2. Runtime verification (live Godot 4.5 binary)

These could not be settled from headers; they were run against the real editor. All passed, with
three design corrections that follow.

| ID | Runtime check | Result | Evidence |
| -- | ------------- | ------ | -------- |
| R1a | `SceneTree::quit(N)` propagates to the OS exit code under `--headless` (no editor) | ✅ exact: `quit(0)→0`, `quit(1)→1`, `quit(7)→7` | autoload `_ready()` called `quit(N)`; shell exit matched |
| R1b | Same under `--headless --editor` via `EditorPlugin::_ready()` | ✅ `quit(7)` from `EditorPlugin::_ready()` → exit `7` | editor-plugin `_ready()` runs after `first_scan_filesystem`; `quit()` takes effect |
| R2a | `SceneTree::process_frame` fires under `--headless` | ✅ 3 ticks then clean exit | `process_frame.connect(...)` fired 3 times before `quit(0)` |
| R2b | `process_frame` fires under `--headless --editor` | ✅ 3 ticks then clean exit | same, from `EditorPlugin::_ready()` |
| R3 | Earliest safe adapter hook per mode | ✅ editor: `EditorPlugin::_ready()`; runtime: autoload `_ready()` (plain `--headless`) | both have a live `get_tree()`; `quit()` works from both in their respective mode |
| R4 | Hermetic `user://` | ✅ via `XDG_DATA_HOME=<dir>` env var (NOT `--user-data-dir` — see §3) | `OS::get_user_data_dir()` → `<dir>/godot/app_userdata/<proj>`; `user://` writes land there |

## 3. Design corrections implied by the runtime pass

Three facts the plan assumed are wrong for Godot 4.5; each is small but material. The plan
(§3, §7.1, §11) has been updated to match.

### 3.1 `--user-data-dir` does not exist in Godot 4.5

`godot --help` lists no such flag; setting it (before or after `--`) does nothing —
`OS::get_user_data_dir()` keeps returning the default `~/.local/share/godot/app_userdata/<proj>`.
**Replacement:** the runner sets `XDG_DATA_HOME=<tmpdir>` in the child environment (verified:
writes then land under `<tmpdir>/godot/app_userdata/<proj>`). The framework's `TempDirGuard`
exposes a helper that sets the env var for the process and restores it.

### 3.2 Trigger detection must check both arg lists

`--gdextest-run` placed **before** `--` lands in `OS::get_cmdline_args()` (engine args); tokens
**after** `--` land in `OS::get_cmdline_user_args()`. The plan's trigger detection only mentioned
user args. **Fix:** the adapter checks `has_environment("GDX_RUN_TESTS") || get_cmdline_args().has("--gdextest-run") || get_cmdline_user_args().has("--gdextest-run")`. (The `--gdextest-*` option flags
like `--gdextest-filter=…` are passed after `--` so they arrive as user args, where the parser
reads them.)

### 3.3 Editor mode hooks the runner from `EditorPlugin::_ready()`, never an autoload

An autoload's `_ready()` runs during "Creating autoload scripts" (mid-`first_scan_filesystem`),
**before** the editor main loop is up; a `get_tree().quit()` from there is dropped/deferred and
the editor hangs indefinitely (verified: timeout, exit 124). `EditorPlugin::_ready()` runs
**after** `first_scan_filesystem` completes, when the tree is live, and `quit()` from it exits
cleanly with the right code (verified: exit 7). **Rule:**
- editor extensions → hook from `EditorPlugin::_ready()` (the fixture project enables the
  plugin via `editor/plugins/enabled` in `project.godot`);
- runtime extensions → hook from an autoload's `_ready()` under plain `--headless` (no `--editor`).

Implication for the plan's §3 "Triggered entry point": the editor branch is the **only** branch
that uses `EditorPlugin::_ready()`; the autoload branch is the **only** branch usable without
`--editor`. The plan text now states this explicitly.

## 5. M2 addendum — plugin `_ready()` timing correction (verified with the fixture)

Building the fixture (`testdata/project`) and running `--headless --editor` revealed a nuance
not captured by the M0 spike:

- **`EditorPlugin::_ready()` fires BEFORE the initial file scan completes**, not after. The
  plugin manager calls `_enter_tree()`/`_ready()` during the "Initializing plugins" step of
  `first_scan_filesystem`; the scan thread only starts at the "Starting file scan" step.
- Quitting from that early point races the scan thread: it usually exits 0, but intermittently
  the editor crashed on shutdown (SIGSEGV, exit 134) with "Scan thread aborted".
- **Fix (in `testdata/project/addons/gdextest/plugin.gd`):** defer the run until
  `EditorFileSystem.is_scanning()` is false (poll on `SceneTree.process_frame`, 20 s timeout),
  then instantiate the native plugin. With that, the sequence is deterministic:
  `first_scan_filesystem DONE → loading_editor_layout DONE → gdextest runs → quit(code)`, no
  scan-thread warnings.

R1b's exit-code claim still holds — but only when the run is deferred past the scan. M0's
"_ready() runs after first_scan_filesystem" was wrong for the manager-plugin path.

## 4. M0 exit-criteria status

> "All answered; recorded in `docs/testing/notes.md`."

- **Static engine facts (§1):** ✅ all answered.
- **Runtime behaviors (§2):** ✅ all answered (R1a, R1b, R2a, R2b, R3, R4 all green).
- **Design corrections (§3):** ✅ propagated into the plan (§3 engine-facts table + triggered-entry
  text, §7.1 user-dir mechanism, §11 CI invocation).

**M0 is complete.** The framework can be authored against the verified API set and the three
corrected mechanisms. No open runtime questions remain; the next milestone (M1: registry,
context, asserts, sync runner, `tests=true` flag, `self` suite + two host suites) can begin.
