#!/usr/bin/env python3
"""Tests for the external-consumer configuration contract."""

from pathlib import Path
import contextlib
import importlib.util
import io
import json
import os
import sys
import xml.etree.ElementTree as ET
import tempfile


ROOT = Path(__file__).resolve().parents[1]

def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


config_module = load("gdextest_config", ROOT / "tools" / "gdextest_config.py")
generator = load("generate_fixture", ROOT / "tools" / "generate_fixture.py")
cli = load("gdextest_cli", ROOT / "tools" / "gdextest.py")
compiler_module = load("gdextest_compiler", ROOT / "tools" / "gdextest_compiler.py")


def _stub_cmd_test_deps(module) -> dict:
    """Neutralize everything cmd_test touches around the Godot invocation, the
    same set the fixture-cleanup tests stub; returns the originals."""
    saved = {"doctor": module._run_doctor, "build": module._run_build,
             "executable": module.godot_executable,
             "version": module.godot_version,
             "command": module._godot_command,
             "warm": module._warm_fixture,
             "run": module.subprocess.run}
    module._run_doctor = lambda config, godot, allow_injection=False: 0
    module._run_build = lambda config: None
    module.godot_executable = lambda config, override: "/usr/bin/godot"
    module.godot_version = lambda executable: "4.5"
    module._godot_command = lambda config, executable, *user_args: ["godot", *user_args]
    module._warm_fixture = lambda config, executable: None
    return saved


def _restore_cmd_test_deps(module, saved: dict) -> None:
    module._run_doctor = saved["doctor"]
    module._run_build = saved["build"]
    module.godot_executable = saved["executable"]
    module.godot_version = saved["version"]
    module._godot_command = saved["command"]
    module._warm_fixture = saved["warm"]
    module.subprocess.run = saved["run"]


def test_structured_config_and_excludes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / "extern" / "gdextest").mkdir(parents=True)
        (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
        (root / "tests" / "unit").mkdir(parents=True)
        (root / "tests" / "generated").mkdir()
        (root / "tests" / "unit" / "one.cpp").write_text("", encoding="utf-8")
        (root / "tests" / "generated" / "two.cpp").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\nexclude = [\"tests/generated\"]\n[gdextest.host]\nmode = \"runtime\"\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert config.host_mode == "runtime"
        assert [path.name for path in config_module.discover_sources(config)] == ["one.cpp"]
        assert config.validate() == []


def test_toml_unterminated_string_raises() -> None:
    """A missing closing quote must fail the parse, not silently drop sources.

    Regression: `sources = ["a", "b]` used to parse as ["a", '"b'] — the
    mangled pattern matched no files, which silently compiled a test library
    missing the code under test (surfacing later as undefined symbols).
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".gdextest.toml").write_text(
            '[gdextest.tests]\nsources = ["tests/**/*.cpp", "src/**/*.cpp]\n',
            encoding="utf-8")
        try:
            config_module.load_toml(root / ".gdextest.toml")
        except ValueError as error:
            assert "unterminated string" in str(error)
        else:
            raise AssertionError("unterminated string must raise ValueError")


def test_toml_multiline_array_parses() -> None:
    """Arrays may span lines; the parser joins until brackets balance."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".gdextest.toml").write_text(
            '[gdextest.tests]\nsources = [\n  "tests/**/*.cpp",\n  "src/**/*.cpp",\n]\n',
            encoding="utf-8")
        parsed = config_module.load_toml(root / ".gdextest.toml")
        assert parsed["gdextest"]["tests"]["sources"] == [
            "tests/**/*.cpp", "src/**/*.cpp"]


def test_toml_hash_inside_string_is_literal() -> None:
    """'#' inside a quoted value is not a comment start."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".gdextest.toml").write_text(
            '[gdextest.fixture]\nproject_name = "tests #1"  # trailing comment\n',
            encoding="utf-8")
        parsed = config_module.load_toml(root / ".gdextest.toml")
        assert parsed["gdextest"]["fixture"]["project_name"] == "tests #1"


def test_extension_sources_resolve_alongside_suites() -> None:
    """The consumer layout: suites plus the extension's own sources."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / "extern" / "gdextest").mkdir(parents=True)
        (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "text_conversion_tests.cpp").write_text("", encoding="utf-8")
        (root / "src" / "text").mkdir(parents=True)
        (root / "src" / "text" / "text_conversion.cpp").write_text("", encoding="utf-8")
        # Vendored C dependency (e.g. md4c) must also resolve.
        (root / "src" / "text" / "md4c.c").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            '[gdextest]\nminimum_required_godot_version = "4.5"\n[gdextest.tests]\n'
            'sources = ["tests/**/*.cpp", "src/**/*.cpp", "src/**/*.c"]\n',
            encoding="utf-8")
        config = config_module.load_config(root)
        sources = config_module.resolve_sources(config)
        assert [path.name for path in sources] == [
            "md4c.c", "text_conversion.cpp", "text_conversion_tests.cpp"]


def test_zero_match_source_pattern_raises() -> None:
    """A configured pattern matching nothing fails loudly instead of silently
    compiling a library that is missing the code under test."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / "extern" / "gdextest").mkdir(parents=True)
        (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "suite.cpp").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            '[gdextest]\nminimum_required_godot_version = "4.5"\n[gdextest.tests]\n'
            'sources = ["tests/**/*.cpp", "src/**/*.cpp"]\n',
            encoding="utf-8")
        config = config_module.load_config(root)
        matches = config_module.source_pattern_matches(config)
        assert len(matches["tests/**/*.cpp"]) == 1
        assert matches["src/**/*.cpp"] == []
        try:
            config_module.resolve_sources(config)
        except RuntimeError as error:
            assert "src/**/*.cpp" in str(error)
            assert "matched no C++ files" in str(error)
        else:
            raise AssertionError("zero-match pattern must raise RuntimeError")
        # discover_sources keeps its lenient contract for existing callers.
        assert [path.name for path in config_module.discover_sources(config)] == [
            "suite.cpp"]


def test_doctor_reports_zero_match_pattern() -> None:
    """Doctor names the pattern that matched nothing and exits non-zero."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        (root / "src").mkdir()
        (root / ".gdextest.toml").write_text(
            '[gdextest]\nminimum_required_godot_version = "4.5"\n[gdextest.tests]\n'
            'sources = ["tests/**/*.cpp", "src/**/*.cpp"]\n',
            encoding="utf-8")
        config = config_module.load_config(root)
        original_which = cli.shutil.which
        original_godot = cli.godot_executable
        original_version = cli.godot_version
        try:
            cli.shutil.which = lambda name: "/usr/bin/scons" if name == "scons" else None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            assert cli._run_doctor(config, "/usr/bin/godot") == 2
        finally:
            cli.shutil.which = original_which
            cli.godot_executable = original_godot
            cli.godot_version = original_version


def test_init_is_idempotent_without_force() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        cli._write_config(root)
        config_path = root / ".gdextest.toml"
        original = config_path.read_text(encoding="utf-8")
        config_path.write_text("consumer configuration", encoding="utf-8")

        changed = cli._write_config(root)

        assert not changed
        assert config_path.read_text(encoding="utf-8") == "consumer configuration"
        assert original != config_path.read_text(encoding="utf-8")


