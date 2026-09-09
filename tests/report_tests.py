#!/usr/bin/env python3
"""Tests for the console report renderer (tools/gdextest_report.py).

Dependency-free by convention: imports the renderer by file path, exercises
`render_report` against synthetic result documents and `use_color` against a
patched environment. Run directly: `python3 tests/report_tests.py`.
"""

from pathlib import Path
import importlib.util
import io
import os
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gdextest_report", ROOT / "tools" / "gdextest_report.py")
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules["gdextest_report"] = REPORT
SPEC.loader.exec_module(REPORT)


def _doc(results: list, totals: dict | None = None) -> dict:
    return {"totals": totals or REPORT.compute_totals(results),
            "results": results}


def _result(suite: str, name: str, status: str, **extra) -> dict:
    base = {"suite": suite, "name": name, "status": status,
            "duration_ms": 0, "retries": 0, "failures": []}
    base.update(extra)
    return base


# --- render_report: shape and content ---------------------------------------


def test_green_run_shape() -> None:
    document = _doc([
        _result("smoke", "framework_is_wired", "pass"),
        _result("counter", "bump_increments", "pass"),
    ])
    out = REPORT.render_report(document)
    assert out.startswith("[==========] Running 2 tests from 2 suites.")
    assert "[----------] 1 test from smoke" in out
    assert "[ RUN      ] smoke.framework_is_wired" in out
    assert "[       OK ] smoke.framework_is_wired (0 ms)" in out
    assert "[==========] 2 tests from 2 suites ran. (0 ms total)" in out
    assert "[  PASSED  ] 2 tests." in out
    # Green run: no failure or skip epilogue.
    assert "FAILED" not in out
    assert "SKIPPED" not in out


def test_suites_grouped_in_execution_order_not_alphabetical() -> None:
    document = _doc([
        _result("zeta", "a", "pass"),
        _result("alpha", "b", "pass"),
        _result("zeta", "c", "pass"),
    ])
    out = REPORT.render_report(document)
    assert out.index("2 tests from zeta") < out.index("1 test from alpha"), \
        "suites must follow first-appearance order, not alphabetical"


def test_failure_detail_and_epilogue() -> None:
    document = _doc([
        _result("counter", "bump_increments", "fail", failures=[{
            "file": "tests/counter_state_tests.cpp", "line": 12,
            "message": "expected bump() == 1\n  expected: 1\n  actual:   2",
        }]),
        _result("smoke", "ok", "pass"),
    ])
    out = REPORT.render_report(document)
    assert "[  FAILED  ] counter.bump_increments (0 ms)" in out
    assert ("    tests/counter_state_tests.cpp:12: expected bump() == 1"
            in out)
    assert "  expected: 1" in out and "  actual:   2" in out
    assert "[  FAILED  ] 1 test, listed below:" in out
    assert "[  FAILED  ] counter.bump_increments" in out
    assert "[  PASSED  ] 1 test." in out


def test_multi_line_message_keeps_indentation() -> None:
    document = _doc([
        _result("m", "multi", "fail", failures=[{
            "file": "f.cpp", "line": 1, "message": "head\nline two\nline three",
        }]),
    ])
    out = REPORT.render_report(document)
    assert "    f.cpp:1: head" in out
    assert "    line two" in out
    assert "    line three" in out


def test_crashed_renders_as_failed_with_dedicated_note() -> None:
    document = _doc([
        _result("a", "explodes", "crashed"),
    ])
    out = REPORT.render_report(document)
    assert "[  FAILED  ] a.explodes (0 ms)" in out
    assert "crashed without a recorded failure" in out
    assert "[  PASSED  ] 0 tests." in out
    assert "[  FAILED  ] 1 test, listed below:" in out


def test_skip_reason_rendered_and_listed() -> None:
    document = _doc([
        _result("skip_demo", "needs_service", "skipped",
                reason="precondition not met: GDX_BENCHMARK_SERVICE is unset"),
    ])
    out = REPORT.render_report(document)
    assert "[ SKIPPED  ] skip_demo.needs_service (0 ms)" in out
    assert ("    skipped: precondition not met: GDX_BENCHMARK_SERVICE is unset"
            in out)
    assert "[ SKIPPED  ] 1 test, listed below:" in out
    assert "[ SKIPPED  ] skip_demo.needs_service" in out


def test_retries_annotation() -> None:
    document = _doc([
        _result("self", "flaky", "pass", retries=2),
    ])
    out = REPORT.render_report(document)
    assert "[       OK ] self.flaky (0 ms) (retries: 2)" in out


def test_empty_selection_renders_zero_line() -> None:
    out = REPORT.render_report(_doc([]))
    assert out == "[==========] 0 tests ran."


