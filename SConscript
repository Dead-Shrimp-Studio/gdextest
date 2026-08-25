#!/usr/bin/env python3
# Reusable build wiring for the gdextest framework.
#
# Include this from your extension's SConstruct after godot-cpp is wired into
# `env`. The common consumer path only needs suites:
#
#   lib = env.SConscript(
#       "extern/gdxtest/SConscript",
#       variant_dir="build/gdxtest", duplicate=0,
#       exports={"env": env, "gdxtest": {
#           "enabled": env.get("tests", False),
#           "suites": Glob("tests/*.cpp"),
#       }},
#   )
#   if lib:
#       Default(lib)
#
# The framework supplies the entry point, adapter, output name, and a generated
# fixture project. `entry`, `adapter`, and fixture settings remain overrideable
# for extensions with custom startup behavior.

Import("env")

import importlib.util
import os

from SCons.Errors import UserError
from SCons.Script import Default

try:
    Import("gdxtest")
except Exception:
    gdxtest = {}

# --- enabled? ----------------------------------------------------------------
enabled = gdxtest.get("enabled")
if enabled is None:
    enabled = env.get("tests", False)
    if not enabled:
        try:
            enabled = ARGUMENTS.get("tests", "false").lower() in ("1", "true", "yes")
        except NameError:
            pass

if not enabled:
    print("gdxtest: disabled (pass tests=true or gdxtest['enabled'])")
    Return()

# --- paths and options -------------------------------------------------------
framework_root = Dir(".").srcnode()
out_dir = gdxtest.get("out_dir", "bin")
out_name = gdxtest.get("out_name", "libgdxtest")

# godot-cpp sets env["suffix"] (".linux.template_debug.x86_64"). Fall back
# for hosts whose env did not go through godot-cpp's SConscript.
suffix = env.get("suffix", "")
if not suffix:
    plat = env.get("platform", "")
    tgt = env.get("target", "")
    arch = env.get("arch", "x86_64")
    if plat and tgt:
        suffix = f".{plat}.{tgt}.{arch}"

entry = gdxtest.get("entry", framework_root.File("src/gdx_test_entry.cpp"))
adapter = gdxtest.get("adapter", framework_root.File("src/support/adapter.cpp"))
if not entry or not adapter:
    raise UserError("gdxtest: 'entry' and 'adapter' must be valid paths")


def root_path(path):
    """Resolve host-supplied paths against the host project root."""
    if isinstance(path, str) and not path.startswith("#") and not os.path.isabs(path):
        return "#" + path
    return path


def to_script_rel(path):
    """Map a source into this SConscript's variant directory."""
    absolute = os.path.abspath(env.File(root_path(path)).abspath)
    return os.path.relpath(absolute, framework_root.abspath)


framework_sources = [
    to_script_rel(source)
    for source in env.Glob(str(framework_root.abspath) + "/src/framework/*.cpp")
]
suite_sources = gdxtest.get("suites")
if suite_sources is None:
    configured_sources = os.environ.get("GDXTEST_SOURCES", "")
    suite_sources = ([root_path(path) for path in configured_sources.split(os.pathsep)
                      if path] if configured_sources else env.Glob("#tests/**/*.cpp"))
bootstrap = gdxtest.get("bootstrap", "tests/gdxtest_bootstrap.cpp")
bootstrap_path = env.File(root_path(bootstrap))
if bootstrap_path.exists():
    suite_sources = list(suite_sources) + [bootstrap_path]
sources = (
    [to_script_rel(entry), to_script_rel(adapter)]
    + [to_script_rel(source) for source in suite_sources]
    + framework_sources
)

# --- test library ------------------------------------------------------------
test_env = env.Clone()
test_env.Append(CPPDEFINES=["GDX_TESTS_ENABLED"])
test_env.Append(CPPPATH=[framework_root.Dir("src")])
test_env.Append(CCFLAGS=["-std=c++17", "-fPIC", "-Wall", "-Wextra"])
# godot-cpp defaults to -fno-exceptions; the framework uses exceptions to abort
# an individual test body without crossing an engine callback boundary.
test_env.Append(CXXFLAGS=["-fexceptions"])

if not test_env.get("LIBS"):
    print("gdxtest: WARNING - env has no LIBS; did you wire godot-cpp before calling this SConscript?")

out_abs = os.path.join(env.Dir("#").abspath, out_dir)
target = f"{out_abs}/{out_name}{suffix}{test_env['SHLIBSUFFIX']}"
lib = test_env.SharedLibrary(target=target, source=sources)
print(f"gdxtest: test library -> {target}")

# --- generated fixture -------------------------------------------------------
generate_fixture = gdxtest.get("generate_fixture", True)
if generate_fixture:
    fixture_dir = gdxtest.get("fixture_dir", "build/gdxtest/project")
    fixture_abs = os.path.join(env.Dir("#").abspath, fixture_dir)
    project_name = gdxtest.get("project_name", "gdxtest fixture")
    entry_symbol = gdxtest.get("entry_symbol", "gdx_test_library_init")
    godot_version = gdxtest.get("godot_version", "4.5")
    manifest_name = gdxtest.get("manifest_name", out_name + ".gdextension")
    library_basename = os.path.basename(target)

    platform = env.get("platform", "linux")
    target_name = env.get("target", "template_debug")
    arch = env.get("arch", "x86_64")
    feature = "release" if target_name == "template_release" else "debug"
    library_key = gdxtest.get(
        "library_key", f"{platform}.{feature}.{arch}")

    fixture_targets = [
        os.path.join(fixture_abs, "project.godot"),
        os.path.join(fixture_abs, "addons", "gdxtest", "plugin.cfg"),
        os.path.join(fixture_abs, "addons", "gdxtest", "plugin.gd"),
        os.path.join(fixture_abs, "addons", "gdxtest", manifest_name),
        os.path.join(fixture_abs, "addons", "gdxtest", "bin", library_basename),
    ]
    generator_path = framework_root.File("tools/generate_fixture.py")
    generator_spec = importlib.util.spec_from_file_location(
        "gdxtest_fixture_generator", generator_path.abspath)
    fixture_generator = importlib.util.module_from_spec(generator_spec)
    generator_spec.loader.exec_module(fixture_generator)

    def generate_fixture_action(target=None, source=None, env=None):
        fixture_generator.generate_fixture(
            project_root=fixture_abs,
            library_path=source[0].abspath,
            library_basename=library_basename,
            manifest_basename=manifest_name,
            entry_symbol=entry_symbol,
            project_name=project_name,
            godot_version=godot_version,
            library_key=library_key,
            native_extensions=gdxtest.get("native_extensions", []),
            extension_library=gdxtest.get("extension_library"),
            extension_manifest=gdxtest.get("extension_manifest"),
            fixture_assets=gdxtest.get("fixture_assets", []),
            project_source_root=env.Dir("#").abspath,
        )
        return 0

    fixture = test_env.Command(
        fixture_targets,
        [lib, generator_path],
        generate_fixture_action,
    )
    Default(fixture)
    print(f"gdxtest: fixture -> {fixture_abs}")

Return("lib")
