#!/usr/bin/env python3
"""Convenient command-line integration for gdxtest consumers."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from gdxtest_config import Config, discover_sources, godot_executable, godot_version, load_config


CONFIG_TEMPLATE = '''[gdxtest]
godot_version = "4.5"
fixture_dir = "build/gdxtest/project"
build_dir = "build/gdxtest"
out_dir = "bin"
out_name = "libgdxtest"
test_sources = ["tests/**/*.cpp"]
entry_symbol = "gdx_test_library_init"
project_name = "gdxtest fixture"
'''

CI_TEMPLATE = '''name: gdxtest

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
      - name: Run gdxtest
        run: python3 extern/gdxtest/tools/gdxtest.py test --godot "$GITHUB_WORKSPACE/Godot_v4.5-stable_linux.x86_64"
'''


def _scons_command(config: Config, sources: list[Path]) -> list[str]:
    # SConstructs are free to discover sources themselves. The environment
    # variables make the convention available to simple host SConstructs too.
    command = ["scons", "tests=true"]
    return command


def _run_build(config: Config) -> None:
    env = os.environ.copy()
    env["GDXTEST_PROJECT_ROOT"] = str(config.project_root)
    env["GDXTEST_SOURCES"] = os.pathsep.join(
        str(path.relative_to(config.project_root)) for path in discover_sources(config))
    subprocess.run(_scons_command(config, discover_sources(config)), cwd=config.project_root,
                   env=env, check=True)


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    config_path = root / ".gdxtest.toml"
    if config_path.exists() and not args.force:
        print(f"gdxtest: keeping existing {config_path}")
    else:
        config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        print(f"gdxtest: wrote {config_path}")
    if args.ci:
        workflow = root / ".github" / "workflows" / "gdxtest.yml"
        if workflow.exists() and not args.force:
            print(f"gdxtest: keeping existing {workflow}")
        else:
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text(CI_TEMPLATE, encoding="utf-8")
            print(f"gdxtest: wrote {workflow}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    _run_build(config)
    executable = godot_executable(config, args.godot)
    command = [executable, "--headless", "--editor", "--path", str(config.fixture_path), "--",
               "--gdxtest-run", "--gdxtest-list"]
    return subprocess.run(command, cwd=config.project_root).returncode


def cmd_test(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    _run_build(config)
    executable = godot_executable(config, args.godot)
    expected = config.godot_version.split(".")[:2]
    actual = godot_version(executable)
    if expected and not actual.startswith(".".join(expected)):
        raise RuntimeError(f"Godot {actual} found, but gdxtest requires {config.godot_version}")
    command = [executable, "--headless", "--editor", "--path", str(config.fixture_path), "--",
               "--gdxtest-run"]
    if args.filter:
        command.append(f"--gdxtest-filter={args.filter}")
    if args.shard:
        command.append(f"--gdxtest-shard={args.shard}")
    if args.shuffle is not None:
        command.append("--gdxtest-shuffle" if args.shuffle == "" else
                       f"--gdxtest-shuffle={args.shuffle}")
    if args.json:
        command.append(f"--gdxtest-json={args.json}")
    environment = os.environ.copy()
    user_data = config.project_root / config.build_dir / "user-data"
    user_data.mkdir(parents=True, exist_ok=True)
    environment["XDG_DATA_HOME"] = str(user_data)
    return subprocess.run(command, cwd=config.project_root, env=environment).returncode


def cmd_clean(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    for relative in (config.fixture_dir, config.build_dir):
        path = config.project_root / relative
        if path.exists():
            shutil.rmtree(path)
            print(f"gdxtest: removed {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gdxtest")
    parser.add_argument("--project-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create starter configuration")
    init.add_argument("--ci", action="store_true", help="also create a GitHub Actions workflow")
    init.add_argument("--force", action="store_true")
    init.set_defaults(function=cmd_init)

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
    except (FileNotFoundError, RuntimeError) as error:
        print(f"gdxtest: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
