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
#           # Omit 'enabled': the SConscript toggles from `scons tests=true`.
#           "suites": Glob("tests/**/*.cpp"),
#       }},
#   )
#   if lib:
#       Default(lib)
#
# The framework supplies the entry point, adapter, output name, and a generated
# fixture project. `entry`, `adapter`, and fixture settings remain overrideable
# for extensions with custom startup behavior.
#
# Config contract: values flow from the most specific to the least specific
# source — the `gdextest` export wins, then the env vars the CLI sets
# (`gdextest_SOURCES`, `gdextest_BOOTSTRAP`, `gdextest_HOST_MODE`), then the
# consumer's `.gdextest.toml` (loaded here), then built-in defaults. This keeps
# the TOML the single source of truth for the CLI-driven flow.

Import("env")

import importlib.util
import os
import sys

from SCons.Errors import UserError
from SCons.Script import Default

try:
    Import("gdextest")
except Exception:
    gdextest = {}

# --- config ---------------------------------------------------------------
framework_root = Dir(".").srcnode()
# Register in sys.modules before exec: the module's @dataclass resolves its
# field types through sys.modules[__module__] at class-creation time.
_config_spec = importlib.util.spec_from_file_location(
    "gdextest_config_consumer", framework_root.File("tools/gdextest_config.py").abspath)
_config_module = importlib.util.module_from_spec(_config_spec)
sys.modules[_config_spec.name] = _config_module
_config_spec.loader.exec_module(_config_module)


def _load_toml_config():
    """Load the consumer's .gdextest.toml as the default configuration."""
    try:
        return _config_module.load_config(Dir("#").abspath, framework_root.abspath)
    except Exception as error:
        raise UserError(f"gdextest: failed to load consumer config: {error}")


toml_config = _load_toml_config()


def _env(name: str, default=None):
    return os.environ.get(name, default)


def _argument(name: str, default=None):
    try:
        return ARGUMENTS.get(name, default)
    except NameError:
        return default


# --- enabled? ----------------------------------------------------------------
enabled = gdextest.get("enabled")
if enabled is None:
    enabled = env.get("tests", False)
    if not enabled:
        enabled = _argument("tests", "false").lower() in ("1", "true", "yes", "on")
# env["tests"] may arrive as a string from Variables; normalize so a literal
# "false"/"0" disables instead of silently enabling (truthy string).
if isinstance(enabled, str):
    enabled = enabled.lower() in ("1", "true", "yes", "on")

if not enabled:
    print("gdextest: disabled (pass tests=true or gdextest['enabled'])")
    Return()

# --- paths and options -------------------------------------------------------
out_dir = gdextest.get("out_dir", toml_config.out_dir)
out_name = gdextest.get("out_name", toml_config.out_name)

# godot-cpp sets env["suffix"] (".linux.template_debug.x86_64"). Fall back
# for hosts whose env did not go through godot-cpp's SConscript — including
# `platform`/`target`/`arch` passed as scons ARGUMENTS, which is how the CLI
# drives cross-compile and editor-only targets.
suffix = env.get("suffix", "")
if not suffix:
    plat = env.get("platform", _argument("platform", ""))
    tgt = env.get("target", _argument("target", ""))
    arch = env.get("arch", _argument("arch", "x86_64"))
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
# An explicit but empty list usually means a Glob that matched nothing (e.g.
# `Glob("tests/*.cpp")` with suites in a subdirectory) — treat it like an
# unset list and fall back to the CLI/TOML source discovery, which the doctor
# has already validated against the same .gdextest.toml.
if not suite_sources:
    configured_sources = _env("gdextest_SOURCES", "")
    if configured_sources:
        suite_sources = [root_path(path) for path in configured_sources.split(os.pathsep)
                         if path]
    else:
        # Strict discovery: a zero-match pattern in the TOML is a config error,
        # not an empty suite set — fail naming the offending pattern.
        try:
            suite_sources = [str(path) for path in
                             _config_module.resolve_sources(toml_config)]
        except RuntimeError as error:
            raise UserError(f"gdextest: {error}")
bootstrap = gdextest.get("bootstrap", _env("gdextest_BOOTSTRAP", toml_config.bootstrap))
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
# Public headers live in include/gdextest/, so suites include them as
# `#include "gdextest/assert.h"` etc. (the classic library layout).
test_env.Append(CPPPATH=[framework_root.Dir("include")])
# A consumer's env commonly carries root-relative CPPPATH/LIBPATH strings
# (e.g. "extern/godot-cpp/bin") written against their top-level SConstruct.
# Used from this SConscript (extern/gdextest/) SCons would resolve those
# against extern/gdextest/ instead, silently breaking the test build's
# includes and links. Rebase them to the consumer's project root so the
# test build looks in the same places as the consumer's own build.
_project_root = env.Dir("#").abspath


def _anchor_root_path(value):
    if (isinstance(value, str) and value and not value.startswith("#")
            and not os.path.isabs(value)):
        return os.path.join(_project_root, value)
    return value

