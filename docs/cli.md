# Command-line reference

## Invocation shape

The test run is triggered by launching Godot against the fixture project. Engine arguments
go before `--`; gdextest arguments go after `--`:

```bash
godot --headless --editor --path <fixture> -- --gdxtest-run [--gdxtest-* options]
```

- The **trigger** (`--gdxtest-run`, or the `GDX_RUN_TESTS` env var) is detected in *both*
  argument lists — before or after `--` — because Godot 4.5 splits them differently
  (`get_cmdline_args()` vs `get_cmdline_user_args()`; see `testing/notes.md` §3.2).
- The **option flags** (`--gdxtest-filter=…`, `--gdxtest-json=…`, …) are read from the user
  list only, so pass them after `--`.
- Without a trigger, the extension loads but does nothing — normal startup continues.

## Flags

| Flag | Effect | Notes |
| --- | --- | --- |
| `--gdxtest-run` | Run the suites, print the summary, quit | The trigger. `GDX_RUN_TESTS=1` env var is equivalent |
| `--gdxtest-list` | Print the selected tests and quit without running | Requires a trigger to be present |
| `--gdxtest-filter=<spec>` | Select tests | Comma-separated globs; `-` prefix excludes, e.g. `--gdxtest-filter=string_utils.*,-string_utils.trim_no_op*` |
| `--gdxtest-shuffle[=<seed>]` | Randomize run order | Fixed seed reproduces the order; `--gdxtest-shuffle` alone seeds with 1 |
| `--gdxtest-shard=<k>/<n>` | Run shard `k` (0-based) of `n` | Stable hash assignment — same test always lands in the same shard |
| `--gdxtest-json=<path>` | Write machine-readable results | Path is relative to the process working directory; JSON schema below |

Filter grammar (see `docs/api-reference.md` → `Filter`): `*` and `?` wildcards,
case-sensitive, matched against `suite.name`, the suite, or the name.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | All selected tests passed |
| `1` | At least one test failed or crashed |
| `2` | Usage error (reserved; not yet emitted) |

Exit happens via `SceneTree::quit(code)`, which propagates to the OS exit code under
`--headless` (M0-verified: `quit(0)→0`, `quit(1)→1`, `quit(7)→7`).

## Human output

```
== gdextest: 15 passed, 0 failed ==
[PASS] self.filter_positive_glob_matches  (0 ms)
[PASS] string_utils.trim_strips_both_ends  (0 ms)
[FAIL] counter.bump_increments  (0 ms)
    tests/counter_state_tests.cpp:12: expected bump() == 1
        expected: 1
        actual:   2
    (test body aborted/crashed)          # only if the body threw/aborted
```

`--gdxtest-list` prints:

```
# gdxtest list: 15 tests selected
self.filter_positive_glob_matches
string_utils.trim_strips_both_ends
...
```

## JSON output

Written by `--gdxtest-json=<path>`. Schema:

```json
{
  "totals": { "pass": 15, "fail": 0, "skip": 0, "crashed": 0 },
  "results": [
    {
      "suite": "counter",
      "name": "bump_increments",
      "status": "pass",              // "pass" | "fail" | "crashed"
      "duration_ms": 0,
      "failures": [
        { "file": "tests/counter_state_tests.cpp", "line": 12, "message": "…" }
      ]
    }
  ]
}
```

- `status` is `"crashed"` when the body threw (including `GDX_ABORT_TEST`) or the run was
  otherwise interrupted; a crashed test also counts toward `fail`.
- `skip` is always 0 in the current milestone (skipping is not implemented yet).
- Strings are JSON-escaped; control characters become `\uXXXX`.

## Examples

Run everything, write results for CI:

```bash
godot --headless --editor --path testdata/project -- \
    --gdxtest-run --gdxtest-json=results.json
```

One suite, randomized with a reproducible seed:

```bash
godot --headless --editor --path testdata/project -- \
    --gdxtest-run --gdxtest-filter=counter.* --gdxtest-shuffle=42
```

Parallel CI (4 shards, job 0):

```bash
godot --headless --editor --path testdata/project -- \
    --gdxtest-run --gdxtest-shard=0/4 --gdxtest-json=shard0.json
```

Environment-variable trigger (useful when you can't touch the command line):

```bash
GDX_RUN_TESTS=1 godot --headless --editor --path testdata/project
```

The repo's `./run_tests.sh` wraps build + wiring + the standard invocation (and points
`XDG_DATA_HOME` at a temp dir so `user://` stays hermetic).
