# Configuration reference

gdextest reads one TOML file, `.gdextest.toml`, at the root of the consumer repository. The CLI creates a starter file when `gdextest test` or `gdextest init` runs and none exists. It never overwrites an existing file unless you pass `--force` to `init`.

## Full example

```toml
[gdextest]
version = "1"
minimum_required_godot_version = "4.5"

[gdextest.tests]
sources = ["tests/**/*.cpp"]
exclude = ["tests/helpers/**"]

[gdextest.test]
timeout_ms = 30000
isolate_timeout_sec = 60
flaky_retries = 3
color = "auto"

[gdextest.host]
mode = "editor"
entry_symbol = "gdextest_library_init"
plugin_class = "GdextestPlugin"
bootstrap = "tests/bootstrap.cpp"

[gdextest.fixture]
directory = "build/gdextest/project"
project_name = "my extension tests"
native_extensions = []
assets = ["tests/fixtures/**"]
scan_timeout_ms = 20000

[gdextest.output]
directory = "bin"
name = "libmy_extension_tests"

[gdextest.build]
args = []

[gdextest.consumer_extension]
library = "addons/my_extension/bin/libmy_extension.linux.editor.x86_64.so"
```

## Sections and keys

### `[gdextest]`

| Key | Default | Meaning |
| --- | --- | --- |
| `version` | `"1"` | Config format version. |
| `minimum_required_godot_version` | `"4.5"` | Minimum Godot major.minor[.patch] the tests need. The doctor and `test` reject a found binary below it; a binary at or above it runs the tests. |
| `godot` | unset | Path to a Godot binary. Same effect as the `GODOT` environment variable. |

### `[gdextest.tests]`

| Key | Default | Meaning |
| --- | --- | --- |
| `sources` | `["tests/**/*.cpp"]` | Glob patterns for suite and test-support sources. Repo-root relative. `.c`, `.cpp`, `.cc`, and `.cxx` files match. |
| `exclude` | `[]` | Glob patterns removed from the matched set. |

A pattern that matches nothing fails the build with the pattern named. Everything the patterns match compiles into the test library.

### `[gdextest.test]`

| Key | Default | Meaning |
| --- | --- | --- |
| `timeout_ms` | `30000` | Per-wait timeout for async waits. Forwarded as `--gdextest-timeout-ms`. |
| `isolate_timeout_sec` | `60` | Whole-test budget for one async test. Forwarded as `--gdextest-isolate-timeout-sec`. |
| `flaky_retries` | `3` | Extra attempts for `TAG_FLAKY` tests. Forwarded as `--gdextest-flaky-retries`. |
| `report` | `"cli"` | In-engine console layout. `"cli"` (default) means the CLI renders the report itself and forces the quiet engine; `"quiet"`/`"pretty"` choose the runner's own marker-prefixed layout for the captured lines. Only observable when driving Godot directly. Forwarded as `--gdextest-report`. |
| `color` | `"auto"` | Console report colors: `auto` (terminal-aware), `always`, or `never`. The `--color` flag overrides. |
| `raw_log` | unset | Write Godot's captured output verbatim to this file on every run. The `--gdextest-raw-log` flag overrides. |

The CLI forwards the budgets on every run, so CI can tune them without rebuilding the framework. The console keys (`report`, `color`, `raw_log`) have CLI-flag counterparts that win when set.

### `[gdextest.host]`

| Key | Default | Meaning |
| --- | --- | --- |
| `mode` | `"editor"` | `"editor"` runs `--headless --editor` with a scan-safe editor plugin. `"runtime"` runs plain `--headless` with an autoload host. |
| `entry_symbol` | `"gdextest_library_init"` | Entry function the generated `.gdextension` manifest declares. |
| `plugin_class` | `"GdextestPlugin"` | Native editor plugin class the fixture wrapper instantiates. Keep it in sync with your entry point. |
| `bootstrap` | unset | Extra C++ source compiled into the test library. Typical use: the file that calls `gdextest::configure_host`. |

### `[gdextest.fixture]`

| Key | Default | Meaning |
| --- | --- | --- |
| `directory` | `"build/gdextest/project"` | Where the generated fixture project lives. Disposable build output. |
| `project_name` | `"gdextest fixture"` | Name written into the fixture's `project.godot`. |
| `manifest_name` | `<output name>.gdextension` | File name of the generated `.gdextension` manifest. |
| `library_key` | `<platform>.<feature>.<arch>` | Manifest key for the test library, for example `linux.debug.x86_64`. `feature` is `debug` unless the target is `template_release`. |
| `native_extensions` | `[]` | Extra `res://` paths added to the fixture's `[native_extensions]`. |
| `assets` | `[]` | Glob patterns copied into the fixture, preserving paths relative to the project root. Use for test data and scenes. |
| `scan_timeout_ms` | `20000` | How long the editor's first filesystem scan may take before the host fails the run. Raise for large repositories or loaded CI machines. |

The fixture is removed after each run. Pass `--keep-fixture` to `test` or `list` to keep it when a run fails.

### `[gdextest.output]`

| Key | Default | Meaning |
| --- | --- | --- |
| `directory` | `"bin"` | Directory for the built test library. |
| `name` | `"libgdextest"` | Base name of the test library. The platform suffix comes from the SCons environment. |

### `[gdextest.build]`

| Key | Default | Meaning |
| --- | --- | --- |
| `args` | `[]` | Extra SCons arguments, for example `["platform=windows", "target=editor", "arch=x86_64"]`. |

### `[gdextest.consumer_extension]`

Loads your real extension alongside the tests. See [Consumer guide](consumer-guide.md#6-load-your-real-extension) for the full story.

| Key | Default | Meaning |
| --- | --- | --- |
| `library` | unset | Path to your built extension shared library. |
| `manifest` | unset | Path to your `.gdextension` manifest. |

Set one and the other is derived: a library finds the unique `.gdextension` near it; a manifest's `[libraries]` table names its library. Set both when the search is ambiguous. The fixture stages the extension under `addons/consumer/` and rewrites the manifest's library paths to that copy.

## TOML dialect

The loader is a small, dependency-free TOML subset:

- Dotted section headers, quoted strings, booleans, and arrays.
- Arrays may span multiple lines.
- `#` starts a comment, except inside quoted strings.
- A missing closing quote or bracket is a parse error with `file:line` context. Nothing is silently mangled into a literal.

## Validation

`gdextest doctor` and every `gdextest test` validate the config before building:

- Godot version matches the `\d+.\d+` shape and the found binary's major.minor.
- `host.mode` is `editor` or `runtime`.
- `sources` is non-empty and every pattern matches at least one file.
- `entry_symbol` and `plugin_class` are valid identifiers.
- `build.args` entries are `key=value`.
- Budgets are positive; `flaky_retries` is zero or more.
- `report` is `cli`, `quiet`, or `pretty`; `color` is `auto`, `always`, or `never`.
- `consumer_extension` sets both files or neither, unless derivation succeeds.

A failed validation exits `2` before SCons or Godot starts.

## Precedence

The build resolves each setting from the most specific source:

1. The `gdextest` export in your `SConscript` call (rare; for custom setups).
2. The `gdextest_*` environment variables the CLI sets (`gdextest_SOURCES`, `gdextest_HOST_MODE`, `gdextest_BOOTSTRAP`).
3. This `.gdextest.toml`.
4. Built-in defaults.

The SConscript loads the TOML itself, so the file is the single source of truth for both the CLI flow and a bare `scons tests=true`.
