#!/usr/bin/env python3
"""Configuration and environment discovery for gdextest consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import configparser
import os
import re
import shutil
import subprocess
from typing import Iterable


SUPPORTED_HOST_MODES = {"editor", "runtime"}
# .c included so vendored C dependencies (e.g. md4c) compile into the test
# library alongside the extension sources that call them.
SOURCE_SUFFIXES = {".c", ".cpp", ".cc", ".cxx"}


@dataclass
class Config:
    project_root: Path
    framework_dir: Path
    version: str = "1"
    godot: str | None = None
    # Lowest Godot major.minor[.patch] the tests can run against. Binaries with a
    # higher version are valid; a lower one fails the doctor and test checks.
    minimum_required_godot_version: str = "4.5"
    fixture_dir: str = "build/gdextest/project"
    build_dir: str = "build/gdextest"
    out_dir: str = "bin"
    out_name: str = "libgdextest"
    test_sources: list[str] = field(default_factory=lambda: ["tests/**/*.cpp"])
    test_exclude: list[str] = field(default_factory=list)
    entry_symbol: str = "gdextest_library_init"
    plugin_class: str = "GdextestPlugin"
    project_name: str = "gdextest fixture"
    # None -> the SConscript derives it from the output name (out_name + ".gdextension").
    manifest_name: str | None = None
    library_key: str | None = None
    host_mode: str = "editor"
    bootstrap: str | None = None
    native_extensions: list[str] = field(default_factory=list)
    extension_library: str | None = None
    extension_manifest: str | None = None
    fixture_assets: list[str] = field(default_factory=list)
    scan_timeout_ms: int = 20000
    build_args: list[str] = field(default_factory=list)
    timeout_ms: int = 30000
    isolate_timeout_sec: int = 60
    flaky_retries: int = 3
    # Console reporting (see .plans/gtest-style-console-output.md). "cli" keeps
    # the engine's own behavior (direct-Godot runs render the quiet marker
    # layout); the CLI always overrides to "quiet" and renders the report
    # itself after the engine exits.
    report: str = "cli"
    color: str = "auto"
    raw_log: str = ""
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
        if not self.minimum_required_godot_version or not re.fullmatch(
                r"\d+\.\d+(?:\.\d+)?", self.minimum_required_godot_version):
            errors.append(
                f"invalid minimum_required_godot_version: {self.minimum_required_godot_version!r}")
        if self.host_mode not in SUPPORTED_HOST_MODES:
            errors.append(f"host_mode must be one of {sorted(SUPPORTED_HOST_MODES)}")
        if not self.test_sources:
            errors.append("test_sources must contain at least one glob")
        if not self.entry_symbol or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.entry_symbol):
            errors.append(f"invalid entry_symbol: {self.entry_symbol!r}")
        if not self.plugin_class or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.plugin_class):
            errors.append(f"invalid plugin_class: {self.plugin_class!r}")
        for argument in self.build_args:
            if "=" not in argument or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:=[^\s]+)?", argument):
                errors.append(f"invalid build arg: {argument!r} (expected key=value)")
        if self.timeout_ms <= 0:
            errors.append(f"timeout_ms must be positive, got {self.timeout_ms}")
        if self.isolate_timeout_sec <= 0:
            errors.append(f"isolate_timeout_sec must be positive, got {self.isolate_timeout_sec}")
        if self.flaky_retries < 0:
            errors.append(f"flaky_retries must be >= 0, got {self.flaky_retries}")
        if self.report not in ("cli", "quiet", "pretty"):
            errors.append(
                f'report must be one of ["cli", "pretty", "quiet"], got {self.report!r}')
        if self.color not in ("auto", "always", "never"):
            errors.append(
                f'color must be one of ["auto", "always", "never"], got {self.color!r}')
        if self.scan_timeout_ms <= 0:
            errors.append(f"scan_timeout_ms must be positive, got {self.scan_timeout_ms}")
        if self.extension_library and not self.extension_manifest:
            errors.append(
                "extension_manifest is required when extension_library is set "
                "(no .gdextension manifest could be derived next to the library; "
                "set [gdextest.consumer_extension] manifest explicitly)")
        if self.extension_manifest and not self.extension_library:
            errors.append(
                "extension_library is required when extension_manifest is set "
                "(no library declared in the manifest could be resolved on disk; "
                "set [gdextest.consumer_extension] library explicitly)")
        return errors


def find_project_root(start: str | Path = ".") -> Path:
    path = Path(start).resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / ".gdextest.toml").is_file() or (candidate / "SConstruct").is_file():
            return candidate
    return path


def _strip_comment(line: str) -> str:
    """Drop a trailing comment; '#' inside quoted strings is literal."""
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "#":
            return line[:index]
    return line


def _unbalanced_brackets(text: str) -> int:
    """Net count of unclosed '[' outside quoted strings."""
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
    return depth


def _unterminated_string(text: str) -> bool:
    """True when `text` ends inside a quoted string."""
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
    return in_string


def _array_incomplete(value: str) -> bool:
    """True when an array value needs continuation lines (or is malformed)."""
    return _unterminated_string(value) or _unbalanced_brackets(value) > 0


def _parse_value(value: str):
    value = value.strip()
    if value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            raise ValueError(f"unterminated string {value!r} (missing closing quote?)")
        return bytes(value[1:-1], "utf-8").decode("unicode_escape")
    if value.startswith("["):
        if not value.endswith("]"):
            raise ValueError(f"unterminated array {value!r} (missing closing ']')")
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(item) for item in re.split(r",\s*", inner) if item.strip()]
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def load_toml(path: Path) -> dict:
    """Load the small TOML subset used by gdextest without third-party packages.

    Supports quoted strings, booleans, single-line and multiline arrays, and
    dotted section headers. Malformed values raise with file:line context
    instead of being silently mangled — an unterminated string used to parse
    as a literal pattern (quote included) that then matched no files.
    """
    result: dict = {}
    section = result
    if not path.is_file():
        return result
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line_number = index + 1
        line = _strip_comment(lines[index]).strip()
        index += 1
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
        value = value.strip()
        # Multiline arrays: join continuation lines until brackets balance.
        while value.startswith("[") and _array_incomplete(value):
            if index >= len(lines):
                if _unterminated_string(value):
                    raise ValueError(
                        f"{path}:{line_number}: unterminated string in "
                        f"'{key.strip()}' (missing closing quote?)")
                raise ValueError(
                    f"{path}:{line_number}: unterminated array for key "
                    f"'{key.strip()}' (missing closing ']')")
            value += " " + _strip_comment(lines[index]).strip()
            index += 1
        try:
            section[key.strip()] = _parse_value(value)
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error
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
    build = values.get("build", {})
    test = values.get("test", {})
    consumer = values.get("consumer_extension", {})
    extension_library = _first(consumer, "library", default=_first(values, "extension_library"))
    extension_manifest = _first(consumer, "manifest", default=_first(values, "extension_manifest"))

    # A consumer extension is one addon described by two files: the
    # .gdextension manifest and the shared library it points at. Only one of
    # the two needs to be configured; the other is derived from the file
    # layout, so `gdextest` works without hunting for both paths.
    if extension_library and not extension_manifest:
        library_path = _resolve_path(root, extension_library)
        derived = discover_extension_manifest(library_path) if library_path else None
        if derived:
            extension_manifest = _config_value(derived, root)
    elif extension_manifest and not extension_library:
        manifest_path = _resolve_path(root, extension_manifest)
        derived = discover_extension_library(manifest_path) if manifest_path else None
        if derived:
            extension_library = _config_value(derived, root)

    # Flat keys remain supported so existing consumers do not need a migration commit.
    config = Config(
        project_root=root,
        framework_dir=framework,
        version=str(_first(values, "version", default="1")),
        godot=_first(values, "godot"),
        minimum_required_godot_version=str(
            _first(values, "minimum_required_godot_version", default="4.5")),
        fixture_dir=str(_first(fixture, "directory", default=_first(values, "fixture_dir", default="build/gdextest/project"))),
        build_dir=str(_first(values, "build_dir", default="build/gdextest")),
        out_dir=str(_first(output, "directory", default=_first(values, "out_dir", default="bin"))),
        out_name=str(_first(output, "name", default=_first(values, "out_name", default="libgdextest"))),
        test_sources=list(_first(tests, "sources", default=_first(values, "test_sources", default=["tests/**/*.cpp"]))),
        test_exclude=list(_first(tests, "exclude", default=[])),
        entry_symbol=str(_first(host, "entry_symbol", default=_first(values, "entry_symbol", default="gdextest_library_init"))),
        plugin_class=str(_first(host, "plugin_class", default=_first(values, "plugin_class", default="GdextestPlugin"))),
        project_name=str(_first(fixture, "project_name", default=_first(values, "project_name", default="gdextest fixture"))),
        manifest_name=_first(fixture, "manifest_name", default=_first(values, "manifest_name")),
        library_key=_first(fixture, "library_key", default=_first(values, "library_key")),
        host_mode=str(_first(host, "mode", default="editor")),
        bootstrap=_first(host, "bootstrap", default=_first(values, "bootstrap")),
        native_extensions=list(_first(fixture, "native_extensions", default=_first(values, "native_extensions", default=[]))),
        extension_library=extension_library,
        extension_manifest=extension_manifest,
        fixture_assets=list(_first(fixture, "assets", default=_first(values, "fixture_assets", default=[]))),
        scan_timeout_ms=int(_first(fixture, "scan_timeout_ms", default=_first(values, "scan_timeout_ms", default=20000))),
        build_args=list(_first(build, "args", default=[])),
        timeout_ms=int(_first(test, "timeout_ms", default=_first(values, "timeout_ms", default=30000))),
        isolate_timeout_sec=int(_first(test, "isolate_timeout_sec", default=_first(values, "isolate_timeout_sec", default=60))),
        flaky_retries=int(_first(test, "flaky_retries", default=_first(values, "flaky_retries", default=3))),
        report=str(_first(test, "report", default=_first(values, "report", default="cli"))),
        color=str(_first(test, "color", default=_first(values, "color", default="auto"))),
        raw_log=str(_first(test, "raw_log", default=_first(values, "raw_log", default=""))),
        ci_provider=str(_first(values, "ci_provider", default="github")),
    )
    return config


def source_pattern_matches(config: Config) -> dict[str, list[Path]]:
    """Map each [gdextest.tests] source pattern to the C++ files it matched.

    Patterns are repo-root-relative globs. A pattern matching zero files is
    reported as an empty list so callers can fail loudly instead of silently
    compiling a test library that is missing the code under test (which only
    surfaces later as undefined symbols when Godot loads the .so).
    """
    matches: dict[str, list[Path]] = {}
    excluded = [config.project_root / pattern for pattern in config.test_exclude]
    for pattern in config.test_sources:
        found: list[Path] = []
        try:
            candidates = list(config.project_root.glob(pattern))
        except ValueError:
            # Malformed glob (e.g. an empty pattern): report zero matches so
            # the diagnostics name the offending pattern.
            candidates = []
        for path in candidates:
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if any(path == candidate or candidate in path.parents for candidate in excluded):
                continue
            if path not in found:
                found.append(path)
        matches[pattern] = found
    return matches


def _zero_match_error(patterns: list[str], config: Config) -> str:
    return (
        "[gdextest.tests] sources pattern matched no C++ files: "
        + ", ".join(repr(pattern) for pattern in patterns)
        + f" (patterns are repo-root-relative; searched from {config.project_root})")


def resolve_sources(config: Config) -> list[Path]:
    """Discover sources, raising when a configured pattern matches nothing.

    A zero-match pattern is almost always a typo, an unterminated string in
    the TOML, or a pattern anchored at the wrong root — failing here beats a
    half-built test library that only fails at load time.
    """
    matches = source_pattern_matches(config)
    empty = [pattern for pattern, paths in matches.items() if not paths]
    if empty:
        raise RuntimeError(_zero_match_error(empty, config))
    found: set[Path] = set()
    for paths in matches.values():
        found.update(paths)
    return sorted(found)


def discover_sources(config: Config) -> list[Path]:
    """Lenient discovery (zero-match patterns ignored) for existing callers."""
    found: set[Path] = set()
    for paths in source_pattern_matches(config).values():
        found.update(paths)
    return sorted(found)


def _discover_godot(config: Config) -> str | None:
    """Find a `Godot_v*` executable near the project or in common home dirs.

    Searches the project root and its ancestors (e.g. a sibling `godot/`
    checkout beside the repo) plus $HOME and a few conventional locations.
    Binaries matching the configured major.minor (e.g. 4.5) are preferred;
    among the rest, the newest name wins. Returns None when nothing is found.
    """
    expected = ".".join(config.minimum_required_godot_version.split(".")[:2])
    candidates: list[Path] = []
    directories: list[Path] = []
    current = config.project_root
    while True:
        directories.append(current)
        if current == current.parent:
            break
        current = current.parent
    home = Path.home()
    directories += [home, home / "godot", home / "Godot", home / "Downloads",
                    home / "Documents" / "godot", home / "Documents" / "Godot"]
    seen: set[Path] = set()
    for directory in directories:
        if directory in seen or not directory.is_dir():
            continue
        seen.add(directory)
        for path in directory.glob("Godot_v*"):
            if path.is_file() and os.access(path, os.X_OK):
                candidates.append(path)
    if not candidates:
        return None
    matching = [path for path in candidates if expected in path.name] if expected else []
    pool = matching or candidates
    return str(max(pool, key=lambda path: path.name))


def godot_executable(config: Config, override: str | None = None) -> str:
    candidate = override or config.godot or os.environ.get("GODOT") or "godot"
    resolved = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
    if not resolved:
        resolved = _discover_godot(config)
    if not resolved:
        raise FileNotFoundError(
            f"Godot executable not found: {candidate}. Set GODOT, pass --godot=/path/to/godot, "
            "or place a Godot_v* binary in the project, an ancestor, or $HOME.")
    return resolved


def godot_cpp_version(project_root: str | Path) -> str | None:
    """Best-effort major.minor of the consumer's godot-cpp binding (or None).

    Reads the submodule's checked-out branch, falling back to `git describe`
    tags for detached checkouts. None when godot-cpp is absent or not a repo.
    """
    cpp = Path(project_root) / "extern" / "godot-cpp"
    if not (cpp / "SConstruct").is_file():
        return None
    try:
        branch = subprocess.run(
            ["git", "-C", str(cpp), "branch", "--show-current"],
            capture_output=True, text=True, check=False).stdout.strip()
        if re.fullmatch(r"\d+\.\d+", branch):
            return branch
        describe = subprocess.run(
            ["git", "-C", str(cpp), "describe", "--tags"],
            capture_output=True, text=True, check=False).stdout.strip()
        match = re.search(r"(\d+\.\d+)", describe)
        if match:
            return match.group(1)
    except OSError:
        pass
    return None


def godot_version(executable: str) -> str:
    output = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    text = (output.stdout + output.stderr).strip()
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else text


def version_at_least(actual: str, minimum: str) -> bool:
    """Return True when `actual` is at or above the required `minimum` version."""

    def _parts(value: str) -> tuple[int, ...]:
        return tuple(int(part) for part in re.findall(r"\d+", value)[:3])

    return bool(actual) and _parts(actual) >= _parts(minimum)


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


def _resolve_path(root: Path, value: str) -> Path | None:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _config_value(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def discover_extension_manifest(library: Path) -> Path | None:
    """Derive the .gdextension manifest that declares `library`.

    godot-cpp addons keep the manifest next to the shared library
    (addons/<name>/bin/<lib>.so + addons/<name>/bin/<name>.gdextension) or one
    level up in the addon root (addons/<name>/<name>.gdextension). Walk a few
    levels up from the library and return the manifest only when the search is
    unambiguous (zero or several matches -> None).
    """
    candidates: set[Path] = set()
    directory = library.parent
    for _ in range(3):
        if directory.is_dir():
            candidates.update(directory.glob("*.gdextension"))
        directory = directory.parent
    return next(iter(candidates)) if len(candidates) == 1 else None


def discover_extension_library(manifest: Path) -> Path | None:
    """Derive the shared library a .gdextension manifest declares.

    Reads the manifest's [libraries] table (e.g. `linux.debug.x86_64 =
    "res://addons/<name>/bin/lib...so"`) and returns the first entry whose file
    exists on disk, anchoring res:// to the manifest's project root.
    """
    parser = configparser.ConfigParser()
    try:
        with manifest.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error):
        return None
    if not parser.has_section("libraries"):
        return None
    for _key, value in parser.items("libraries"):
        path = value.strip().strip('"')
        if not path.startswith("res://"):
            continue
        relative = path[len("res://"):]
        for base in (manifest.parent.parent.parent, manifest.parent.parent, manifest.parent):
            candidate = base / relative
            if candidate.is_file():
                return candidate
    return None


def discover_consumer_manifests(config: Config) -> list[Path]:
    """Every .gdextension in the consumer project that is not part of the
    framework's own generated output (used for doctor hints)."""
    excluded = {
        config.project_root / config.build_dir,
        config.fixture_path,
        config.project_root / ".godot",
        config.project_root / "extern",
    }
    results = []
    for manifest in config.project_root.rglob("*.gdextension"):
        if any(excluded_dir in manifest.parents for excluded_dir in excluded):
            continue
        results.append(manifest)
    return sorted(results)