def test_doctor_rejects_empty_source_set() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / "extern" / "gdextest").mkdir(parents=True)
        (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        original_which = cli.shutil.which
        original_godot = cli.godot_executable
        original_version = cli.godot_version
        try:
            cli.shutil.which = lambda name: "/usr/bin/scons" if name == "scons" else None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            result = cli._run_doctor(config, "/usr/bin/godot")
        finally:
            cli.shutil.which = original_which
            cli.godot_executable = original_godot
            cli.godot_version = original_version

        assert result == 2


def test_test_auto_initializes_and_checks_before_build() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / "extern" / "gdextest").mkdir(parents=True)
        (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "smoke.cpp").write_text("", encoding="utf-8")
        args = cli.argparse.Namespace(
            project_root=root,
            framework_dir=None,
            godot="/usr/bin/godot",
            filter=None,
            shard=None,
            shuffle=None,
            json=None,
        )
        events = []
        original_doctor = cli._run_doctor
        original_build = cli._run_build
        original_executable = cli.godot_executable
        original_version = cli.godot_version
        original_command = cli._godot_command
        original_run = cli.subprocess.run
        try:
            cli._run_doctor = lambda config, godot, allow_injection=False: events.append("doctor") or 0
            cli._run_build = lambda config: events.append("build")
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            cli._godot_command = lambda config, executable, *user_args: events.append("command") or []
            cli.subprocess.run = lambda *command, **kwargs: type("Result", (), {"returncode": 0})()
            result = cli.cmd_test(args)
        finally:
            cli._run_doctor = original_doctor
            cli._run_build = original_build
            cli.godot_executable = original_executable
            cli.godot_version = original_version
            cli._godot_command = original_command
            cli.subprocess.run = original_run

        assert result == 0
        assert (root / ".gdextest.toml").is_file()
        assert events == ["doctor", "build", "command"]


def test_unwired_build_injects_temporary_sconstruct() -> None:
    """An unwired SConstruct builds via a temporary injected SConstruct that is
    cleaned up afterwards; the real build file stays untouched."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)   # empty SConstruct -> unwired
        (root / "bin").mkdir()
        (root / "bin" / "libgdextest.linux.template_debug.x86_64.so").write_bytes(b"")
        config = config_module.load_config(root)
        captured = {}
        original_run = cli.subprocess.run
        try:
            def fake_run(command, **kwargs):
                if command and command[0] == "ldd":
                    # Undefined-symbol preflight; not the command under test.
                    return type("Result", (), {"returncode": 0,
                                                "stdout": "", "stderr": ""})()
                captured["command"] = list(command)
                # Read while the temporary SConstruct still exists (cleanup
                # happens in _run_build's finally, after this returns).
                captured["injected"] = Path(command[2]).read_text(encoding="utf-8")
                return type("Result", (), {"returncode": 0})()
            cli.subprocess.run = fake_run
            cli._run_build(config)
        finally:
            cli.subprocess.run = original_run
        assert captured["command"][:2] == ["scons", "-f"]
        injected = Path(captured["command"][2])
        assert injected.name == "SConstruct.gdextest"
        assert injected.parent == root
        assert "extern/gdextest/SConscript" in captured["injected"]
        assert not injected.exists(), "temporary SConstruct must be cleaned up"
        assert (root / "SConstruct").read_text(encoding="utf-8") == ""


def test_runtime_fixture_has_autoload_not_editor_plugin() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        library = root / "libtest.so"
        library.write_bytes(b"test")
        fixture = root / "fixture"
        generator.generate_fixture(
            project_root=fixture,
            library_path=library,
            library_basename="libtest.so",
            manifest_basename="test.gdextension",
            host_mode="runtime",
        )
        project = (fixture / "project.godot").read_text(encoding="utf-8")
        assert "[autoload]" in project
        assert "[editor_plugins]" not in project
        assert (fixture / "addons" / "gdextest" / "runtime.gd").is_file()
        assert not (fixture / "addons" / "gdextest" / "plugin.cfg").exists()


def _consumer_root(directory: str, sconstruct: str = "") -> Path:
    """Create a minimal consumer repo layout used by the CLI tests."""
    root = Path(directory)
    (root / "SConstruct").write_text(sconstruct, encoding="utf-8")
    (root / "extern" / "gdextest").mkdir(parents=True)
    (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "smoke.cpp").write_text("", encoding="utf-8")
    return root


def test_build_uses_gdextest_env_contract() -> None:
    """The CLI sets gdextest_* vars and the SConscript reads the same names."""
    scons_script = (ROOT / "SConscript").read_text(encoding="utf-8")
    for name in ("gdextest_SOURCES", "gdextest_BOOTSTRAP", "gdextest_HOST_MODE"):
        assert name in scons_script
    for stale in ("GDEXTEST_SOURCES", "GDEXTEST_BOOTSTRAP", "GDEXTEST_HOST_MODE"):
        assert stale not in scons_script
    # Test-library objects get explicit targets under the framework variant dir
    # (build/gdextest/obj/...): a host build that compiles the same sources in
    # place must never fight the test build for the same object paths
    # ("Two environments with different actions..." graph error).
    assert "SharedObject(" in scons_script

    wired = ("env = Environment(tools=['default'])\n"
             "env.SConscript('extern/gdextest/SConscript',\n"
             "    variant_dir='build/gdextest', duplicate=0,\n"
             "    exports={'env': env})\n")
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory, sconstruct=wired)
        (root / "bin").mkdir()
        (root / "bin" / "libgdextest.linux.template_debug.x86_64.so").write_bytes(b"")
        config = config_module.load_config(root)
        captured = {}
        original_run = cli.subprocess.run
        try:
            def fake_run(command, **kwargs):
                if command and command[0] == "ldd":
                    # Undefined-symbol preflight; not the command under test.
                    return type("Result", (), {"returncode": 0,
                                                "stdout": "", "stderr": ""})()
                captured["command"] = list(command)
                captured["env"] = kwargs.get("env", {})
                return type("Result", (), {"returncode": 0})()
            cli.subprocess.run = fake_run
            cli._run_build(config)
        finally:
            cli.subprocess.run = original_run
        assert captured["command"] == ["scons", "tests=true"]
        assert captured["env"]["gdextest_PROJECT_ROOT"] == str(root)
        assert captured["env"]["gdextest_SOURCES"] == "tests/smoke.cpp"
        assert captured["env"]["gdextest_HOST_MODE"] == "editor"
        assert "GDEXTEST_SOURCES" not in captured["env"]


def test_scons_command_includes_build_args() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n[gdextest.build]\nargs = [\"platform=linux\", \"target=editor\"]\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert cli._scons_command(config) == ["scons", "tests=true", "platform=linux", "target=editor"]


def test_run_build_verifies_library_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        config = config_module.load_config(root)
        original_run = cli.subprocess.run
        try:
            cli.subprocess.run = lambda *command, **kwargs: type("Result", (), {"returncode": 0})()
            try:
                cli._run_build(config)
                assert False, "expected RuntimeError when the SConscript did not run"
            except RuntimeError as error:
                assert "does not appear to call" in str(error)
            (root / "bin").mkdir()
            (root / "bin" / "libgdextest.linux.template_debug.x86_64.so").write_bytes(b"")
            cli._run_build(config)
        finally:
            cli.subprocess.run = original_run


def test_run_environment_wipes_previous_user_data() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        config = config_module.load_config(root)
        user_data = root / config.build_dir / "user-data"
        user_data.mkdir(parents=True)
        stale = user_data / "residue.txt"
        stale.write_text("from a previous run", encoding="utf-8")
        environment = cli._run_environment(config)
        assert not stale.exists()
        assert user_data.is_dir()
        assert environment["XDG_DATA_HOME"] == str(user_data)


def test_extension_manifest_derived_from_library() -> None:
    """Setting only the library path derives the .gdextension manifest."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        addon = root / "addons" / "gcs"
        (addon / "bin").mkdir(parents=True)
        (addon / "bin" / "libgcs.linux.editor.x86_64.so").write_bytes(b"lib")
        (addon / "gcs.gdextension").write_text(
            '[configuration]\nentry_symbol = "gcs_library_init"\n', encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n"""
            "[gdextest.consumer_extension]\n"
            'library = "addons/gcs/bin/libgcs.linux.editor.x86_64.so"\n',
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert config.extension_manifest == "addons/gcs/gcs.gdextension"
        assert config.validate() == []


def test_extension_library_derived_from_manifest() -> None:
    """Setting only the manifest derives the library from its [libraries] table."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        addon = root / "addons" / "gcs"
        (addon / "bin").mkdir(parents=True)
        (addon / "bin" / "libgcs.linux.debug.x86_64.so").write_bytes(b"lib")
        (addon / "gcs.gdextension").write_text(
            "[configuration]\nentry_symbol = \"gcs_library_init\"\n"
            "[libraries]\n"
            'linux.debug.x86_64 = "res://addons/gcs/bin/libgcs.linux.debug.x86_64.so"\n',
            encoding="utf-8",
        )
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n"""
            "[gdextest.consumer_extension]\n"
            'manifest = "addons/gcs/gcs.gdextension"\n',
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert config.extension_library == "addons/gcs/bin/libgcs.linux.debug.x86_64.so"
        assert config.validate() == []


def test_extension_pair_still_validates_when_derivation_ambiguous() -> None:
    """Multiple manifests near the library fail validation with a clear error."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        addon = root / "addons" / "gcs"
        (addon / "bin").mkdir(parents=True)
        (addon / "bin" / "libgcs.so").write_bytes(b"lib")
        (addon / "gcs.gdextension").write_text("", encoding="utf-8")
        (addon / "bin" / "other.gdextension").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n"""
            "[gdextest.consumer_extension]\n"
            'library = "addons/gcs/bin/libgcs.so"\n',
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        errors = config.validate()
        assert any("extension_manifest is required" in error for error in errors)


def test_fixture_removed_after_test_run() -> None:
    """The fixture is disposable: removed after the run, even on failure."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        fixture = root / "build" / "gdextest" / "project"
        fixture.mkdir(parents=True)
        (fixture / "project.godot").write_text("generated", encoding="utf-8")
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[],)
        original_doctor = cli._run_doctor
        original_build = cli._run_build
        original_executable = cli.godot_executable
        original_version = cli.godot_version
        original_command = cli._godot_command
        original_warm = cli._warm_fixture
        original_run = cli.subprocess.run
        try:
            cli._run_doctor = lambda config, godot, allow_injection=False: 0
            cli._run_build = lambda config: None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            cli._godot_command = lambda config, executable, *user_args: ["godot"]
            cli._warm_fixture = lambda config, executable: None
            # Red run: the fixture must still be cleaned up.
            cli.subprocess.run = lambda *command, **kwargs: type(
                "Result", (), {"returncode": 1})()
            assert cli.cmd_test(args) == 1
        finally:
            cli._run_doctor = original_doctor
            cli._run_build = original_build
            cli.godot_executable = original_executable
            cli.godot_version = original_version
            cli._godot_command = original_command
            cli._warm_fixture = original_warm
            cli.subprocess.run = original_run
        assert not fixture.exists(), "fixture must be removed after the run"


