#!/usr/bin/env python3
# Reusable build wiring for the gdextest framework.
#
# Include this from your extension's SConstruct to compile the framework core,
# your entry point, your adapter, and your suites into a test-only shared
# object. Call it AFTER your godot-cpp SConscript so `env` already carries
# godot-cpp's include paths and LIBS (this repo's SConstruct is a working
# example of the full call).
#
#   lib = env.SConscript(
#       "extern/gdextest/SConscript",
#       variant_dir="build/gdextest", duplicate=0,   # keep objects out of the submodule
#       exports={"env": env, "gdxtest": {
#           "enabled":  env.get("tests", False),     # or omit -> ARGUMENTS tests=true
#           "entry":    "testsupport/entry.cpp",     # host entry (required)
#           "adapter":  "testsupport/adapter.cpp",   # host adapter (required)
#           "suites":   Glob("tests/*.cpp"),         # host suites (optional)
#           "out_dir":  "bin",
#           "out_name": "libgdxtest",                # -> libgdxtest.linux.template_debug.x86_64.so
#       }},
#   )
#   if lib:
#       Default(lib)
#
# Paths in `gdxtest` resolve against your project root (pass plain relative
# paths, "#..." paths, absolute paths, or SCons nodes). Returns the
# shared-library node, or None when disabled.

Import("env")

import os

from SCons.Errors import UserError

try:
    Import("gdxtest")
except Exception:
    gdxtest = {}

# --- enabled? ----------------------------------------------------------------
# Explicit flag wins; otherwise env["tests"]; otherwise `scons tests=true`.
enabled = gdxtest.get("enabled")
if enabled is None:
    enabled = env.get("tests", False)
    if not enabled:
        try:
            enabled = ARGUMENTS.get("tests", "false").lower() in ("1", "true", "yes")
        except NameError:
            pass

if not enabled:
    print("gdextest: disabled (pass tests=true or gdxtest['enabled'])")
    Return()

# --- options -----------------------------------------------------------------
out_dir = gdxtest.get("out_dir", "bin")
out_name = gdxtest.get("out_name", "libgdextest")
# godot-cpp sets env["suffix"] (".linux.template_debug.x86_64"); fall back for
# hosts whose env didn't go through godot-cpp's SConscript.
suffix = env.get("suffix", "")
if not suffix:
    plat, tgt, arch = env.get("platform", ""), env.get("target", ""), env.get("arch", "x86_64")
    if plat and tgt:
        suffix = f".{plat}.{tgt}.{arch}"

entry = gdxtest.get("entry")
adapter = gdxtest.get("adapter")
if not entry or not adapter:
    raise UserError("gdextest: 'entry' and 'adapter' are required in the gdxtest exports")


def root_path(p):
    """Resolve host-supplied paths against the host project root."""
    if isinstance(p, str) and not p.startswith("#") and not os.path.isabs(p):
        return "#" + p
    return p


framework_root = Dir(".").srcnode()  # real framework dir (works with/without variant_dir)


def to_script_rel(p):
    """Return p as a path relative to this SConscript dir, so variant_dir maps
    its object files into the variant dir instead of polluting source trees
    (absolute/# paths bypass the variant mapping and objects land next to the
    sources). Host files outside the framework tree fall back to normal SCons
    behavior (objects next to their sources)."""
    abs_p = os.path.abspath(env.File(root_path(p)).abspath)
    return os.path.relpath(abs_p, framework_root.abspath)


framework_sources = [to_script_rel(f) for f in
                     env.Glob(str(framework_root.abspath) + "/src/framework/*.cpp")]

sources = ([to_script_rel(entry), to_script_rel(adapter)]
           + [to_script_rel(s) for s in gdxtest.get("suites", [])]
           + framework_sources)

# --- build environment --------------------------------------------------------
# Clone so the host's env (and its real extension build) stays untouched.
test_env = env.Clone()
test_env.Append(CPPDEFINES=["GDX_TESTS_ENABLED"])          # gates all framework code
test_env.Append(CPPPATH=[framework_root.Dir("src")])       # "#include "framework/..."
test_env.Append(CCFLAGS=["-std=c++17", "-fPIC", "-Wall", "-Wextra"])
# godot-cpp defaults to -fno-exceptions; the framework's abort/catch mechanism
# needs exceptions enabled in the TUs it compiles (appended last so it wins).
test_env.Append(CXXFLAGS=["-fexceptions"])

if not test_env.get("LIBS"):
    print("gdextest: WARNING - env has no LIBS; did you wire godot-cpp before calling this SConscript?")

# SHLIBSUFFIX is appended explicitly: SCons treats a trailing ".x86_64" as a
# file extension and would otherwise skip the ".so" (godot-cpp convention).
# The target is made absolute so it lands in the host project's out_dir, not
# inside this SConscript's variant dir.
out_abs = os.path.join(env.Dir("#").abspath, out_dir)
target = f"{out_abs}/{out_name}{suffix}{test_env['SHLIBSUFFIX']}"
lib = test_env.SharedLibrary(target=target, source=sources)
print(f"gdextest: test library -> {target}")

Return("lib")