def test_durations_sum_in_suite_and_total_lines() -> None:
    document = _doc([
        _result("a", "one", "pass", duration_ms=100),
        _result("a", "two", "pass", duration_ms=23),
        _result("b", "three", "pass", duration_ms=104),
    ])
    out = REPORT.render_report(document)
    assert "[----------] 2 tests from a (123 ms total)" in out
    assert "[==========] 3 tests from 2 suites ran. (227 ms total)" in out


# --- colors -----------------------------------------------------------------


def test_colors_enabled_wraps_statuses_in_ansi() -> None:
    document = _doc([
        _result("a", "passes", "pass"),
        _result("b", "fails", "fail", failures=[{"file": "f", "line": 1,
                                                 "message": "m"}]),
        _result("c", "skips", "skipped", reason="r"),
    ])
    out = REPORT.render_report(document, color=True)
    assert "\x1b[32m[       OK ] a.passes (0 ms)\x1b[0m" in out
    assert "\x1b[31m[  FAILED  ] b.fails (0 ms)\x1b[0m" in out
    assert "\x1b[31m[  FAILED  ] 1 test, listed below:\x1b[0m" in out
    assert "\x1b[31m[  FAILED  ] b.fails\x1b[0m" in out
    assert "\x1b[33m[ SKIPPED  ] c.skips (0 ms)\x1b[0m" in out
    # Structural lines stay plain; failure detail stays plain too.
    assert "[ RUN      ] a.passes\x1b" not in out
    assert "    f:1: m\x1b" not in out


def test_colors_disabled_emits_no_escape_codes() -> None:
    document = _doc([_result("a", "passes", "pass")])
    out = REPORT.render_report(document, color=False)
    assert "\x1b[" not in out


# --- use_color precedence ---------------------------------------------------


def test_use_color_explicit_flag_wins() -> None:
    with mock.patch.dict(os.environ, {"NO_COLOR": "1", "CLICOLOR_FORCE": "1",
                                      "CI": "true"}):
        assert REPORT.use_color("never") is False
        assert REPORT.use_color("always") is True


def test_use_color_clicolor_force_beats_no_color_and_ci() -> None:
    with mock.patch.dict(os.environ, {"CLICOLOR_FORCE": "1",
                                      "NO_COLOR": "1", "CI": "true"}):
        assert REPORT.use_color() is True


def test_use_color_no_color_beats_tty() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True
    with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
        assert REPORT.use_color(stream=stream) is False


def test_use_color_ci_blocks_tty_colors() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True
    with mock.patch.dict(os.environ, {"CI": "true"}):
        assert REPORT.use_color(stream=stream) is False


def test_use_color_piped_stream_defaults_off() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        assert REPORT.use_color(stream=io.StringIO()) is False


def test_use_color_tty_defaults_on() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True
    with mock.patch.dict(os.environ, {}, clear=True):
        assert REPORT.use_color(stream=stream) is True


def test_use_color_windows_requires_terminal_support() -> None:
    stream = io.StringIO()
    stream.isatty = lambda: True
    with mock.patch.dict(os.environ, {}, clear=True), \
            mock.patch.object(REPORT, "_platform", return_value="nt"):
        assert REPORT.use_color(stream=stream) is False
        with mock.patch.dict(os.environ, {"WT_SESSION": "x"}):
            assert REPORT.use_color(stream=stream) is True


# --- compute_totals ---------------------------------------------------------


def test_compute_totals_mirrors_merge_rules() -> None:
    results = [
        _result("a", "p", "pass"),
        _result("a", "f", "fail"),
        _result("a", "c", "crashed"),
        _result("a", "s", "skipped"),
    ]
    totals = REPORT.compute_totals(results)
    assert totals == {"pass": 1, "fail": 2, "skip": 1, "crashed": 1}


if __name__ == "__main__":
    test_green_run_shape()
    test_suites_grouped_in_execution_order_not_alphabetical()
    test_failure_detail_and_epilogue()
    test_multi_line_message_keeps_indentation()
    test_crashed_renders_as_failed_with_dedicated_note()
    test_skip_reason_rendered_and_listed()
    test_retries_annotation()
    test_empty_selection_renders_zero_line()
    test_durations_sum_in_suite_and_total_lines()
    test_colors_enabled_wraps_statuses_in_ansi()
    test_colors_disabled_emits_no_escape_codes()
    test_use_color_explicit_flag_wins()
    test_use_color_clicolor_force_beats_no_color_and_ci()
    test_use_color_no_color_beats_tty()
    test_use_color_ci_blocks_tty_colors()
    test_use_color_piped_stream_defaults_off()
    test_use_color_tty_defaults_on()
    test_use_color_windows_requires_terminal_support()
    test_compute_totals_mirrors_merge_rules()
    print("report renderer tests: ok")