for _var in ("CPPPATH", "LIBPATH"):
    test_env[_var] = [_anchor_root_path(entry) for entry in test_env.get(_var, [])]
# Keep warnings enabled for gdextest and consumer code, but do not emit the
# vendored godot-cpp header warnings into every consumer build.
godot_cpp_includes = [include for include in test_env.get("CPPPATH", [])
                      if "godot-cpp" in str(include)]
_is_msvc = (test_env.get("PLATFORM") == "win32" or
            os.path.basename(str(test_env.get("CC", ""))).lower().startswith("cl"))
if _is_msvc:
    for include in godot_cpp_includes:
        test_env.Append(CCFLAGS=["/external:I", str(include)])
    test_env.Append(CCFLAGS=["/W4"])
    # C++20 for coroutines (async tests, plan §7.2) + exceptions (abort an
    # individual test body without crossing an engine callback boundary).
    test_env.Append(CXXFLAGS=["/std:c++20", "/EHsc"])
else:
    for include in godot_cpp_includes:
        test_env.Append(CCFLAGS=["-isystem", str(include)])
    test_env.Append(CCFLAGS=["-fPIC", "-Wall", "-Wextra"])
    test_env.Append(CXXFLAGS=["-fexceptions", "-std=c++20"])

if not test_env.get("LIBS"):
    print("gdextest: WARNING - env has no LIBS; did you wire godot-cpp before calling this SConscript?")

# Every test-library object gets an explicit target under this SConscript's
# variant directory, mirroring the source's path relative to the project root.
# The host build usually compiles the same extension sources in place (objects
# beside sources, the godot-cpp convention) with different flags; relying on
# SCons' implicit object placement then derives the same object paths for both
# environments and aborts with "Two environments with different actions were
# specified for the same target". Explicit targets keep the graphs disjoint.
def _source_node(source):
    """Resolve a sources-list entry (string = framework-root-relative)."""
    if isinstance(source, str):
        return framework_root.File(source)
    return source


def _isolated_object(source):
    node = _source_node(source)
    relative = os.path.relpath(node.abspath, _project_root)
    if relative.startswith(".."):
        # Outside the project root: flatten so the object still lands in obj/.
        relative = os.path.basename(relative)
    # Strip the source extension: a target that already ends in a recognized
    # suffix (.cpp, .c, ...) suppresses the object-suffix append and SCons
    # writes the object over a .cpp-named path, which then gets compiled as
    # source on a later pass. With no extension, SharedObject appends
    # $SHOBJSUFFIX (.os / .obj) itself.
    relative = os.path.splitext(relative)[0]
    return test_env.SharedObject(
        target=os.path.join(Dir(".").abspath, "obj", relative), source=node)


objects = [_isolated_object(source) for source in sources]

out_abs = os.path.join(env.Dir("#").abspath, out_dir)
target = f"{out_abs}/{out_name}{suffix}{test_env['SHLIBSUFFIX']}"
lib = test_env.SharedLibrary(target=target, source=objects)
print(f"gdextest: test library -> {target}")

# --- generated fixture -------------------------------------------------------
generate_fixture = gdextest.get("generate_fixture", True)
if generate_fixture:
    fixture_dir = gdextest.get("fixture_dir", toml_config.fixture_dir)
    fixture_abs = os.path.join(env.Dir("#").abspath, fixture_dir)
    project_name = gdextest.get("project_name", toml_config.project_name)
    entry_symbol = gdextest.get("entry_symbol", toml_config.entry_symbol)
    plugin_class = gdextest.get("plugin_class", toml_config.plugin_class)
    godot_version = gdextest.get("godot_version", toml_config.godot_version)
    host_mode = gdextest.get("host_mode", _env("gdextest_HOST_MODE", toml_config.host_mode))
    if host_mode not in ("editor", "runtime"):
        raise UserError(f"gdextest: unsupported host_mode {host_mode!r} (expected 'editor' or 'runtime')")
    manifest_name = gdextest.get("manifest_name",
                                  toml_config.manifest_name or out_name + ".gdextension")
    library_basename = os.path.basename(target)

    platform = env.get("platform", _argument("platform", "linux"))
    target_name = env.get("target", _argument("target", "template_debug"))
    arch = env.get("arch", _argument("arch", "x86_64"))
    feature = "release" if target_name == "template_release" else "debug"
    library_key = gdextest.get("library_key", toml_config.library_key) or \
        f"{platform}.{feature}.{arch}"
    scan_timeout_ms = gdextest.get("scan_timeout_ms", toml_config.scan_timeout_ms)

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
            plugin_class=plugin_class,
            project_name=project_name,
            godot_version=godot_version,
            library_key=library_key,
            native_extensions=gdextest.get("native_extensions", toml_config.native_extensions),
            extension_library=gdextest.get("extension_library", toml_config.extension_library),
            extension_manifest=gdextest.get("extension_manifest", toml_config.extension_manifest),
            fixture_assets=gdextest.get("fixture_assets", toml_config.fixture_assets),
            host_mode=host_mode,
            project_source_root=env.Dir("#").abspath,
            scan_timeout_ms=scan_timeout_ms,
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