def test_fixture_removed_after_list() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        fixture = root / "build" / "gdextest" / "project"
        fixture.mkdir(parents=True)
        (fixture / "project.godot").write_text("generated", encoding="utf-8")
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            passthrough=[],)
        original_build = cli._run_build
        original_executable = cli.godot_executable
        original_warm = cli._warm_fixture
        original_run = cli.subprocess.run
        try:
            cli._run_build = lambda config: None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli._warm_fixture = lambda config, executable: None
            cli.subprocess.run = lambda *command, **kwargs: type(
                "Result", (), {"returncode": 0})()
            assert cli.cmd_list(args) == 0
        finally:
            cli._run_build = original_build
            cli.godot_executable = original_executable
            cli._warm_fixture = original_warm
            cli.subprocess.run = original_run
        assert not fixture.exists(), "fixture must be removed after list"


def test_keep_fixture_retains_on_failure_removes_on_success() -> None:
    """`--keep-fixture` retains the fixture on a failed run, but still cleans up
    a green one; the default (no flag) always removes."""
    for keep, run_code, should_exist in ((True, 1, True),   # failed run, flag -> kept
                                         (True, 0, False),  # green run, flag -> removed
                                         (False, 1, False),  # failed run, no flag -> removed
                                         (False, 0, False)):  # green run, no flag -> removed
        with tempfile.TemporaryDirectory() as directory:
            root = _consumer_root(directory)
            fixture = root / "build" / "gdextest" / "project"
            fixture.mkdir(parents=True)
            (fixture / "project.godot").write_text("generated", encoding="utf-8")
            args = cli.argparse.Namespace(
                project_root=root, framework_dir=None, godot="/usr/bin/godot",
                filter=None, shard=None, shuffle=None, json=None, junit=None,
                passthrough=[], keep_fixture=keep)
            original_doctor = cli._run_doctor
            original_build = cli._run_build
            original_executable = cli.godot_executable
            original_version = cli.godot_version
            original_command = cli._godot_command
            original_warm = cli._warm_fixture
            original_run = cli.subprocess.run
            try:
                cli._run_doctor = lambda config, godot, allow_injection=False: 0
                cli._run_build = lambda config: None
                cli.godot_executable = lambda config, override: "/usr/bin/godot"
                cli.godot_version = lambda executable: "4.5"
                cli._godot_command = lambda config, executable, *user_args: ["godot"]
                cli._warm_fixture = lambda config, executable: None
                cli.subprocess.run = lambda *command, **kwargs: type(
                    "Result", (), {"returncode": run_code})()
                assert cli.cmd_test(args) == run_code
            finally:
                cli._run_doctor = original_doctor
                cli._run_build = original_build
                cli.godot_executable = original_executable
                cli.godot_version = original_version
                cli._godot_command = original_command
                cli._warm_fixture = original_warm
                cli.subprocess.run = original_run
            assert fixture.exists() is should_exist, \
                f"keep={keep} run_code={run_code}: fixture exists={fixture.exists()}"


