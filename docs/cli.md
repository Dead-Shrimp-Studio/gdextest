# Command-line reference

## Invocation shape

The consumer-facing command is:

```bash
./gdextest test [--godot /path/to/Godot] [--filter=...] [--json=results.json]
```

`test` is intentionally safe to run from a freshly cloned consumer repository. If
`.gdextest.toml` is missing, it writes the starter config once. It then runs the doctor
checks on every invocation before building or launching Godot. Existing configuration is
never overwritten by `test`; use `init --force` for an explicit reset.

The test run is triggered by launching Godot against the fixture project. Engine arguments
go before `--`; gdextest arguments go after `--`:

```bash
godot --headless --editor --path <fixture> -- --gdextest-run [--gdextest-* options]
```

- The **trigger** (`--gdextest-run`, or the `GDX_RUN_TESTS` env var) is detected in *both*
  argument lists — before or after `--` — because Godot 4.5 splits them differently
  (`get_cmdline_args()` vs `get_cmdline_user_args()`; see `testing/notes.md` §3.2).
- The **option flags** (`--gdextest-filter=…`, `--gdextest-json=…`, …) are read from the user
  list only, so pass them after `--`.
- Without a trigger, the extension loads but does nothing — normal startup continues.

## Setup commands

| Command | Effect |
| --- | --- |
| `./gdextest init` | Create the starter `.gdextest.toml` if it does not exist |
| `./gdextest init --ci` | Create the starter config and GitHub Actions workflow |
| `./gdextest init --force` | Regenerate the starter config and any requested workflow |
| `./gdextest doctor` | Run environment checks without building or running tests |
| `./gdextest scaffold [--apply]` | Wire `SConstruct`, generate entry + smoke suite, run doctor |
| `./gdextest list` | Build the test library and list selected tests |
| `./gdextest report <paths…>` | Merge shard result JSON into one JSON/JUnit report |
| `./gdextest clean` | Remove generated test output |

`test` combines the useful setup steps: missing config initialization, doctor preflight,
build, fixture generation, and the headless Godot run. A doctor failure returns `2` and
prevents the build from starting. It is the **one-command quickstart**: `./gdextest test`
is all you run — config is auto-created, Godot is auto-discovered, everything else
follows. If your `SConstruct` is not wired, `test` builds through a temporary
`SConstruct.gdextest` (the framework call injected into a copy, `scons -f`, cleaned up
afterwards) — your build file is never modified.

`scaffold` is for making that wiring **permanent** or for a **custom entry point**.
Without `--apply` it reports that `SConstruct` does not call the framework SConscript;
with `--apply` it patches the file (backing it up as `SConstruct.gdextest.bak` first and
verifying the patch parses), generates `testsupport/entry.cpp` and a smoke suite from the
TOML values, and finishes with the doctor checks. It is the only command that writes
your `SConstruct`. The setup path is:

```bash
./gdextest init                 # create .gdextest.toml (test auto-does this)
./gdextest scaffold --apply     # wire SConstruct + generate entry/smoke
./gdextest test
```

`report shard*.json --json=merged.json [--junit=results.xml]` merges the JSON documents
produced by parallel `--shard` runs: results are concatenated and `totals` recomputed, and
the merged document (optionally also JUnit XML) is written. It exits `1` when any merged
test failed or crashed, mirroring the runner.

## Flags

| Flag | Effect | Notes |
| --- | --- | --- |
| `--gdextest-run` | Run the suites, print the summary, quit | The trigger. `GDX_RUN_TESTS=1` env var is equivalent |
| `--gdextest-list` | Print the selected tests and quit without running | Requires a trigger to be present |
| `--gdextest-filter=<spec>` | Select tests | Comma-separated globs; `-` prefix excludes, e.g. `--gdextest-filter=string_utils.*,-string_utils.trim_no_op*` |
| `--gdextest-shuffle[=<seed>]` | Randomize run order | Fixed seed reproduces the order; `--gdextest-shuffle` alone uses seed 1 |
| `--gdextest-shard=<k>/<n>` | Run shard `k` (0-based) of `n` | Stable hash assignment — same test always lands in the same shard |
| `--gdextest-json=<path>` | Write machine-readable results | The CLI resolves the path to an absolute path before launching Godot |
| `--gdextest-timeout-ms=<n>` | Per-wait timeout for async tests | CLI forwards `[gdextest.test] timeout_ms` (default 30000) |
| `--gdextest-isolate-timeout-sec=<n>` | Whole-test async budget | CLI forwards `[gdextest.test] isolate_timeout_sec` (default 60) |
| `--gdextest-flaky-retries=<n>` | Additional attempts for `TAG_FLAKY` tests | CLI forwards `[gdextest.test] flaky_retries` (default 3) |

CLI-level convenience flags (not runner options):

| Flag | Effect | Notes |
| --- | --- | --- |
| `gdextest test --junit=<path>` | Also write JUnit XML | Converted from the run's JSON; `--gdextest-junit=<path>` as a pass-through works too |
| `gdextest report <paths…> --junit=<path>` | Write merged JUnit XML | Same schema as `--junit`, over merged shards |

