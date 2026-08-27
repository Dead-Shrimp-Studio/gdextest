#!/usr/bin/env python3
"""Small dependency-free tests for the generated fixture contract."""

from pathlib import Path
import importlib.util
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gdextest_fixture_generator", ROOT / "tools" / "generate_fixture.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["gdextest_fixture_generator"] = MODULE
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
        manifest = (root / "project" / "addons" / "gdextest" /
                    "custom-test.gdextension").read_text()
        staged = (root / "project" / "addons" / "gdextest" / "bin" /
                  "libtest.so")
        assert 'res://addons/gdextest/custom-test.gdextension' in project
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
            manifest_basename="gdextest.gdextension",
        )
        plugin = (root / "project" / "addons" / "gdextest" / "plugin.gd").read_text()
        assert "EditorInterface.get_resource_filesystem()" in plugin
        assert "is_scanning()" in plugin
        assert "GdextestPlugin.new()" in plugin
        assert "did not finish before timeout" in plugin


def test_generated_plugin_uses_configured_plugin_class() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        MODULE.generate_fixture(
            project_root=root / "project",
            library_path=source,
            library_basename="libtest.so",
            manifest_basename="gdextest.gdextension",
            plugin_class="MyTestPlugin",
        )
        plugin = (root / "project" / "addons" / "gdextest" / "plugin.gd").read_text()
        assert "MyTestPlugin.new()" in plugin
        assert "GdextestPlugin.new()" not in plugin


def test_generated_runtime_host_uses_configured_plugin_class() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        MODULE.generate_fixture(
            project_root=root / "project",
            library_path=source,
            library_basename="libtest.so",
            manifest_basename="gdextest.gdextension",
            host_mode="runtime",
            plugin_class="MyTestPlugin",
        )
        runtime = (root / "project" / "addons" / "gdextest" / "runtime.gd").read_text()
        assert "MyTestPlugin.new()" in runtime
        assert "GdextestPlugin.new()" not in runtime


def test_invalid_plugin_class_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        try:
            MODULE.generate_fixture(
                project_root=root / "project",
                library_path=source,
                library_basename="libtest.so",
                manifest_basename="gdextest.gdextension",
                plugin_class="not a class",
            )
            assert False, "expected ValueError for an invalid plugin class name"
        except ValueError as error:
            assert "plugin_class" in str(error)


def test_generated_plugin_uses_configured_scan_timeout() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        MODULE.generate_fixture(
            project_root=root / "project",
            library_path=source,
            library_basename="libtest.so",
            manifest_basename="gdextest.gdextension",
            scan_timeout_ms=90000,
        )
        plugin = (root / "project" / "addons" / "gdextest" / "plugin.gd").read_text()
        assert "const SCAN_TIMEOUT_MS := 90000" in plugin


def test_stale_manifests_and_binaries_removed() -> None:
    """A regenerated fixture must not leave manifests/libraries from an earlier
    config behind — Godot's editor tries to load every .gdextension it finds.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        project = root / "project"
        MODULE.generate_fixture(project_root=project, library_path=source,
                                library_basename="libtest.so",
                                manifest_basename="gdextest.gdextension")
        stale_manifest = project / "addons" / "gdextest" / "libstale.gdextension"
        stale_manifest.write_text("stale", encoding="utf-8")
        stale_binary = project / "addons" / "gdextest" / "bin" / "libstale.so"
        stale_binary.write_bytes(b"stale")
        MODULE.generate_fixture(project_root=project, library_path=source,
                                library_basename="libtest.so",
                                manifest_basename="gdextest.gdextension")
        assert not stale_manifest.exists(), "stale .gdextension must be removed"
        assert not stale_binary.exists(), "stale library must be removed"
        assert (project / "addons" / "gdextest" /
                "gdextest.gdextension").is_file()
        assert (project / "addons" / "gdextest" / "bin" /
                "libtest.so").read_bytes() == b"test-library"


def test_invalid_scan_timeout_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "libtest.so"
        source.write_bytes(b"test-library")
        try:
            MODULE.generate_fixture(
                project_root=root / "project",
                library_path=source,
                library_basename="libtest.so",
                manifest_basename="gdextest.gdextension",
                scan_timeout_ms=0,
            )
            assert False, "expected ValueError for a non-positive scan timeout"
        except ValueError as error:
            assert "scan_timeout_ms" in str(error)


if __name__ == "__main__":
    test_generated_manifest_is_referenced()
    test_generated_plugin_uses_scan_safe_host()
    test_generated_plugin_uses_configured_plugin_class()
    test_generated_runtime_host_uses_configured_plugin_class()
    test_invalid_plugin_class_rejected()
    test_generated_plugin_uses_configured_scan_timeout()
    test_invalid_scan_timeout_rejected()
    test_stale_manifests_and_binaries_removed()
    print("fixture generator tests: ok")
