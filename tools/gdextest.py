#!/usr/bin/env python3
"""Command-line integration for gdextest consumers."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from gdextest_config import (
    Config,
    discover_sources,
    godot_executable,
    godot_version,
    load_config,
    locate_extension_library,
    locate_extension_manifest,
)


CONFIG_TEMPLATE = '''[gdextest]
version = "1"
godot_version = "4.5"

[gdextest.tests]
sources = ["tests/**/*.cpp"]

[gdextest.host]
mode = "editor"
entry_symbol = "gdextest_library_init"

[gdextest.fixture]
directory = "build/gdextest/project"
project_name = "gdextest fixture"
native_extensions = []
assets = []

[gdextest.output]
directory = "bin"
name = "libgdextest"
'''

CI_TEMPLATE = '''name: gdextest

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - name: Install SCons
        run: python3 -m pip install scons
      - name: Download Godot 4.5
        run: |
          curl -fsSL -o godot.zip https://github.com/godotengine/godot/releases/download/4.5-stable/Godot_v4.5-stable_linux.x86_64.zip
          unzip -o godot.zip
          chmod +x Godot_v4.5-stable_linux.x86_64
      - name: Run gdextest
        run: python3 extern/gdextest/tools/gdextest.py test --godot "$GITHUB_WORKSPACE/Godot_v4.5-stable_linux.x86_64"
'''


def _framework_path(config: Config) -> str:
    return str(config.framework_dir)


def _scons_command(config: Config) -> list[str]:
    return ["scons", "tests=true"]


def _run_build(config: Config) -> None:
    sources = discover_sources(config)
    if not sources:
        raise RuntimeError("no test sources found; check [gdextest.tests].sources")
    errors = config.validate()
    if errors:
        raise RuntimeError("configuration is invalid:\n  " + "\n  ".join(errors))
    env = os.environ.copy()
    env["gdextest_PROJECT_ROOT"] = str(config.project_root)
    env["gdextest_FRAMEWORK_DIR"] = _framework_path(config)
    env["gdextest_SOURCES"] = os.pathsep.join(
        str(path.relative_to(config.project_root)) for path in sources)
    env["gdextest_HOST_MODE"] = config.host_mode
    if config.bootstrap:
        env["gdextest_BOOTSTRAP"] = config.bootstrap
    subprocess.run(_scons_command(config), cwd=config.project_root, env=env, check=True)


def _godot_command(config: Config, executable: str, *user_args: str) -> list[str]:
    mode_args = ["--headless", "--editor"] if config.host_mode == "editor" else ["--headless"]
    return [executable, *mode_args, "--path", str(config.fixture_path), "--",
            "--gdextest-run", *user_args]


def _run_environment(config: Config) -> dict[str, str]:
    environment = os.environ.copy()
    user_data = config.project_root / config.build_dir / "user-data"
    user_data.mkdir(parents=True, exist_ok=True)
    environment["XDG_DATA_HOME"] = str(user_data)
    return environment


def _print_check(label: str, value: str, ok: bool) -> bool:
    print(f"{'[ok]' if ok else '[!!]'} {label}: {value}")
    return ok


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.project_root, args.framework_dir)
    print("gdextest doctor")
    print(f"project root: {config.project_root}")
    print(f"framework:    {config.framework_dir}")
    print(f"host mode:    {config.host_mode}")
    print(f"test sources: {len(discover_sources(config))}")

    ok = True
    errors = config.validate()
    ok &= _print_check("configuration", "valid" if not errors else "; ".join(errors), not errors)
    try:
        executable = godot_executable(config, args.godot)
        version = godot_version(executable)
        expected = ".".join(config.godot_version.split(".")[:2])
        ok &= _print_check("Godot", f"{executable} ({version})", version.startswith(expected))
    except (FileNotFoundError, OSError) as error:
        ok &= _print_check("Godot", str(error), False)
    ok &= _print_check("SCons", shutil.which("scons") or "not found", shutil.which("scons") is not None)
    ok &= _print_check("framework SConscript", str(config.framework_dir / "SConscript"),
                       (config.framework_dir / "SConscript").is_file())
    extension_library = locate_extension_library(config)
    extension_manifest = locate_extension_manifest(config)
    if extension_library or extension_manifest:
        ok &= _print_check("consumer extension library", str(extension_library),
                           bool(extension_library and extension_library.is_file()))
        ok &= _print_check("consumer extension manifest", str(extension_manifest),
                           bool(extension_manifest and extension_manifest.is_file()))
    return 0 if ok else 2


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    config_path = root / ".gdextest.toml"
    if config_path.exists() and not args.force:
        print(f"gdextest: keeping existing {config_path}")
    else:
        config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        print(f"gdextest: wrote {config_path}")
    if args.ci:
        workflow = root / ".github" / "workflows" / "gdextest.yml"
        if workflow.exists() and not args.force:
            print(f"gdextest: keeping existing {workflow}")
        else:
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text(CI_TEMPLATE, encoding="utf-8")
            print(f"gdextest: wrote {workflow}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    config = load_config(args.project_root, args.framework_dir)
    _run_build(config)
    executable = godot_executable(config, args.godot)
    command = _godot_command(config, executable, "--gdextest-list")
    return subprocess.run(command, cwd=config.project_root, env=_run_environment(config)).returncode


def cmd_test(args: argparse.Namespace) -> int:
    config = load_config(args.project_root, args.framework_dir)
    _run_build(config)
    executable = godot_executable(config, args.godot)
    expected = ".".join(config.godot_version.split(".")[:2])
    actual = godot_version(executable)
    if expected and not actual.startswith(expected):
        raise RuntimeError(f"Godot {actual} found, but gdextest requires {config.godot_version}")
    user_args: list[str] = []
    if args.filter:
        user_args.append(f"--gdextest-filter={args.filter}")
    if args.shard:
        user_args.append(f"--gdextest-shard={args.shard}")
    if args.shuffle is not None:
        user_args.append("--gdextest-shuffle" if args.shuffle == "" else
                         f"--gdextest-shuffle={args.shuffle}")
    if args.json:
        # Godot chdirs to the fixture dir (--path), so a relative path would resolve
        # against the fixture, not the user's cwd. Resolve it up front.
        user_args.append(f"--gdextest-json={os.path.abspath(args.json)}")
    return subprocess.run(_godot_command(config, executable, *user_args),
                          cwd=config.project_root, env=_run_environment(config)).returncode


def cmd_clean(args: argparse.Namespace) -> int:
    config = load_config(args.project_root, args.framework_dir)
    for relative in (config.fixture_dir, config.build_dir):
        path = config.project_root / relative
        if path.exists():
            shutil.rmtree(path)
            print(f"gdextest: removed {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gdextest")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--framework-dir")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create starter configuration")
    init.add_argument("--ci", action="store_true", help="also create a GitHub Actions workflow")
    init.add_argument("--force", action="store_true")
    init.set_defaults(function=cmd_init)

    doctor = subparsers.add_parser("doctor", help="validate the consumer environment")
    doctor.add_argument("--godot")
    doctor.set_defaults(function=cmd_doctor)

    test = subparsers.add_parser("test", help="build and run tests")
    test.add_argument("--godot")
    test.add_argument("--filter")
    test.add_argument("--shard")
    test.add_argument("--shuffle", nargs="?", const="", default=None)
    test.add_argument("--json")
    test.set_defaults(function=cmd_test)

    listing = subparsers.add_parser("list", help="build and list tests")
    listing.add_argument("--godot")
    listing.set_defaults(function=cmd_list)

    clean = subparsers.add_parser("clean", help="remove generated test output")
    clean.set_defaults(function=cmd_clean)

    args = parser.parse_args(argv)
    try:
        return args.function(args)
    except (FileNotFoundError, RuntimeError, OSError) as error:
        print(f"gdextest: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