Unknown `--gdextest-*` options are not rejected by the CLI: `gdextest test` passes them
through to the runner verbatim, so new runner flags work without a CLI update (typos are
still caught by the runner's exit code `2`).

**Godot discovery:** when `--godot`, `config.godot`, the `GODOT` env var, and `godot` on
`PATH` all miss, the CLI searches for an executable named `Godot_v*` in the project root,
its ancestors (e.g. a sibling `godot/` checkout), and `$HOME`/common dirs. Binaries whose
name matches the configured major.minor are preferred, so `./gdextest test` usually needs
no `--godot` at all.

**Doctor** additionally checks the consumer's `extern/godot-cpp` binding version against the
framework's supported `godot_version` (via the submodule branch/`git describe`); a mismatch
prints a loud warning (the compile step is the final arbiter). It also verifies the
`SConstruct` calls the framework SConscript.

Filter grammar (see `docs/api-reference.md` → `Filter`): `*` and `?` wildcards,
case-sensitive, matched against `suite.name`, the suite, or the name.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | All selected tests passed |
| `1` | At least one test failed or crashed |
| `2` | Usage error: malformed or unknown `--gdextest-*` option |

Exit happens via `SceneTree::quit(code)`, which propagates to the OS exit code under
`--headless` (M0-verified: `quit(0)→0`, `quit(1)→1`, `quit(7)→7`).

`2` is emitted when an option value fails to parse (e.g. `--gdextest-shard=xyz`, a
non-numeric `--gdextest-shuffle` seed, or a shard outside `[0, n)`) or when an option
starting with `--gdextest-` is unknown (e.g. `--gdextest-bogus`). The offending option is
printed to stdout before exiting.

## Human output

```text
== gdextest: <passed> passed, <failed> failed, <skipped> skipped ==
[PASS] self.filter_positive_glob_matches  (0 ms)
[PASS] string_utils.trim_strips_both_ends  (0 ms)
[FAIL] counter.bump_increments  (0 ms)
    tests/counter_state_tests.cpp:12: expected bump() == 1
        expected: 1
        actual:   2
    (test body aborted/crashed)          # only if the body threw/aborted
[SKIP] skip_demo.requires_optional_benchmark_service  (0 ms)
    skipped: precondition not met: GDX_BENCHMARK_SERVICE is unset
```

Async tests (`GDEX_TEST_ASYNC`, see `api-reference.md`) appear with their wall-clock
duration, e.g. `[PASS] async.timer_await_resumes_after_elapsed_time  (104 ms)`. A test
whose wait never resolves is failed by the runner with a `timed out` failure line — it
counts as `failed` and exits `1`, so a hung test can never stall a pipeline.

The summary line always shows the `skipped` count. A row is `[SKIP]` (with its reason)
when the body called `GDEX_SKIP`. Skipped tests never count toward `failed` and never
change the exit code.

`--gdextest-list` prints:

```
# gdextest list: 15 tests selected
self.filter_positive_glob_matches
string_utils.trim_strips_both_ends
...
```

## JSON output

Written by `--gdextest-json=<path>`. Schema:

```json
{
  "totals": { "pass": 19, "fail": 0, "skip": 1, "crashed": 0 },
  "results": [
    {
      "suite": "counter",
      "name": "bump_increments",
      "status": "fail",              // "pass" | "fail" | "crashed" | "skipped"
      "duration_ms": 0,
      "retries": 0,
      "failures": [
        { "file": "tests/counter_state_tests.cpp", "line": 12, "message": "…" }
      ]
    },
    {
      "suite": "skip_demo",
      "name": "requires_optional_benchmark_service",
      "status": "skipped",
      "reason": "precondition not met: GDX_BENCHMARK_SERVICE is unset",
      "duration_ms": 0,
      "retries": 0,
      "failures": []
    }
  ]
}
```

- `status` is `"crashed"` when the body threw (including `GDEX_ABORT_TEST`) or the run was
  otherwise interrupted; a crashed test also counts toward `fail`.
- `status` is `"skipped"` when the body called `GDEX_SKIP`; the optional `reason` field
  carries the skip message. A skipped test counts toward `totals.skip`, never `fail`.
- An async test whose wait timed out is reported with `status` `"fail"` and a failure
  message containing `timed out` — same schema, no special fields.
- `totals.skip` is the number of tests skipped via `GDEX_SKIP` (0 when none).
- `retries` is the number of additional attempts used for the test. `TAG_FLAKY` tests may
  use up to `kDefaultFlakyRetries` (currently 3) retries; other tests report `0`.
- Strings are JSON-escaped; control characters become `\uXXXX`.

## Examples

Run everything, write results for CI:

```bash
./gdextest test --godot /path/to/Godot --json=results.json
```

The command above performs config initialization and doctor preflight automatically.
For direct Godot invocation, use:

```bash
godot --headless --editor --path testdata/project -- \
    --gdextest-run --gdextest-json=results.json
```

One suite, randomized with a reproducible seed:

```bash
godot --headless --editor --path testdata/project -- \
    --gdextest-run --gdextest-filter=counter.* --gdextest-shuffle=42
```

Parallel CI (4 shards, job 0):

```bash
godot --headless --editor --path testdata/project -- \
    --gdextest-run --gdextest-shard=0/4 --gdextest-json=shard0.json
```

Environment-variable trigger (useful when you can't touch the command line):

```bash
GDX_RUN_TESTS=1 godot --headless --editor --path testdata/project
```

The repo's `./run_tests.sh` wraps build + wiring + the standard invocation. The CLI keeps
`user://` hermetic itself: `test` and `list` wipe `build/gdextest/user-data` before every
run and point `XDG_DATA_HOME` at it, so residue from a previous run never leaks into
"should not exist at start" assertions.

When the fixture has no `.godot` cache yet (a fresh checkout or after `clean`), `test` and
`list` run a single no-trigger warmup pass first: Godot 4.5's first headless-editor run on
a cold project aborts during shutdown (`testing/notes.md` §5 — the import completes before
the abort, so the cache is valid), and the warmup makes the real run deterministic instead
of failing a consumer's very first CI run with a backtrace.
