"""Compiler-family detection for the gdextest SConscript.

Lives in a plain module (not inline in the SConscript) so the classification
is unit-testable without an SCons environment. `is_msvc` accepts anything
dict-like with `.get` — a real SCons `Environment` or a plain dict.
"""

import os

# MSVC front-end program names, compared after basename + extension strip.
# `clang` (the GNU front end) is deliberately absent: it starts with "cl" but
# takes GCC-style flags, which is exactly the prefix-match trap this module
# exists to avoid.
_MSVC_PROGRAM_NAMES = ("cl", "clang-cl")


def _program_name(command) -> str:
    """Normalize a CC/CXX value to a comparable program name.

    Takes the last whitespace-separated token (`ccache clang` -> `clang`),
    strips directories (`C:/.../cl.exe` -> `cl.exe`), lowercases, and removes
    a `.exe` suffix (`cl.exe` -> `cl`).
    """
    tokens = str(command or "").split()
    if not tokens:
        return ""
    name = os.path.basename(tokens[-1]).lower()
    return name[:-4] if name.endswith(".exe") else name


def is_msvc(env) -> bool:
    """True only for the MSVC front end: `cl`, `clang-cl`, godot-cpp's
    `is_msvc` env flag, or the SCons `msvc` tool.

    GCC, g++, clang, and clang++ return False — including on Windows (MinGW,
    GNU-front-end clang) — so the caller picks flags from the compiler
    actually in use, never from `PLATFORM` alone.
    """
    # An explicitly configured CC/CXX is the strongest signal: it overrides
    # stale tool state (e.g. the msvc tool applied before the user switched
    # to MinGW).
    for variable in ("CC", "CXX"):
        if _program_name(env.get(variable)) in _MSVC_PROGRAM_NAMES:
            return True
    if env.get("is_msvc"):
        return True
    return any(str(tool).lower() == "msvc" for tool in (env.get("TOOLS") or []))
