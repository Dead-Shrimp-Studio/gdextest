#!/usr/bin/env python3
"""Tests for the external-consumer configuration contract."""

from pathlib import Path
import importlib.util
import json
import os
import sys
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
            """[gdextest]\ngodot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\nexclude = [\"tests/generated\"]\n[gdextest.host]\nmode = \"runtime\"\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert config.host_mode == "runtime"
        assert [path.name for path in config_module.discover_sources(config)] == ["one.cpp"]
        assert config.validate() == []


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
            """[gdextest]\ngodot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\n""",
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
            """[gdextest]\ngodot_version = \"4.5\"\n[gdextest.build]\nargs = [\"platform=linux\", \"target=editor\"]\n""",
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
            """[gdextest]\ngodot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\n[gdextest.host]\nentry_symbol = \"my_library_init\"\nplugin_class = \"MyTestPlugin\"\n""",
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
        assert captured == [("--gdextest-some-new-flag=1",
                             "--gdextest-timeout-ms=30000",
                             "--gdextest-isolate-timeout-sec=60",
                             "--gdextest-flaky-retries=3")]


def test_timeout_budgets_forwarded_from_toml() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        (root / ".gdextest.toml").write_text(
            """[gdextest]\ngodot_version = \"4.5\"\n[gdextest.tests]\nsources = [\"tests/**/*.cpp\"]\n[gdextest.test]\ntimeout_ms = 5000\nisolate_timeout_sec = 120\nflaky_retries = 5\n""",
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
        assert 'classname="a"' in xml_text
        assert 'name="fails"' in xml_text
        assert "expected a == b" in xml_text
        assert 'message="no service"' in xml_text


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
            """[gdextest]\ngodot_version = \"4.5\"\n[gdextest.fixture]\nscan_timeout_ms = 90000\n""",
            encoding="utf-8",
        )
        config = config_module.load_config(root)
        assert config.scan_timeout_ms == 90000


if __name__ == "__main__":
    test_structured_config_and_excludes()
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
    test_report_merges_shard_documents()
    test_godot_discovery_finds_nearby_binary()
    test_doctor_godot_cpp_version_checks()
    test_scan_timeout_config_parses()
    test_warm_fixture_runs_only_when_cold()
    print("configuration tests: ok")
