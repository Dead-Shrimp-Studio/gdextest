#!/usr/bin/env python3
# Build integration for the gdextest framework (this repo is the reference host).
#
#   scons platform=linux target=template_debug tests=true

cpp_root = "#extern/godot-cpp"

# --- options ----------------------------------------------------------------
import sys
from pathlib import Path

from SCons.Script import Variables, EnumVariable, BoolVariable, Alias, ARGUMENTS

_tools_dir = Path(Dir("#").abspath) / "tools"
sys.path.insert(0, str(_tools_dir))
from gdextest_config import load_config

opts = Variables(None)
opts.Add(EnumVariable("platform", "target platform", "linux",
                      allowed_values=("linux", "macos", "windows")))
opts.Add(EnumVariable("target", "build target", "template_debug",
                      allowed_values=("template_debug", "template_release", "editor")))
opts.Add(BoolVariable("tests", "build the test framework", False))
opts.Add(BoolVariable("sanitize", "ASan/UBSan", False))
opts.Add(BoolVariable("coverage", "code coverage", False))

# SCons' Variables accepts command-line values through an environment. Use a
# normal SCons environment first, then apply the option declarations so bool
# and enum conversion remains SCons-owned.
env = Environment(tools=["default"])
opts.Update(env)
env = Environment(options=opts, tools=["default"])

# Preserve explicit command-line values for the framework even on SCons versions
# that do not propagate Variables values into the final environment.
if "tests" in ARGUMENTS:
    env["tests"] = ARGUMENTS["tests"].lower() in ("1", "true", "yes", "on")

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
# The reusable wiring supplies the generic entry, adapter, and fixture. The
# reference host only declares its output name; suites use convention discovery.
lib = env.SConscript(
    "SConscript",
    variant_dir="build/gdextest",
    duplicate=0,
    exports={"env": env, "gdextest": {
        "enabled": env["tests"],
        "suites": None,
        "out_name": "libgdextest",
    }},
)
if lib:
    Default(lib)

# `scons test` remains useful for SCons-native users. The CLI owns the Godot
# invocation because it can validate the executable and provide consistent flags.
def _run_gdextest(target, source, env):
    command = [sys.executable, str(_tools_dir / "gdextest.py"), "test"]
    return env.Execute(" ".join(command))

Alias("test", lib, _run_gdextest)
