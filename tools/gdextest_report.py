#!/usr/bin/env python3
"""Console rendering for gdextest result documents (GoogleTest style).

Pure functions over the run-result JSON schema documented in docs/cli.md
("JSON output"): per-suite blocks in execution order, `[ RUN ]` / `[ OK ]` /
`[ FAILED ]` / `[ SKIPPED ]` result lines, banners, totals, failure detail,
skip reasons, and retry annotations. No subprocess or engine knowledge — the
CLI can render both single runs and merged shard reports with the same code.

Colors follow GoogleTest's precedent: on for a TTY, off when piped, off in CI
logs, with the NO_COLOR / CLICOLOR_FORCE conventions. The decision is made
once by `use_color()` and passed explicitly to `render_report()`, so rendering
is deterministic and unit-testable without a terminal."""

from __future__ import annotations

import os
import sys

# Labels are padded to ten characters inside the brackets, mirroring
# googletest's columns so tooling that greps for googletest-style markers also
# matches ours. SKIPPED has no googletest precedent; it follows the same width.
BANNER = "[==========]"
RULE = "[----------]"
RUN = "[ RUN      ]"
OK = "[       OK ]"
FAILED = "[  FAILED  ]"
SKIPPED = "[ SKIPPED  ]"
PASSED = "[  PASSED  ]"

_GREEN = "32"
_RED = "31"
_YELLOW = "33"

# A conservative CI probe: these variables mean the output lands in a CI log,
# where ANSI escapes render as garbage. CLICOLOR_FORCE still overrides.
_CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "TRAVIS",
                "APPVEYOR", "TEAMCITY_VERSION", "BUILD_NUMBER")


def _platform() -> str:
    """Indirection for tests (os.name cannot be patched cleanly)."""
    return os.name


def paint(text: str, code: str, enabled: bool) -> str:
    """Wrap `text` in the ANSI SGR sequence `code` when colors are enabled."""
    if not enabled:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def use_color(mode: str | None = None, stream=None) -> bool:
    """Decide whether ANSI colors are on.

    `mode` mirrors the CLI's --color flag: "always", "never", or None/"auto".
    Precedence, most specific first:

      1. --color=never / --color=always (explicit user choice wins)
      2. CLICOLOR_FORCE (non-empty and not "0") forces colors on
      3. NO_COLOR (present at all) forces colors off
      4. a CI environment probe forces colors off
      5. on Windows, colors need WT_SESSION / ANSICON / ConEmuANSI
      6. otherwise: whether `stream` (default stdout) is a TTY

    `stream` is an argument so tests can pass a fake TTY or a StringIO
    without touching the real stdout.
    """
    if stream is None:
        stream = sys.stdout
    if mode == "never":
        return False
    if mode == "always":
        return True
    force = os.environ.get("CLICOLOR_FORCE", "")
    if force and force != "0":
        return True
    if "NO_COLOR" in os.environ:
        return False
    if any(os.environ.get(name) for name in _CI_ENV_VARS):
        return False
    if _platform() == "nt" and not (os.environ.get("WT_SESSION")
                                    or os.environ.get("ANSICON")
                                    or os.environ.get("ConEmuANSI")):
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def compute_totals(results: list) -> dict:
    """Totals for a result list, mirroring `_merge_documents`' counting rules:
    `crashed` also counts toward `fail`; `skipped` never does."""
    totals = {"pass": 0, "fail": 0, "skip": 0, "crashed": 0}
    for result in results:
        status = result.get("status")
        if status == "crashed":
            totals["crashed"] += 1
            totals["fail"] += 1
        elif status == "fail":
            totals["fail"] += 1
        elif status == "skipped":
            totals["skip"] += 1
        else:
            totals["pass"] += 1
    return totals


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _result_label(result: dict) -> str:
    return f"{result.get('suite', '?')}.{result.get('name', '?')}"


