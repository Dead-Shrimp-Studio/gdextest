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
    test_runtime_fixture_has_autoload_not_editor_plugin()
    print("configuration tests: ok")
