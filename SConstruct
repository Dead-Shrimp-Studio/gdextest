#!/usr/bin/env python3
# Build integration for the gdextest framework (this repo is the reference host).
#
#   scons platform=linux target=template_debug tests=true
#
# `tests=true` builds the framework core + this repo's entry/adapter/suites into
# a separately-named shared object (libgdx-test...so) that only testdata/project
# loads. Release artifacts carry neither the define nor the file.

# godot-cpp lives in extern/godot-cpp; its own SConstruct builds the static lib.
cpp_root = "#extern/godot-cpp"

# --- options ----------------------------------------------------------------
from SCons.Script import Variables, EnumVariable, BoolVariable

opts = Variables(None)
opts.Add(EnumVariable("platform", "target platform", "linux",
                      allowed_values=("linux", "macos", "windows")))
opts.Add(EnumVariable("target", "build target", "template_debug",
                      allowed_values=("template_debug", "template_release", "editor")))
opts.Add(BoolVariable("tests", "build the test framework", False))
opts.Add(BoolVariable("sanitize", "ASan/UBSan", False))
opts.Add(BoolVariable("coverage", "code coverage", False))

env = Environment(options=opts, tools=["default"])

# --- godot-cpp static lib + include paths -----------------------------------
env.SConscript(cpp_root + "/SConstruct",
               variant_dir="extern/godot-cpp/.build",
               duplicate=0,
               exports={"env": env})

gen_include = Dir(cpp_root + "/gen/include")
inc_include = Dir(cpp_root + "/include")
env.Append(CPPPATH=[str(gen_include), str(inc_include)])

if env["sanitize"]:
    env.Append(CCFLAGS=["-fsanitize=address,undefined", "-fno-omit-frame-pointer"])
    env.Append(LINKFLAGS=["-fsanitize=address,undefined"])
if env["coverage"]:
    env.Append(CCFLAGS=["--coverage"], LINKFLAGS=["--coverage"])

# --- the framework test library ----------------------------------------------
# The reusable wiring lives in SConscript; this host passes its own files.
lib = env.SConscript(
    "SConscript",
    variant_dir="build/gdextest",
    duplicate=0,
    exports={"env": env, "gdxtest": {
        "enabled": env["tests"],
        "entry":   "src/gdx_test_entry.cpp",
        "adapter": "src/support/adapter.cpp",
        "suites": [
            "tests/framework_self_tests.cpp",
            "tests/string_utils_tests.cpp",
            "tests/counter_state_tests.cpp",
            "tests/engine_integration_tests.cpp",
            "tests/reference_skip_tests.cpp",
        ],
        "out_name": "libgdx-test",
    }},
)
if lib:
    Default(lib)
