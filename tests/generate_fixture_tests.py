#!/usr/bin/env python3
"""Small dependency-free tests for the generated fixture contract."""

from pathlib import Path
import importlib.util
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gdxtest_fixture_generator", ROOT / "tools" / "generate_fixture.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_generated_manifest_is_referenced() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        MODULE.generate_fixture(
            project_root=root / "project",
            library_path=source,
            library_basename="libtest.so",
            manifest_basename="custom-test.gdextension",
            entry_symbol="custom_init",
        )
        project = (root / "project" / "project.godot").read_text()
        manifest = (root / "project" / "addons" / "gdxtest" /
                    "custom-test.gdextension").read_text()
        staged = (root / "project" / "addons" / "gdxtest" / "bin" /
                  "libtest.so")
        assert 'res://addons/gdxtest/custom-test.gdextension' in project
        assert 'entry_symbol = "custom_init"' in manifest
        assert staged.read_bytes() == b"test-library"


def test_generated_plugin_uses_scan_safe_host() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        MODULE.generate_fixture(
            project_root=root / "project",
            library_path=source,
            library_basename="libtest.so",
            manifest_basename="gdxtest.gdextension",
        )
        plugin = (root / "project" / "addons" / "gdxtest" / "plugin.gd").read_text()
        assert "EditorInterface.get_resource_filesystem()" in plugin
        assert "is_scanning()" in plugin
        assert "GdxTestPlugin.new()" in plugin


if __name__ == "__main__":
    test_generated_manifest_is_referenced()
    test_generated_plugin_uses_scan_safe_host()
    print("fixture generator tests: ok")
