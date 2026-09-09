# CLI reference

The CLI is the `gdextest` script inside the framework submodule. Run it from your repository root:

```bash
./extern/gdextest/gdextest <command> [flags]
```

(The framework's own repository uses `./gdextest`.) Global flags: `--project-root` (default `.`) and `--framework-dir` (default `extern/gdextest`).

## Commands

| Command | Effect |
| --- | --- |
| `gdextest test` | The one-command flow: config init, doctor preflight, build, fixture generation, headless run. |
| `gdextest init` | Create the starter `.gdextest.toml`. `--ci` also writes a GitHub Actions workflow. `--force` regenerates. |
| `gdextest doctor` | Environment checks without building. |
| `gdextest scaffold` | Wire the `SConstruct` permanently (`--apply`), generate the entry point and a smoke suite, then run doctor. |
| `gdextest list` | Build the test library and list the selected tests. Needs a run trigger: pass `--gdextest-run` through or set `GDX_RUN_TESTS`. |
| `gdextest report` | Merge shard result documents into one JSON/JUnit report. `--console` also renders a human report. |
| `gdextest clean` | Remove the fixture directory and the build output. |

`test` is safe on a fresh clone: it creates the starter config only when none exists, and it never modifies your `SConstruct`. When the build file does not call the framework SConscript, `test` builds through a temporary injected copy (`SConstruct.gdextest`, created with `scons -f`, deleted afterwards). `scaffold --apply` is the only command that writes your `SConstruct`; it backs the file up as `SConstruct.gdextest.bak` first and verifies the patch parses.

## Flags for `test` and `list`

| Flag | Effect |
| --- | --- |
| `--godot /path/to/Godot` | Use this Godot binary. Otherwise: config `godot` key, `GODOT` env var, `godot` on `PATH`, then a `Godot_v*` search. |
| `--filter=<spec>` | Select tests. Comma-separated globs; `-` prefix excludes. Forwarded to the runner. |
| `--shard=k/n` | Run shard `k` (0-based) of `n`. Stable hash assignment. Forwarded to the runner. |
| `--shuffle[=seed]` | Randomize run order with a fixed LCG. `--shuffle` alone uses seed 1. Forwarded to the runner. |
| `--json=<path>` | Write the run's JSON document here. The CLI resolves the path to an absolute path before launching Godot. |
| `--junit=<path>` | Also write JUnit XML, converted from the run's JSON. `--gdextest-junit=<path>` works as a pass-through too. |
| `--keep-fixture` | Keep the generated fixture project when the run fails. Removed on a green run as usual. |
| `--color={auto,always,never}` | Colorize the report. `auto` (default): on for a terminal, off when piped or in CI. |
| `--verbose` | Also print Godot's captured engine output after the report. |
| `--gdextest-raw-log=<path>` | Write Godot's captured output verbatim to this file. |

Unknown `--gdextest-*` arguments are not rejected by the CLI; `test` passes them through to the runner verbatim, so new runner flags work without a CLI update. Typos still fail: the runner exits `2` on unknown options. Any other unknown argument is a CLI usage error.

## Runner options (`--gdextest-*`)

The runner reads these from Godot's user argument list (after `--`). The CLI forwards them; you rarely type them yourself.

| Option | Effect | Default |
| --- | --- | --- |
| `--gdextest-run` | Run the suites, print the summary, and quit. The trigger. | off |
| `--gdextest-list` | Print the selected tests and quit without running. Needs the trigger to be present. | off |
| `--gdextest-filter=<spec>` | Select tests: comma-separated globs, `-` prefix excludes. Matched against `suite.name`, the suite, or the name. Case-sensitive; `*` and `?` wildcards. | all tests |
| `--gdextest-shard=k/n` | Run shard `k` of `n`. `hash(suite) ^ (hash(name) * 2654435761)` modulo `n`, so assignment is stable across runs. | no sharding |
| `--gdextest-shuffle[=seed]` | Shuffle with a seeded LCG and Fisher-Yates. A fixed seed reproduces the order. | declaration order |
| `--gdextest-json=<path>` | Write the JSON results document. | none |
| `--gdextest-timeout-ms=<n>` | Per-wait timeout for async waits. | 30000 |
| `--gdextest-isolate-timeout-sec=<n>` | Whole-test budget for one async test. | 60 |
| `--gdextest-flaky-retries=<n>` | Extra attempts for `TAG_FLAKY` tests. | 3 |

The CLI always forwards the three budget flags, populated from `[gdextest.test]` in `.gdextest.toml`, so TOML values apply without a framework rebuild.

## The trigger

A run starts only when a trigger is present:

- `--gdextest-run` in Godot's arguments. The adapter checks **both** argument lists, before and after `--`.
- The `GDX_RUN_TESTS` environment variable (any value).

Without a trigger the extension loads, the plugin starts, and nothing runs. This is what makes the test library safe to open in a real editor session.

## Doctor checks

`gdextest doctor` runs on every `test` invocation before the build:

- Configuration validity, including zero-match source patterns (each pattern prints its match count).
- Godot: found, executable, and its version matches the configured major.minor.
- SCons on `PATH`.
- The framework SConscript exists.
- godot-cpp binding version (read from `extern/godot-cpp`'s branch or `git describe`); a mismatch prints a loud warning, and the compile step stays the final arbiter.
- `SConstruct` wiring: whether it calls the framework SConscript. `test` reports an unwired file as an informational note (it builds through injection); bare `doctor` reports it as a failure.
- Consumer extension files, when `[gdextest.consumer_extension]` is configured. With none configured and exactly one `.gdextension` in the project, it prints the exact TOML lines to add.

Exit codes: `0` healthy, `2` a check failed.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | All selected tests passed. |
| `1` | At least one test failed or crashed. `report` also exits `1` when any merged test failed. |
| `2` | Usage or environment error: malformed option, failed doctor check, failed build, or unknown `--gdextest-*` option. |

Exit happens through `SceneTree::quit(code)`, which propagates to the process exit code under `--headless`.

## Human output

`gdextest test` captures Godot's output and prints a GoogleTest-style report after the engine exits — engine chatter (banner, import messages, plugin load lines) never mixes into it:

```text
[==========] Running 21 tests from 3 suites.
[----------] 4 tests from counter
[ RUN      ] counter.bump_increments
[       OK ] counter.bump_increments (0 ms)
[ RUN      ] counter.reset_clears
[  FAILED  ] counter.reset_clears (0 ms)
    tests/counter_state_tests.cpp:12: expected bump() == 1
  expected: 1
  actual:   2
[----------] 4 tests from counter (12 ms total)
...
[==========] 21 tests from 3 suites ran. (118 ms total)
[  PASSED  ] 19 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] counter.reset_clears
[ SKIPPED  ] 1 test, listed below:
[ SKIPPED  ] skip_demo.requires_optional_benchmark_service
```

- Tests are grouped per suite in execution order. Durations appear per test, per suite, and in the totals line; `(retries: n)` marks `TAG_FLAKY` tests that needed extra attempts.
- Failure lines carry `file:line` and the formatted message; comparison macros print both operands beneath the expression text. A timed-out async wait renders as a failed test whose message contains `timed out`.
- On a green run the failure and skip epilogues are omitted entirely.
- Passing lines are green, failures red, skips yellow when the report goes to a terminal. `--color={auto,always,never}` overrides the default `auto` mode: colors turn off when piped or in CI, honoring `NO_COLOR` and `CLICOLOR_FORCE`.

### Engine output and crash forensics

- Godot's captured output is suppressed by default. `--verbose` prints it after the report; `--gdextest-raw-log=<path>` writes it verbatim to a file.
- A failed run appends the last engine lines as `gdextest: godot output (tail)` — load-time errors and warnings usually live there.
- If the engine dies before writing the results document (segfault, OOM kill), no results are faked: the CLI prints the noise tail instead and propagates the process exit code.
- Runs that drive the Godot binary directly (see the examples below) bypass the CLI, so Godot's and the runner's output both appear unfiltered on the console; the captured-and-rendered report is the `gdextest test` surface.

`--gdextest-list` prints the selected tests and captures the engine launch output:

```text
# gdextest list: 15 tests selected
self.filter_positive_glob_matches
string_utils.trim_strips_both_ends
...
```

## JSON output

`--gdextest-json=<path>` writes one document:

```json
{
  "totals": { "pass": 19, "fail": 1, "skip": 1, "crashed": 0 },
  "results": [
    {
      "suite": "counter",
      "name": "bump_increments",
      "status": "fail",
      "duration_ms": 0,
      "retries": 0,
      "failures": [
        { "file": "tests/counter_state_tests.cpp", "line": 12, "message": "expected bump() == 1\n  expected: 1\n  actual:   2" }
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

Field notes:

- `status` is one of `pass`, `fail`, `crashed`, `skipped`.
- `crashed` marks a body that threw an unexpected exception, or an async test that aborted. A crashed test also counts toward `fail`.
- `skipped` marks a `GDEX_SKIP` test; the optional `reason` carries the skip message. Skips never count toward `fail`.
- A timed-out async wait reports status `fail` with a failure message containing `timed out`. There is no special field.
- `retries` is the number of additional attempts a `TAG_FLAKY` test used; other tests report `0`.
- Strings are escaped per RFC 8259; control characters become `\uXXXX`.

## JUnit output

`--junit=<path>` (CLI-level, on `test` and `report`) converts the run's JSON into JUnit XML. GitHub Actions and other CI surfaces render JUnit natively, so failures and skips become inline annotations. Skipped tests produce `<skipped>` elements with their reason.

## Parallel CI: sharding and report

Run one job per shard, each writing its own JSON document:

```bash
./extern/gdextest/gdextest test --shard=0/4 --json=shard0.json
./extern/gdextest/gdextest test --shard=3/4 --json=shard3.json
```

Shard assignment hashes `suite` and `name`, so it is stable across runs and disjoint across shards. Then merge:

```bash
./extern/gdextest/gdextest report 'shard*.json' --json=merged.json --junit=merged.xml
```

`report` accepts file paths or glob patterns, concatenates the results, and recomputes `totals`. It exits `1` when any merged test failed or crashed, so the merge step gates the pipeline too.

With `--console`, `report` additionally renders the merged results as a GoogleTest-style console report — per-suite blocks with `[ RUN ]` / `[ OK ]` / `[ FAILED ]` / `[ SKIPPED ]` lines, failure detail, skip reasons, and retry annotations. Colors follow `--color={auto,always,never}` (default `auto`: on for a terminal, off when piped or in CI, honoring `NO_COLOR` and `CLICOLOR_FORCE`). The default JSON-on-stdout output is unchanged; `--console` only prints the human report in addition.

## Environment and hygiene

- **Hermetic `user://`.** The CLI wipes `build/gdextest/user-data` before every run and points `XDG_DATA_HOME` at it. Residue from a previous run cannot leak into `should not exist at start` assertions.
- **Disposable fixture.** The fixture project is generated per run and removed afterwards. `--keep-fixture` retains it when a run fails.
- **Cold-cache warmup.** On a fixture with no `.godot` cache, the CLI runs one no-trigger warmup pass first. Godot 4.5's first headless-editor run on a cold cache can abort during shutdown; the import completes before the abort, so the warmup makes the real run deterministic.
- **`ldd -r` preflight.** On Linux the CLI relocates the built library and reports unresolved symbols, with each source pattern's match count, before Godot ever loads it.

## Examples

Run everything and write results for CI:

```bash
./extern/gdextest/gdextest test --json=results.json --junit=results.xml
```

Drive Godot directly against a kept fixture:

```bash
godot --headless --editor --path build/gdextest/project -- \
    --gdextest-run --gdextest-json=results.json
```

One suite, reproducible random order:

```bash
godot --headless --editor --path build/gdextest/project -- \
    --gdextest-run --gdextest-filter=counter.* --gdextest-shuffle=42
```

Environment-variable trigger, when you cannot touch the command line:

```bash
GDX_RUN_TESTS=1 godot --headless --editor --path build/gdextest/project
```

This repository's `./run_tests.sh` wraps the standard invocation for its own suites.