def test_remove_fixture_refuses_project_root() -> None:
    """A fixture path at or above the project root is never deleted."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n[gdextest.fixture]\ndirectory = \".\"\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        marker = root / "keep.txt"
        marker.write_text("do not delete", encoding="utf-8")
        cli._remove_fixture(config)
        assert marker.is_file(), "project root must never be removed"


def test_doctor_flags_unwired_sconstruct() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory, sconstruct="env = Environment()\n")
        config = config_module.load_config(root)
        original_which = cli.shutil.which
        original_godot = cli.godot_executable
        original_version = cli.godot_version
        try:
            cli.shutil.which = lambda name: "/usr/bin/scons" if name == "scons" else None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            assert cli._run_doctor(config, "/usr/bin/godot") == 2
        finally:
            cli.shutil.which = original_which
            cli.godot_executable = original_godot
            cli.godot_version = original_version


def test_doctor_passes_when_sconstruct_is_wired() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(
            directory, sconstruct='env = Environment()\nenv.SConscript("extern/gdextest/SConscript")\n')
        config = config_module.load_config(root)
        original_which = cli.shutil.which
        original_godot = cli.godot_executable
        original_version = cli.godot_version
        try:
            cli.shutil.which = lambda name: "/usr/bin/scons" if name == "scons" else None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            assert cli._run_doctor(config, "/usr/bin/godot") == 0
        finally:
            cli.shutil.which = original_which
            cli.godot_executable = original_godot
            cli.godot_version = original_version


def test_scaffold_apply_wires_and_generates() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("env = Environment()\n", encoding="utf-8")
        (root / "extern" / "gdextest").mkdir(parents=True)
        (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\n[gdextest.host]\nentry_symbol = \"my_library_init\"\nplugin_class = \"MyTestPlugin\"\n""",
            encoding="utf-8",
        )
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot=None, apply=True, force=False)
        original_doctor = cli._run_doctor
        try:
            cli._run_doctor = lambda config, godot, allow_injection=False: 0
            result = cli.cmd_scaffold(args)
        finally:
            cli._run_doctor = original_doctor
        assert result == 0
        sconstruct = (root / "SConstruct").read_text(encoding="utf-8")
        assert "extern/gdextest/SConscript" in sconstruct
        assert "testsupport/entry.cpp" in sconstruct
        assert (root / "SConstruct.gdextest.bak").is_file()
        entry = (root / "testsupport" / "entry.cpp").read_text(encoding="utf-8")
        assert "class MyTestPlugin" in entry
        assert "GDE_EXPORT my_library_init" in entry
        # The entry lives outside the tests/ glob so it is not double-compiled.
        assert not (root / "tests" / "support" / "entry.cpp").exists()
        assert (root / "tests" / "smoke.cpp").is_file()


