#!/usr/bin/env python3
"""Configuration and environment discovery for gdextest consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import shutil
import subprocess
from typing import Iterable


SUPPORTED_HOST_MODES = {"editor", "runtime"}
SOURCE_SUFFIXES = {".cpp", ".cc", ".cxx"}


@dataclass
class Config:
    project_root: Path
    framework_dir: Path
    version: str = "1"
    godot: str | None = None
    godot_version: str = "4.5"
    fixture_dir: str = "build/gdextest/project"
    build_dir: str = "build/gdextest"
    out_dir: str = "bin"
    out_name: str = "libgdextest"
    test_sources: list[str] = field(default_factory=lambda: ["tests/**/*.cpp"])
    test_exclude: list[str] = field(default_factory=list)
    entry_symbol: str = "gdextest_library_init"
    project_name: str = "gdextest fixture"
    manifest_name: str = "gdextest.gdextension"
    library_key: str | None = None
    host_mode: str = "editor"
    bootstrap: str | None = None
    native_extensions: list[str] = field(default_factory=list)
    extension_library: str | None = None
    extension_manifest: str | None = None
    fixture_assets: list[str] = field(default_factory=list)
    ci_provider: str = "github"

    @property
    def fixture_path(self) -> Path:
        return self.project_root / self.fixture_dir

    @property
    def output_path(self) -> Path:
        return self.project_root / self.out_dir

    def validate(self, *, require_framework: bool = True) -> list[str]:
        errors: list[str] = []
        if not self.project_root.is_dir():
            errors.append(f"project root does not exist: {self.project_root}")
        if require_framework and not (self.framework_dir / "SConscript").is_file():
            errors.append(f"framework SConscript not found: {self.framework_dir / 'SConscript'}")
        if not self.godot_version or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", self.godot_version):
            errors.append(f"invalid godot_version: {self.godot_version!r}")
        if self.host_mode not in SUPPORTED_HOST_MODES:
            errors.append(f"host_mode must be one of {sorted(SUPPORTED_HOST_MODES)}")
        if not self.test_sources:
            errors.append("test_sources must contain at least one glob")
        if not self.entry_symbol or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.entry_symbol):
            errors.append(f"invalid entry_symbol: {self.entry_symbol!r}")
        if self.extension_library and not self.extension_manifest:
            errors.append("extension_manifest is required when extension_library is set")
        if self.extension_manifest and not self.extension_library:
            errors.append("extension_library is required when extension_manifest is set")
        return errors


def find_project_root(start: str | Path = ".") -> Path:
    path = Path(start).resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / ".gdextest.toml").is_file() or (candidate / "SConstruct").is_file():
            return candidate
    return path


def _parse_value(value: str):
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return bytes(value[1:-1], "utf-8").decode("unicode_escape")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_parse_value(item) for item in re.split(r",\s*", inner)]
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def load_toml(path: Path) -> dict:
    """Load the small TOML subset used by gdextest without third-party packages."""
    result: dict = {}
    section = result
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = result
            for component in line[1:-1].split("."):
                section = section.setdefault(component, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        section[key.strip()] = _parse_value(value)
    return result


def _first(values: dict, *keys: str, default=None):
    for key in keys:
        if key in values:
            return values[key]
    return default


def load_config(project_root: str | Path = ".", framework_dir: str | Path | None = None) -> Config:
    root = find_project_root(project_root)
    framework = Path(framework_dir).resolve() if framework_dir else root / "extern" / "gdextest"
    if not framework.is_dir() and (root / "SConscript").is_file():
        framework = root
    raw = load_toml(root / ".gdextest.toml")
    values = raw.get("gdextest", raw)
    tests = values.get("tests", {})
    host = values.get("host", {})
    fixture = values.get("fixture", {})
    output = values.get("output", {})
    consumer = values.get("consumer_extension", {})

    # Flat keys remain supported so existing consumers do not need a migration commit.
    config = Config(
        project_root=root,
        framework_dir=framework,
        version=str(_first(values, "version", default="1")),
        godot=_first(values, "godot"),
        godot_version=str(_first(values, "godot_version", default="4.5")),
        fixture_dir=str(_first(fixture, "directory", default=_first(values, "fixture_dir", default="build/gdextest/project"))),
        build_dir=str(_first(values, "build_dir", default="build/gdextest")),
        out_dir=str(_first(output, "directory", default=_first(values, "out_dir", default="bin"))),
        out_name=str(_first(output, "name", default=_first(values, "out_name", default="libgdextest"))),
        test_sources=list(_first(tests, "sources", default=_first(values, "test_sources", default=["tests/**/*.cpp"]))),
        test_exclude=list(_first(tests, "exclude", default=[])),
        entry_symbol=str(_first(host, "entry_symbol", default=_first(values, "entry_symbol", default="gdextest_library_init"))),
        project_name=str(_first(fixture, "project_name", default=_first(values, "project_name", default="gdextest fixture"))),
        manifest_name=str(_first(fixture, "manifest_name", default=_first(values, "manifest_name", default="gdextest.gdextension"))),
        library_key=_first(fixture, "library_key", default=_first(values, "library_key")),
        host_mode=str(_first(host, "mode", default="editor")),
        bootstrap=_first(host, "bootstrap", default=_first(values, "bootstrap")),
        native_extensions=list(_first(fixture, "native_extensions", default=_first(values, "native_extensions", default=[]))),
        extension_library=_first(consumer, "library", default=_first(values, "extension_library")),
        extension_manifest=_first(consumer, "manifest", default=_first(values, "extension_manifest")),
        fixture_assets=list(_first(fixture, "assets", default=_first(values, "fixture_assets", default=[]))),
        ci_provider=str(_first(values, "ci_provider", default="github")),
    )
    return config


def discover_sources(config: Config) -> list[Path]:
    found: list[Path] = []
    excluded = [config.project_root / pattern for pattern in config.test_exclude]
    for pattern in config.test_sources:
        for path in config.project_root.glob(pattern):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if path in found or any(path == candidate or candidate in path.parents for candidate in excluded):
                continue
            found.append(path)
    return sorted(found)


def godot_executable(config: Config, override: str | None = None) -> str:
    candidate = override or config.godot or os.environ.get("GODOT") or "godot"
    resolved = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
    if not resolved:
        raise FileNotFoundError(
            f"Godot executable not found: {candidate}. Set GODOT or pass --godot=/path/to/godot.")
    return resolved


def godot_version(executable: str) -> str:
    output = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    text = (output.stdout + output.stderr).strip()
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else text


def copy_globbed_assets(project_root: Path, fixture_root: Path, patterns: Iterable[str]) -> None:
    for pattern in patterns:
        for source in project_root.glob(pattern):
            if not source.is_file():
                continue
            relative = source.relative_to(project_root)
            destination = fixture_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def locate_extension_library(config: Config) -> Path | None:
    if not config.extension_library:
        return None
    path = Path(config.extension_library)
    return path if path.is_absolute() else config.project_root / path


def locate_extension_manifest(config: Config) -> Path | None:
    if not config.extension_manifest:
        return None
    path = Path(config.extension_manifest)
    return path if path.is_absolute() else config.project_root / path
