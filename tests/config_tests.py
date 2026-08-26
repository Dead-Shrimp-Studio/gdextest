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


if __name__ == "__main__":
    test_structured_config_and_excludes()
    test_init_is_idempotent_without_force()
    test_doctor_rejects_empty_source_set()
    test_test_auto_initializes_and_checks_before_build()
    test_runtime_fixture_has_autoload_not_editor_plugin()
    print("configuration tests: ok")
