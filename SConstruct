#!/usr/bin/env python3
# Build integration for the GDExtension test framework (plan §10).
#
#   scons platform=linux target=template_debug tests=true
#
# `tests=true` gates GDX_TESTS_ENABLED and compiles the test sources + adapter into a
# SEPARATELY-NAMED shared object (libgdx-test...so) that only testdata/project loads.
# Release artifacts carry neither the define nor the file.

import os

# godot-cpp lives in extern/godot-cpp; its own SConstruct builds the static lib.
cpp_root = "#extern/godot-cpp"

# --- options ----------------------------------------------------------------
from SCons.Script import Variables, EnumVariable, BoolVariable

opts = Variables(None)
opts.Add(EnumVariable("platform", "target platform", "linux",
                      allowed_values=("linux", "macos", "windows")))
opts.Add(EnumVariable("target", "build target", "template_debug",
                      allowed_values=("template_debug", "template_release", "editor")))
opts.Add(BoolVariable("tests", "build the test framework (plan §10)", False))
opts.Add(BoolVariable("sanitize", "ASan/UBSan (plan §10)", False))
opts.Add(BoolVariable("coverage", "code coverage (plan §10)", False))

env = Environment(options=opts, tools=["default"])

# --- godot-cpp static lib + include paths -----------------------------------
env.SConscript(cpp_root + "/SConstruct",
               variant_dir="extern/godot-cpp/.build",
               duplicate=0,
               exports={"env": env})

gen_include = Dir(cpp_root + "/gen/include")
inc_include = Dir(cpp_root + "/include")
env.Append(CPPPATH=[str(gen_include), str(inc_include), str(Dir("src"))])
env.Append(CCFLAGS=["-std=c++17", "-fPIC", "-Wall", "-Wextra"])
# godot-cpp defaults to -fno-exceptions; the framework's abort/catch mechanism
# needs exceptions enabled in the TUs it compiles (appended after the SConscript
# call above so it comes last and wins).
env.Append(CXXFLAGS=["-fexceptions"])

if env["sanitize"]:
    env.Append(CCFLAGS=["-fsanitize=address,undefined", "-fno-omit-frame-pointer"])
    env.Append(LINKFLAGS=["-fsanitize=address,undefined"])
if env["coverage"]:
    env.Append(CCFLAGS=["--coverage"], LINKFLAGS=["--coverage"])

# --- sources ----------------------------------------------------------------
# Framework core + engine-boundary files live under src/ and ship with the
# framework; the host suites (this repo's own tests) live under tests/.
host_sources = []
if env["tests"]:
    host_sources += ["src/gdx_test_entry.cpp"]

    test_framework = [
        "src/framework/registry.cpp",
        "src/framework/runner.cpp",
    ]
    test_suites = [
        "tests/framework_self_tests.cpp",
        "tests/string_utils_tests.cpp",
        "tests/counter_state_tests.cpp",
    ]
    adapter = ["src/support/adapter.cpp"]
else:
    test_framework = []
    test_suites = []
    adapter = []

all_sources = host_sources + test_framework + test_suites + adapter

if not all_sources:
    print("scons: nothing to build (set tests=true)")
    # The godot-cpp static lib above is still the default target; no framework
    # sources are compiled. Fall through: no framework targets.

if all_sources:
    env.Append(CPPDEFINES=[])
    if env["tests"]:
        env.Append(CPPDEFINES=["GDX_TESTS_ENABLED"])

    out_name = "libgdx-test" if env["tests"] else "libgdx"
    out_dir = "bin"
    # SHLIBSUFFIX is appended explicitly: SCons treats the trailing ".x86_64" as
    # an extension and would otherwise skip adding ".so". Same convention as the
    # godot-cpp example project (libgdexample.linux.editor.x86_64.so).
    lib = env.SharedLibrary(
        target=f"{out_dir}/{out_name}.{env['platform']}.{env['target']}.x86_64{env['SHLIBSUFFIX']}",
        source=all_sources,
    )
    Default(lib)