def test_sconstruct_wiring_detection_ignores_godot_cpp_path() -> None:
    """A gdextest mention in a godot-cpp path is not a wiring reference."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text(
            'cpp_root = "#extern/gdextest/extern/godot-cpp"\n'
            'env.SConscript(cpp_root + "/SConstruct")\n',
            encoding="utf-8",
        )
        assert not cli._sconstruct_wired(root)
        # The documented consumer wiring is detected.
        (root / "SConstruct").write_text(
            'env.SConscript("extern/gdextest/SConscript")\n', encoding="utf-8")
        assert cli._sconstruct_wired(root)


def test_scaffold_without_apply_does_not_patch() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("env = Environment()\n", encoding="utf-8")
        (root / "extern" / "gdextest").mkdir(parents=True)
        (root / "extern" / "gdextest" / "SConscript").write_text("", encoding="utf-8")
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot=None, apply=False, force=False)
        assert cli.cmd_scaffold(args) == 2
        assert "gdextest" not in (root / "SConstruct").read_text(encoding="utf-8")
        assert not (root / "SConstruct.gdextest.bak").exists()


def test_cmd_test_passes_through_gdextest_args() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        args = cli.argparse.Namespace(
            project_root=root,
            framework_dir=None,
            godot="/usr/bin/godot",
            filter=None,
            shard=None,
            shuffle=None,
            json=None,
            junit=None,
            passthrough=["--gdextest-some-new-flag=1"],
        )
        captured = []
        original_doctor = cli._run_doctor
        original_build = cli._run_build
        original_executable = cli.godot_executable
        original_version = cli.godot_version
        original_command = cli._godot_command
        original_run = cli.subprocess.run
        try:
            cli._run_doctor = lambda config, godot, allow_injection=False: 0
            cli._run_build = lambda config: None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            cli._godot_command = lambda config, executable, *user_args: captured.append(user_args) or []
            cli.subprocess.run = lambda *command, **kwargs: type("Result", (), {"returncode": 0})()
            result = cli.cmd_test(args)
        finally:
            cli._run_doctor = original_doctor
            cli._run_build = original_build
            cli.godot_executable = original_executable
            cli.godot_version = original_version
            cli._godot_command = original_command
            cli.subprocess.run = original_run
        assert result == 0
        assert captured[0][:4] == ("--gdextest-some-new-flag=1",
                                   "--gdextest-timeout-ms=30000",
                                   "--gdextest-isolate-timeout-sec=60",
                                   "--gdextest-flaky-retries=3")
        # Since the captured-output reporting (M2/M3): without --json the CLI
        # appends its own temp JSON target plus the quiet in-engine report
        # flag; the --gdextest-report-path copy is only forwarded when the
        # user named a document target explicitly (see the --json test).
        assert len(captured[0]) == 6
        assert captured[0][4].startswith("--gdextest-json=")
        assert captured[0][5] == "--gdextest-report=quiet"


def test_timeout_budgets_forwarded_from_toml() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\n[gdextest.test]\ntimeout_ms = 5000\nisolate_timeout_sec = 120\nflaky_retries = 5\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert (config.timeout_ms, config.isolate_timeout_sec, config.flaky_retries) == (5000, 120, 5)
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None, passthrough=[])
        captured = []
        original_doctor = cli._run_doctor
        original_build = cli._run_build
        original_executable = cli.godot_executable
        original_version = cli.godot_version
        original_command = cli._godot_command
        original_run = cli.subprocess.run
        try:
            cli._run_doctor = lambda config, godot, allow_injection=False: 0
            cli._run_build = lambda config: None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            cli._godot_command = lambda config, executable, *user_args: captured.append(user_args) or []
            cli.subprocess.run = lambda *command, **kwargs: type("Result", (), {"returncode": 0})()
            cli.cmd_test(args)
        finally:
            cli._run_doctor = original_doctor
            cli._run_build = original_build
            cli.godot_executable = original_executable
            cli.godot_version = original_version
            cli._godot_command = original_command
            cli.subprocess.run = original_run
        assert "--gdextest-timeout-ms=5000" in captured[0]
        assert "--gdextest-isolate-timeout-sec=120" in captured[0]
        assert "--gdextest-flaky-retries=5" in captured[0]


def test_json_to_junit_conversion() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        json_path = root / "results.json"
        json_path.write_text(json.dumps({
            "totals": {"pass": 1, "fail": 1, "skip": 1, "crashed": 0},
            "results": [
                {"suite": "a", "name": "passes", "status": "pass",
                 "duration_ms": 1, "retries": 0, "failures": []},
                {"suite": "a", "name": "fails", "status": "fail", "duration_ms": 2,
                 "retries": 0, "failures": [{"file": "tests/a.cpp", "line": 3,
                                                "message": "expected a == b"}]},
                {"suite": "b", "name": "skips", "status": "skipped",
                 "reason": "no service", "duration_ms": 0, "retries": 0, "failures": []},
            ],
        }), encoding="utf-8")
        junit_path = root / "results.xml"
        cli._json_to_junit(str(json_path), str(junit_path))
        xml_text = junit_path.read_text(encoding="utf-8")
        assert 'tests="3"' in xml_text
        assert 'failures="1"' in xml_text
        assert 'skipped="1"' in xml_text
        assert 'time="0.003"' in xml_text
        assert 'classname="a"' in xml_text
        # One <testsuite> per test suite, in first-appearance order, each with
        # its own counts and aggregate duration in seconds (dorny/test-reporter
        # reads suite-level `time`; a missing attribute renders as NaNms).
        root = ET.fromstring(xml_text)
        assert root.tag == "testsuites"
        assert root.get("tests") == "3" and root.get("time") == "0.003"
        suites = root.findall("testsuite")
        assert [suite.get("name") for suite in suites] == ["a", "b"]
        suite_a, suite_b = suites
        assert suite_a.get("tests") == "2" and suite_a.get("failures") == "1"
        assert suite_a.get("skipped") == "0" and suite_a.get("time") == "0.003"
        assert [case.get("name") for case in suite_a.findall("testcase")] == ["passes", "fails"]
        assert suite_b.get("tests") == "1" and suite_b.get("failures") == "0"
        assert suite_b.get("skipped") == "1" and suite_b.get("time") == "0.000"
        assert suite_b.find("testcase").get("classname") == "b"
        assert 'name="fails"' in xml_text
        assert "expected a == b" in xml_text
        assert 'message="no service"' in xml_text


def test_is_msvc_compiler_detection() -> None:
    """The SConscript's MSVC branch triggers only for the MSVC front end.

    clang must never match a "cl" prefix, and PLATFORM=win32 alone must not
    force MSVC flags onto MinGW or GNU-front-end clang.
    """
    msvc_cases = [
        {"CC": "cl"},
        {"CC": "CL.EXE"},
        {"CC": "C:/Program Files/Microsoft Visual Studio/VC/cl.exe"},
        {"CC": "clang-cl"},
        {"CC": "clang-cl.exe"},
        # No explicit compiler: trust godot-cpp's flag or the SCons tool set.
        {"CC": "", "is_msvc": True},
        {"CC": "gcc", "is_msvc": True},
        {"CC": "", "TOOLS": ["default", "msvc"]},
    ]
    for env in msvc_cases:
        assert compiler_module.is_msvc(env), f"expected MSVC for {env}"
    gcc_cases = [
        {"CC": "gcc"},
        {"CC": "g++"},
        {"CC": "clang"},
        {"CC": "clang++"},
        {"CC": "clang.exe"},
        {"CC": "/usr/bin/clang++"},
        {"CC": "ccache clang"},
        {"CC": "ccache gcc", "PLATFORM": "win32"},
        {"CC": "clang", "PLATFORM": "win32"},
        {"CC": "gcc", "TOOLS": ["default", "mingw"]},
        {"CC": "i686-w64-mingw32-gcc", "PLATFORM": "win32"},
        {"CC": ""},
    ]
    for env in gcc_cases:
        assert not compiler_module.is_msvc(env), f"expected non-MSVC for {env}"


def test_sconscript_selects_flags_by_compiler_family() -> None:
    """MSVC-only flags go to MSVC; GCC/Clang flags go to clang and MinGW."""
    scons_script = (ROOT / "SConscript").read_text(encoding="utf-8")
    assert "_compiler_module.is_msvc(test_env)" in scons_script
    assert 'test_env.get("PLATFORM") == "win32"' not in scons_script


def test_report_merges_shard_documents() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "shard0.json").write_text(json.dumps({
            "totals": {"pass": 2, "fail": 0, "skip": 1, "crashed": 0},
            "results": [
                {"suite": "s", "name": "p1", "status": "pass", "duration_ms": 1, "retries": 0, "failures": []},
                {"suite": "s", "name": "p2", "status": "pass", "duration_ms": 1, "retries": 0, "failures": []},
                {"suite": "s", "name": "k1", "status": "skipped", "reason": "x", "duration_ms": 0, "retries": 0, "failures": []},
            ],
        }), encoding="utf-8")
        (root / "shard1.json").write_text(json.dumps({
            "totals": {"pass": 0, "fail": 1, "skip": 0, "crashed": 1},
            "results": [
                {"suite": "s", "name": "f1", "status": "fail", "duration_ms": 2, "retries": 0,
                 "failures": [{"file": "x.cpp", "line": 1, "message": "boom"}]},
                {"suite": "s", "name": "c1", "status": "crashed", "duration_ms": 3, "retries": 0, "failures": []},
            ],
        }), encoding="utf-8")
        args = cli.argparse.Namespace(
            paths=["shard*.json"], json="merged.json", junit="merged.xml")
        original_cwd = os.getcwd()
        try:
            os.chdir(root)
            result = cli.cmd_report(args)
        finally:
            os.chdir(original_cwd)
        assert result == 1
        merged = json.loads((root / "merged.json").read_text(encoding="utf-8"))
        assert merged["totals"] == {"pass": 2, "fail": 2, "skip": 1, "crashed": 1}
        assert len(merged["results"]) == 5
        assert (root / "merged.xml").is_file()
        # The merged JUnit report regroups all shards back into per-suite
        # elements with recomputed totals and durations.
        root_element = ET.fromstring((root / "merged.xml").read_text(encoding="utf-8"))
        assert root_element.get("tests") == "5" and root_element.get("time") == "0.007"
        merged_suites = root_element.findall("testsuite")
        assert [suite.get("name") for suite in merged_suites] == ["s"]
        merged_suite = merged_suites[0]
        assert merged_suite.get("tests") == "5" and merged_suite.get("failures") == "2"
        assert merged_suite.get("skipped") == "1" and merged_suite.get("time") == "0.007"
        assert len(merged_suite.findall("testcase")) == 5


def test_godot_discovery_finds_nearby_binary() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        executable = root / "Godot_v4.5-stable_linux.x86_64"
        executable.write_bytes(b"#!/bin/sh\n")
        executable.chmod(0o755)
        (root / "Godot_v4.2-stable_linux.x86_64").write_bytes(b"#!/bin/sh\n")
        (root / "Godot_v4.2-stable_linux.x86_64").chmod(0o755)
        config = config_module.load_config(root)
        original_which = config_module.shutil.which
        try:
            config_module.shutil.which = lambda name: None
            found = config_module.godot_executable(config)
        finally:
            config_module.shutil.which = original_which
        # The binary matching the configured 4.5 wins over the 4.2 one.
        assert found == str(executable)


def test_doctor_godot_cpp_version_checks() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory, sconstruct='env = Environment()\nenv.SConscript("extern/gdextest/SConscript")\n')
        config = config_module.load_config(root)
        original_which = cli.shutil.which
        original_godot = cli.godot_executable
        original_version = cli.godot_version
        original_cpp = cli.godot_cpp_version
        try:
            cli.shutil.which = lambda name: "/usr/bin/scons" if name == "scons" else None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_version = lambda executable: "4.5"
            # A mismatch is a loud warning, not a doctor failure.
            cli.godot_cpp_version = lambda root: "4.4"
            assert cli._run_doctor(config, "/usr/bin/godot") == 0
            # A match passes the check.
            cli.godot_cpp_version = lambda root: "4.5"
            assert cli._run_doctor(config, "/usr/bin/godot") == 0
            # Missing godot-cpp is a note, not a failure.
            cli.godot_cpp_version = lambda root: None
            assert cli._run_doctor(config, "/usr/bin/godot") == 0
        finally:
            cli.shutil.which = original_which
            cli.godot_executable = original_godot
            cli.godot_version = original_version
            cli.godot_cpp_version = original_cpp


def test_version_at_least_accepts_higher_binaries() -> None:
    """The Godot check is a floor, so a newer binary is valid."""
    at_least = config_module.version_at_least
    assert at_least("4.5", "4.5") is True     # exact minimum passes
    assert at_least("4.5.3", "4.5") is True   # patch above minimum passes
    assert at_least("4.6", "4.5") is True      # newer minor passes
    assert at_least("5.0", "4.5") is True      # newer major passes
    assert at_least("4.4", "4.5") is False     # below minimum fails
    assert at_least("", "4.5") is False        # unparseable fails


def test_doctor_enforces_minimum_godot_without_capping_high() -> None:
    """Doctor passes binaries at or above the minimum and rejects lower ones."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(
            directory, sconstruct='env = Environment()\nenv.SConscript("extern/gdextest/SConscript")\n')
        config = config_module.load_config(root)
        original_which = cli.shutil.which
        original_godot = cli.godot_executable
        original_version = cli.godot_version
        original_cpp = cli.godot_cpp_version
        try:
            cli.shutil.which = lambda name: "/usr/bin/scons" if name == "scons" else None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli.godot_cpp_version = lambda root: "4.5"
            # A newer binary is valid; a lower one is not.
            cli.godot_version = lambda executable: "4.6"
            assert cli._run_doctor(config, "/usr/bin/godot") == 0
            cli.godot_version = lambda executable: "4.4"
            assert cli._run_doctor(config, "/usr/bin/godot") == 2
        finally:
            cli.shutil.which = original_which
            cli.godot_executable = original_godot
            cli.godot_version = original_version
            cli.godot_cpp_version = original_cpp


