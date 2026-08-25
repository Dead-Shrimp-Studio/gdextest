#!/usr/bin/env python3
# Reusable build wiring for the gdextest framework.
#
# Include this from your extension's SConstruct after godot-cpp is wired into
# `env`. The common consumer path only needs suites:
#
#   lib = env.SConscript(
#       "extern/gdextest/SConscript",
#       variant_dir="build/gdextest", duplicate=0,
#       exports={"env": env, "gdextest": {
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
    Import("gdextest")
except Exception:
    gdextest = {}

# --- enabled? ----------------------------------------------------------------
enabled = gdextest.get("enabled")
if enabled is None:
    enabled = env.get("tests", False)
    if not enabled:
        try:
            enabled = ARGUMENTS.get("tests", "false").lower() in ("1", "true", "yes")
        except NameError:
            pass

if not enabled:
    print("gdextest: disabled (pass tests=true or gdextest['enabled'])")
    Return()

# --- paths and options -------------------------------------------------------
framework_root = Dir(".").srcnode()
out_dir = gdextest.get("out_dir", "bin")
out_name = gdextest.get("out_name", "libgdextest")

# godot-cpp sets env["suffix"] (".linux.template_debug.x86_64"). Fall back
# for hosts whose env did not go through godot-cpp's SConscript.
suffix = env.get("suffix", "")
if not suffix:
    plat = env.get("platform", "")
    tgt = env.get("target", "")
    arch = env.get("arch", "x86_64")
    if plat and tgt:
        suffix = f".{plat}.{tgt}.{arch}"

entry = gdextest.get("entry", framework_root.File("src/gdextest_entry.cpp"))
adapter = gdextest.get("adapter", framework_root.File("src/support/adapter.cpp"))
if not entry or not adapter:
    raise UserError("gdextest: 'entry' and 'adapter' must be valid paths")


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
suite_sources = gdextest.get("suites")
if suite_sources is None:
    configured_sources = os.environ.get("GDEXTEST_SOURCES", "")
    suite_sources = ([root_path(path) for path in configured_sources.split(os.pathsep)
                      if path] if configured_sources else env.Glob("#tests/**/*.cpp"))
bootstrap = gdextest.get("bootstrap", os.environ.get("GDEXTEST_BOOTSTRAP"))
bootstrap_path = env.File(root_path(bootstrap)) if bootstrap else None
if bootstrap_path and bootstrap_path.exists():
    suite_sources = list(suite_sources) + [bootstrap_path]
sources = (
    [to_script_rel(entry), to_script_rel(adapter)]
    + [to_script_rel(source) for source in suite_sources]
    + framework_sources
)

# --- test library ------------------------------------------------------------
test_env = env.Clone()
test_env.Append(CPPDEFINES=["GDEXTEST_ENABLED", "GDEXTEST_BUILDING"])
test_env.Append(CPPPATH=[framework_root.Dir("src")])
# Keep warnings enabled for gdextest and consumer code, but do not emit the
# vendored godot-cpp header warnings into every consumer build.
godot_cpp_includes = [include for include in test_env.get("CPPPATH", [])
                      if "godot-cpp" in str(include)]
for include in godot_cpp_includes:
    test_env.Append(CCFLAGS=["-isystem", str(include)])
test_env.Append(CCFLAGS=["-std=c++17", "-fPIC", "-Wall", "-Wextra"])
# godot-cpp defaults to -fno-exceptions; the framework uses exceptions to abort
# an individual test body without crossing an engine callback boundary.
test_env.Append(CXXFLAGS=["-fexceptions"])

if not test_env.get("LIBS"):
    print("gdextest: WARNING - env has no LIBS; did you wire godot-cpp before calling this SConscript?")

out_abs = os.path.join(env.Dir("#").abspath, out_dir)
target = f"{out_abs}/{out_name}{suffix}{test_env['SHLIBSUFFIX']}"
lib = test_env.SharedLibrary(target=target, source=sources)
print(f"gdextest: test library -> {target}")

# --- generated fixture -------------------------------------------------------
generate_fixture = gdextest.get("generate_fixture", True)
if generate_fixture:
    fixture_dir = gdextest.get("fixture_dir", "build/gdextest/project")
    fixture_abs = os.path.join(env.Dir("#").abspath, fixture_dir)
    project_name = gdextest.get("project_name", "gdextest fixture")
    entry_symbol = gdextest.get("entry_symbol", "gdextest_library_init")
    godot_version = gdextest.get("godot_version", "4.5")
    host_mode = gdextest.get("host_mode", os.environ.get("GDEXTEST_HOST_MODE", "editor"))
    manifest_name = gdextest.get("manifest_name", out_name + ".gdextension")
    library_basename = os.path.basename(target)

    platform = env.get("platform", "linux")
    target_name = env.get("target", "template_debug")
    arch = env.get("arch", "x86_64")
    feature = "release" if target_name == "template_release" else "debug"
    library_key = gdextest.get(
        "library_key", f"{platform}.{feature}.{arch}")

    host_targets = ([
        os.path.join(fixture_abs, "addons", "gdextest", "plugin.cfg"),
        os.path.join(fixture_abs, "addons", "gdextest", "plugin.gd"),
    ] if host_mode == "editor" else [
        os.path.join(fixture_abs, "addons", "gdextest", "runtime.gd"),
    ])
    fixture_targets = [
        os.path.join(fixture_abs, "project.godot"),
        *host_targets,
        os.path.join(fixture_abs, "addons", "gdextest", manifest_name),
        os.path.join(fixture_abs, "addons", "gdextest", "bin", library_basename),
    ]
    generator_path = framework_root.File("tools/generate_fixture.py")
    generator_spec = importlib.util.spec_from_file_location(
        "gdextest_fixture_generator", generator_path.abspath)
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
            native_extensions=gdextest.get("native_extensions", []),
            extension_library=gdextest.get("extension_library"),
            extension_manifest=gdextest.get("extension_manifest"),
            fixture_assets=gdextest.get("fixture_assets", []),
            host_mode=host_mode,
            project_source_root=env.Dir("#").abspath,
        )
        return 0

    fixture = test_env.Command(
        fixture_targets,
        [lib, generator_path],
        generate_fixture_action,
    )
    Default(fixture)
    print(f"gdextest: fixture -> {fixture_abs}")

Return("lib")
