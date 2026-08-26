#!/usr/bin/env python3
"""Tests for the external-consumer configuration contract."""

from pathlib import Path
import importlib.util
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
            cli._run_doctor = lambda config, godot: events.append("doctor") or 0
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

    with tempfile.TemporaryDirectory() as directory:
        root = _consumer_root(directory)
        (root / "bin").mkdir()
        (root / "bin" / "libgdextest.linux.template_debug.x86_64.so").write_bytes(b"")
        config = config_module.load_config(root)
        captured = {}
        original_run = cli.subprocess.run
        try:
            def fake_run(command, **kwargs):
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
            cli._run_doctor = lambda config, godot: 0
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
            cli._run_doctor = lambda config, godot: 0
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
        assert captured == [("--gdextest-some-new-flag=1",)]


if __name__ == "__main__":
    test_structured_config_and_excludes()
    test_init_is_idempotent_without_force()
    test_doctor_rejects_empty_source_set()
    test_test_auto_initializes_and_checks_before_build()
    test_runtime_fixture_has_autoload_not_editor_plugin()
    test_build_uses_gdextest_env_contract()
    test_scons_command_includes_build_args()
    test_run_build_verifies_library_output()
    test_run_environment_wipes_previous_user_data()
    test_doctor_flags_unwired_sconstruct()
    test_doctor_passes_when_sconstruct_is_wired()
    test_scaffold_apply_wires_and_generates()
    test_scaffold_without_apply_does_not_patch()
    test_cmd_test_passes_through_gdextest_args()
    print("configuration tests: ok")