def test_warm_fixture_runs_only_when_cold() -> None:
    """The first-run cache warmup runs once, then is skipped on warm fixtures."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        config = config_module.load_config(root)
        commands = []
        original_run = cli.subprocess.run
        try:
            cli.subprocess.run = (lambda *command, **kwargs:
                                  commands.append(command) or type("Result", (), {"returncode": 134})())
            cli._warm_fixture(config, "/usr/bin/godot")
            assert len(commands) == 1
            assert "--quit-after" in commands[0][0]
            # A warm fixture (cache present) skips the warmup entirely.
            (config.fixture_path / ".godot").mkdir(parents=True)
            cli._warm_fixture(config, "/usr/bin/godot")
            assert len(commands) == 1
        finally:
            cli.subprocess.run = original_run


def test_scan_timeout_config_parses() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            """[gdextest]\nminimum_required_godot_version = \"4.5\"\n[gdextest.fixture]\nscan_timeout_ms = 90000\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert config.scan_timeout_ms == 90000


def test_report_output_config_keys_parse() -> None:
    """[gdextest.test] report/color/raw_log parse with "cli"/"auto"/"" defaults."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            "[gdextest]\nminimum_required_godot_version = \"4.5\"\n"
            "[gdextest.test]\n"
            'report = "pretty"\n'
            'color = "never"\n'
            'raw_log = "build/godot-output.log"\n',
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert config.report == "pretty"
        assert config.color == "never"
        assert config.raw_log == "build/godot-output.log"
        # Defaults when the keys are absent.
        bare = config_module.load_config(_consumer_root(tempfile.mkdtemp()))
        assert bare.report == "cli"
        assert bare.color == "auto"
        assert bare.raw_log == ""


def test_report_output_config_keys_validate() -> None:
    """Invalid report/color values fail validation with the value named."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "SConstruct").write_text("", encoding="utf-8")
        (root / ".gdextest.toml").write_text(
            "[gdextest]\nminimum_required_godot_version = \"4.5\"\n"
            "[gdextest.test]\n"
            'report = "loud"\n'
            'color = "maybe"\n',
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        errors = config.validate()
        assert any("report" in error and "loud" in error for error in errors)
        assert any("color" in error and "maybe" in error for error in errors)


def _godot_run_stub(stdout: str = "", stderr: str = "", returncode: int = 0,
                    document: dict | None = None):
    """A subprocess.run stub for the Godot invocation: returns a captured result
    and, when `document` is given, writes it to the `--gdextest-json=` path the
    CLI appended — mirroring what the in-engine runner does."""
    def _run(command, **kwargs):
        if document is not None:
            for arg in command:
                if arg.startswith("--gdextest-json="):
                    Path(arg.split("=", 1)[1]).write_text(
                        json.dumps(document), encoding="utf-8")
        return type("Result", (), {"returncode": returncode,
                                   "stdout": stdout, "stderr": stderr})()
    return _run


_ENGINE_NOISE = ("Godot Engine v4.5.stable.official - https://godotengine.org\n"
                 "Vulkan API 0.0.0.0 - Running with dummy rendering driver\n"
                 "LoadingGDExtension: gdextest.gdextension loaded\n")


def test_split_captured_output_classifies_markers() -> None:
    marked, noise = cli._split_captured_output(
        "GDX_TEST_OUTPUT: [PASS] a.b\nGodot noise line\n", "stderr chatter\n")
    assert marked == "[PASS] a.b"
    assert "Godot noise line" in noise and "stderr chatter" in noise


def test_extract_list_output_parses_legacy_block() -> None:
    captured = ("Godot banner line\n# gdextest list: 2 tests\n"
                "suite.one\nsuite.two\n\nGodot chatter with spaces resumes\n")
    assert cli._extract_list_output(captured) == [
        "# gdextest list: 2 tests", "suite.one", "suite.two"]


def test_extract_list_output_parses_marker_block() -> None:
    """The M3 runner marker-prefixes list lines; extraction must prefer the
    marked form and still fall back to the legacy layout."""
    captured = ("Godot banner\n"
                "GDX_TEST_OUTPUT: # gdextest list: 2 tests selected\n"
                "GDX_TEST_OUTPUT: suite.one\n"
                "GDX_TEST_OUTPUT: suite.two\n"
                "Godot chatter resumes\n")
    assert cli._extract_list_output(captured) == [
        "# gdextest list: 2 tests selected", "suite.one", "suite.two"]


def test_cmd_test_reads_report_path_copy() -> None:
    """When the user passed --gdextest-json, the renderer reads the extra
    --gdextest-report-path copy the CLI requested, not the user's file."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        document = {"totals": {"pass": 1, "fail": 0, "skip": 0, "crashed": 0},
                    "results": [
                        {"suite": "smoke", "name": "one", "status": "pass",
                         "duration_ms": 0, "retries": 0, "failures": []},
                    ]}
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None,
            json=str(Path(directory) / "user-results.json"), junit=None,
            passthrough=[], keep_fixture=False)
        saved = _stub_cmd_test_deps(cli)
        written_to = {}

        def fake_run(command, **kwargs):
            for arg in command:
                if arg.startswith("--gdextest-report-path="):
                    written_to["report"] = arg.split("=", 1)[1]
                    Path(written_to["report"]).write_text(json.dumps(document),
                                                          encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": "",
                                       "stderr": ""})()

        try:
            cli.subprocess.run = fake_run
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.cmd_test(args)
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        assert code == 0
        assert "[  PASSED  ] 1 test." in out
        assert "report" in written_to
        assert not os.path.exists(written_to["report"]), \
            "the report-path copy must be cleaned up after the run"


def test_cmd_test_marker_forensics_without_document() -> None:
    """Fallback chain, M3 path: engine died during reporting, no JSON document,
    but marker-prefixed lines exist -> the CLI reprints them stripped."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        marked_output = ("Godot banner\n"
                         "GDX_TEST_OUTPUT: == gdextest: 0 passed, 1 failed ==\n"
                         "GDX_TEST_OUTPUT: [FAIL] smoke.one  (3 ms)\n"
                         "GDX_TEST_OUTPUT:     tests/a.cpp:3: expected a == b\n")
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False)
        saved = _stub_cmd_test_deps(cli)
        try:
            cli.subprocess.run = _godot_run_stub(stdout=marked_output,
                                                 returncode=1)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.cmd_test(args)
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        assert code == 1
        assert "[FAIL] smoke.one  (3 ms)" in out
        assert "tests/a.cpp:3: expected a == b" in out
        assert "GDX_TEST_OUTPUT:" not in out, "markers must be stripped"
        assert "Godot banner" not in out


