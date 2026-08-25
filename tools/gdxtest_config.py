#!/usr/bin/env python3
"""Shared configuration for the gdxtest CLI and SCons integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import fnmatch
import os
import re
import shutil
import subprocess
from typing import Iterable


@dataclass
class Config:
    project_root: Path
    framework_dir: Path
    godot: str | None = None
    godot_version: str = "4.5"
    fixture_dir: str = "build/gdxtest/project"
    build_dir: str = "build/gdxtest"
    out_dir: str = "bin"
    out_name: str = "libgdxtest"
    test_sources: list[str] = field(default_factory=lambda: ["tests/**/*.cpp"])
    entry_symbol: str = "gdx_test_library_init"
    project_name: str = "gdxtest fixture"
    library_key: str | None = None
    native_extensions: list[str] = field(default_factory=list)
    extension_library: str | None = None
    extension_manifest: str | None = None
    fixture_assets: list[str] = field(default_factory=list)
    bootstrap: str | None = None
    ci_provider: str = "github"

    @property
    def fixture_path(self) -> Path:
        return self.project_root / self.fixture_dir


def find_project_root(start: str | Path = ".") -> Path:
    path = Path(start).resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / ".gdxtest.toml").is_file() or (candidate / "SConstruct").is_file():
            return candidate
    return path


def _parse_value(value: str):
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return bytes(value[1:-1], "utf-8").decode("unicode_escape")
    if value.startswith("[") and value.endswith("]"):
        values = []
        for item in re.split(r",\s*", value[1:-1].strip()):
            if item:
                values.append(_parse_value(item))
        return values
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def load_toml(path: Path) -> dict:
    """Load the small TOML subset used by gdxtest without third-party packages."""
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


def load_config(project_root: str | Path = ".", framework_dir: str | Path | None = None) -> Config:
    root = find_project_root(project_root)
    framework = Path(framework_dir).resolve() if framework_dir else root / "extern" / "gdxtest"
    raw = load_toml(root / ".gdxtest.toml")
    values = raw.get("gdxtest", raw)
    config = Config(project_root=root, framework_dir=framework)
    for key in config.__dataclass_fields__:
        if key in ("project_root", "framework_dir"):
            continue
        if key in values:
            setattr(config, key, values[key])
    return config


def discover_sources(config: Config) -> list[Path]:
    found: list[Path] = []
    for pattern in config.test_sources:
        for path in config.project_root.glob(pattern):
            if path.is_file() and path.suffix in (".cpp", ".cc", ".cxx") and path not in found:
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