def _failure_lines(failure: dict) -> list:
    """Render one recorded failure: `file:line:` prefix, then the message with
    its own line structure preserved (comparison macros embed the expected and
    actual operands as indented continuation lines)."""
    prefix = f"    {failure.get('file', '?')}:{failure.get('line', 0)}: "
    message = failure.get("message", "")
    lines = message.split("\n") if message else [""]
    out = [prefix + lines[0]]
    out.extend("    " + extra for extra in lines[1:])
    return out


def render_report(document: dict, color: bool = False) -> str:
    """Render one result document ({totals, results}) as a console report.

    Groups tests per suite in first-appearance (execution) order — never
    alphabetized, matching googletest. The failure epilogue re-lists only the
    failed cases; skips get the same treatment; a green run omits both.
    Returns the report without a trailing newline (callers `print()` it).
    """
    results = document.get("results", [])
    totals = document.get("totals") or compute_totals(results)
    suites: dict = {}
    for result in results:
        suites.setdefault(result.get("suite", "?"), []).append(result)
    suite_count = len(suites)
    total_ms = sum(int(result.get("duration_ms", 0)) for result in results)

    lines: list = []
    if not results:
        return f"{BANNER} 0 tests ran."

    lines.append(f"{BANNER} Running {_plural(len(results), 'test')} from "
                 f"{_plural(suite_count, 'suite')}.")

    for suite, suite_results in suites.items():
        suite_ms = sum(int(result.get("duration_ms", 0))
                       for result in suite_results)
        lines.append(f"{RULE} {_plural(len(suite_results), 'test')} from {suite}")
        for result in suite_results:
            label = _result_label(result)
            duration = int(result.get("duration_ms", 0))
            retries = int(result.get("retries", 0))
            suffix = f" ({duration} ms)" + (f" (retries: {retries})"
                                            if retries else "")
            # The RUN line precedes every result, mirroring googletest; in a
            # post-exit render it pairs each test with its outcome.
            lines.append(f"{RUN} {label}")
            status = result.get("status")
            if status == "fail":
                lines.append(paint(f"{FAILED} {label}{suffix}", _RED, color))
                if result.get("failures"):
                    for failure in result["failures"]:
                        lines.extend(_failure_lines(failure))
                else:
                    lines.append("    failed without a recorded failure")
            elif status == "crashed":
                lines.append(paint(f"{FAILED} {label}{suffix}", _RED, color))
                if result.get("failures"):
                    for failure in result["failures"]:
                        lines.extend(_failure_lines(failure))
                else:
                    lines.append("    the test crashed without a recorded failure")
            elif status == "skipped":
                lines.append(paint(f"{SKIPPED} {label}{suffix}", _YELLOW, color))
                reason = result.get("reason", "")
                if reason:
                    lines.append(f"    skipped: {reason}")
            else:
                lines.append(paint(f"{OK} {label}{suffix}", _GREEN, color))
        lines.append(f"{RULE} {_plural(len(suite_results), 'test')} from {suite} "
                     f"({suite_ms} ms total)")

    lines.append(f"{BANNER} {_plural(len(results), 'test')} from "
                 f"{_plural(suite_count, 'suite')} ran. "
                 f"({total_ms} ms total)")

    failed = [result for result in results
              if result.get("status") in ("fail", "crashed")]
    skipped = [result for result in results if result.get("status") == "skipped"]

    lines.append(paint(f"{PASSED} {_plural(totals.get('pass', 0), 'test')}.",
                       _GREEN, color))
    if failed:
        lines.append(paint(f"{FAILED} {_plural(len(failed), 'test')}, "
                           f"listed below:", _RED, color))
        for result in failed:
            lines.append(paint(f"{FAILED} {_result_label(result)}", _RED, color))
    if skipped:
        lines.append(paint(f"{SKIPPED} {_plural(len(skipped), 'test')}, "
                           f"listed below:", _YELLOW, color))
        for result in skipped:
            lines.append(paint(f"{SKIPPED} {_result_label(result)}",
                               _YELLOW, color))
    return "\n".join(lines)