def test_cmd_test_renders_clean_report_and_hides_godot_noise() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        document = {"totals": {"pass": 2, "fail": 0, "skip": 0, "crashed": 0},
                    "results": [
                        {"suite": "smoke", "name": "one", "status": "pass",
                         "duration_ms": 1, "retries": 0, "failures": []},
                        {"suite": "smoke", "name": "two", "status": "pass",
                         "duration_ms": 2, "retries": 0, "failures": []},
                    ]}
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False)
        saved = _stub_cmd_test_deps(cli)
        try:
            cli.subprocess.run = _godot_run_stub(stdout=_ENGINE_NOISE,
                                                 returncode=0,
                                                 document=document)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.cmd_test(args)
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        assert code == 0
        assert "[==========] Running 2 tests from 1 suite." in out
        assert "[  PASSED  ] 2 tests." in out
        assert "Godot Engine v4.5" not in out, "engine noise must be suppressed"
        assert "\x1b[" not in out, "auto color must stay off on a piped stream"


def test_cmd_test_report_color_always() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        document = {"totals": {"pass": 1, "fail": 0, "skip": 0, "crashed": 0},
                    "results": [
                        {"suite": "smoke", "name": "one", "status": "pass",
                         "duration_ms": 0, "retries": 0, "failures": []},
                    ]}
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False, color="always")
        saved = _stub_cmd_test_deps(cli)
        try:
            cli.subprocess.run = _godot_run_stub(document=document)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                assert cli.cmd_test(args) == 0
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        assert "\x1b[32m[       OK ] smoke.one" in out


def test_cmd_test_report_config_defaults_and_overrides() -> None:
    """[gdextest.test] report/color/raw_log flow into cmd_test; the CLI flags
    win where they are more specific (explicit --color, --gdextest-raw-log)."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        (root / ".gdextest.toml").write_text(
            "[gdextest]\nminimum_required_godot_version = \"4.5\"\n"
            "[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\n"
            "[gdextest.test]\n"
            'report = "pretty"\n'
            'color = "never"\n'
            f'raw_log = "{root / "from-config.log"}"\n',
            encoding="utf-8",
        )
        document = {"totals": {"pass": 1, "fail": 0, "skip": 0, "crashed": 0},
                    "results": [
                        {"suite": "smoke", "name": "one", "status": "pass",
                         "duration_ms": 0, "retries": 0, "failures": []},
                    ]}
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False, color="auto", verbose=False,
            raw_log=None)
        saved = _stub_cmd_test_deps(cli)
        captured_args = []
        try:
            cli._godot_command = lambda config, executable, *user_args: (
                captured_args.append(user_args) or ["godot", *user_args])
            cli.subprocess.run = _godot_run_stub(stdout=_ENGINE_NOISE,
                                                 document=document)
            with tempfile.TemporaryDirectory() as flag_log_dir:
                # 1. Config wins for all three keys (flags unset/auto).
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    assert cli.cmd_test(args) == 0
                out = buffer.getvalue()
                forwarded = captured_args[-1]
                assert "--gdextest-report=pretty" in forwarded, (
                    "config report=pretty must be forwarded to the runner")
                assert "\x1b[" not in out, "config color=never must disable ANSI"
                raw_log = root / "from-config.log"
                assert raw_log.is_file(), "config raw_log must be honored"
                assert "Godot Engine v4.5" in raw_log.read_text(encoding="utf-8")
                raw_log.unlink()
                # 2. Explicit CLI flags win over the config.
                flag_log = Path(flag_log_dir) / "from-flag.log"
                args.color = "always"
                args.raw_log = str(flag_log)
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    assert cli.cmd_test(args) == 0
                out = buffer.getvalue()
                assert "\x1b[32m[       OK ] smoke.one" in out, (
                    "explicit --color=always must override config color=never")
                assert flag_log.is_file(), "--gdextest-raw-log must override config"
                assert not (root / "from-config.log").exists(), (
                    "the config raw_log must not be written when the flag names a path")
        finally:
            _restore_cmd_test_deps(cli, saved)


def test_cmd_test_report_config_cli_forces_quiet_engine() -> None:
    """report = "cli" (the default) must still forward --gdextest-report=quiet:
    the CLI renders the report itself, the engine stays quiet."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        document = {"totals": {"pass": 1, "fail": 0, "skip": 0, "crashed": 0},
                    "results": [
                        {"suite": "smoke", "name": "one", "status": "pass",
                         "duration_ms": 0, "retries": 0, "failures": []},
                    ]}
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False, color="auto", verbose=False,
            raw_log=None)
        saved = _stub_cmd_test_deps(cli)
        captured_args = []
        try:
            cli._godot_command = lambda config, executable, *user_args: (
                captured_args.append(user_args) or ["godot", *user_args])
            cli.subprocess.run = _godot_run_stub(stdout=_ENGINE_NOISE,
                                                 document=document)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                assert cli.cmd_test(args) == 0
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        forwarded = captured_args[-1]
        assert "--gdextest-report=quiet" in forwarded
        assert "[==========] Running 1 test from 1 suite." in out
        assert "Godot Engine v4.5" not in out


def test_cmd_test_failed_run_keeps_exit_and_noise_tail() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        document = {"totals": {"pass": 0, "fail": 1, "skip": 0, "crashed": 0},
                    "results": [
                        {"suite": "smoke", "name": "one", "status": "fail",
                         "duration_ms": 0, "retries": 0,
                         "failures": [{"file": "tests/a.cpp", "line": 3,
                                       "message": "expected a == b"}]},
                    ]}
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False)
        saved = _stub_cmd_test_deps(cli)
        try:
            cli.subprocess.run = _godot_run_stub(stdout=_ENGINE_NOISE,
                                                 returncode=1,
                                                 document=document)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.cmd_test(args)
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        assert code == 1
        assert "[  FAILED  ] smoke.one" in out
        assert "gdextest: godot output (tail):" in out
        assert "Godot Engine v4.5" in out  # tail keeps the triage context


def test_cmd_test_crash_without_document_shows_tail() -> None:
    """Fallback chain: no JSON document (engine died) and no runner markers
    (pre-M3) -> render the noise tail, keep the process exit code."""
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        crash_output = ("Godot Engine v4.5.stable.official\n"
                        "ERROR: Condition \"!E\" is true.\n"
                        "handle_crash: Writing stack backtrace\n"
                        "Segmentation fault (core dumped)\n")
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False)
        saved = _stub_cmd_test_deps(cli)
        try:
            cli.subprocess.run = _godot_run_stub(stdout=crash_output,
                                                 returncode=134)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.cmd_test(args)
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        assert code == 134, "the process exit code must never be faked"
        assert "[==========]" not in out, "no fake results for a dead run"
        assert "gdextest: godot output (tail):" in out
        assert "Segmentation fault (core dumped)" in out


def test_cmd_test_verbose_and_raw_log() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        raw_log = Path(directory) / "godot-raw.log"
        document = {"totals": {"pass": 1, "fail": 0, "skip": 0, "crashed": 0},
                    "results": [
                        {"suite": "smoke", "name": "one", "status": "pass",
                         "duration_ms": 0, "retries": 0, "failures": []},
                    ]}
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            filter=None, shard=None, shuffle=None, json=None, junit=None,
            passthrough=[], keep_fixture=False, verbose=True,
            raw_log=str(raw_log))
        saved = _stub_cmd_test_deps(cli)
        try:
            cli.subprocess.run = _godot_run_stub(stdout=_ENGINE_NOISE,
                                                 stderr="engine warning\n",
                                                 returncode=0,
                                                 document=document)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                assert cli.cmd_test(args) == 0
            out = buffer.getvalue()
        finally:
            _restore_cmd_test_deps(cli, saved)
        assert "gdextest: godot output (--verbose):" in out
        assert "Godot Engine v4.5" in out
        assert "engine warning" in out
        logged = raw_log.read_text(encoding="utf-8")
        assert "Godot Engine v4.5" in logged and "engine warning" in logged


def test_cmd_list_prints_extracted_list() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        args = cli.argparse.Namespace(
            project_root=root, framework_dir=None, godot="/usr/bin/godot",
            passthrough=[], keep_fixture=False)
        captured_stdout = (_ENGINE_NOISE + "# gdextest list: 2 tests\n"
                           "suite.one\nsuite.two\n")
        original_build = cli._run_build
        original_executable = cli.godot_executable
        original_warm = cli._warm_fixture
        original_run = cli.subprocess.run
        try:
            cli._run_build = lambda config: None
            cli.godot_executable = lambda config, override: "/usr/bin/godot"
            cli._warm_fixture = lambda config, executable: None
            cli.subprocess.run = _godot_run_stub(stdout=captured_stdout)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = cli.cmd_list(args)
            out = buffer.getvalue()
        finally:
            cli._run_build = original_build
            cli.godot_executable = original_executable
            cli._warm_fixture = original_warm
            cli.subprocess.run = original_run
        assert code == 0
        assert "# gdextest list: 2 tests" in out
        assert "suite.one" in out and "suite.two" in out
        assert "Godot Engine v4.5" not in out


if __name__ == "__main__":
    test_structured_config_and_excludes()
    test_toml_unterminated_string_raises()
    test_toml_multiline_array_parses()
    test_toml_hash_inside_string_is_literal()
    test_extension_sources_resolve_alongside_suites()
    test_zero_match_source_pattern_raises()
    test_doctor_reports_zero_match_pattern()
    test_init_is_idempotent_without_force()
    test_doctor_rejects_empty_source_set()
    test_test_auto_initializes_and_checks_before_build()
    test_runtime_fixture_has_autoload_not_editor_plugin()
    test_build_uses_gdextest_env_contract()
    test_scons_command_includes_build_args()
    test_unwired_build_injects_temporary_sconstruct()
    test_run_build_verifies_library_output()
    test_run_environment_wipes_previous_user_data()
    test_doctor_flags_unwired_sconstruct()
    test_doctor_passes_when_sconstruct_is_wired()
    test_scaffold_apply_wires_and_generates()
    test_scaffold_without_apply_does_not_patch()
    test_sconstruct_wiring_detection_ignores_godot_cpp_path()
    test_cmd_test_passes_through_gdextest_args()
    test_timeout_budgets_forwarded_from_toml()
    test_json_to_junit_conversion()
    test_is_msvc_compiler_detection()
    test_sconscript_selects_flags_by_compiler_family()
    test_report_merges_shard_documents()
    test_godot_discovery_finds_nearby_binary()
    test_doctor_godot_cpp_version_checks()
    test_version_at_least_accepts_higher_binaries()
    test_doctor_enforces_minimum_godot_without_capping_high()
    test_scan_timeout_config_parses()
    test_warm_fixture_runs_only_when_cold()
    test_extension_manifest_derived_from_library()
    test_extension_library_derived_from_manifest()
    test_extension_pair_still_validates_when_derivation_ambiguous()
    test_fixture_removed_after_test_run()
    test_fixture_removed_after_list()
    test_keep_fixture_retains_on_failure_removes_on_success()
    test_remove_fixture_refuses_project_root()
    test_split_captured_output_classifies_markers()
    test_extract_list_output_parses_legacy_block()
    test_extract_list_output_parses_marker_block()
    test_cmd_test_reads_report_path_copy()
    test_cmd_test_marker_forensics_without_document()
    test_cmd_test_renders_clean_report_and_hides_godot_noise()
    test_cmd_test_report_color_always()
    test_report_output_config_keys_parse()
    test_report_output_config_keys_validate()
    test_cmd_test_report_config_defaults_and_overrides()
    test_cmd_test_report_config_cli_forces_quiet_engine()
    test_cmd_test_failed_run_keeps_exit_and_noise_tail()
    test_cmd_test_crash_without_document_shows_tail()
    test_cmd_test_verbose_and_raw_log()
    test_cmd_list_prints_extracted_list()
    print("configuration tests: ok")
