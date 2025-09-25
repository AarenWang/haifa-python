import pathlib

import pytest

from haifa_lua.runtime import run_source
from haifa_lua.stdlib import create_default_environment


def test_load_returns_callable() -> None:
    env = create_default_environment()
    result = run_source('local f = load("return 1 + 2"); return f()', env)
    assert result == [3.0]


def test_loadfile_and_dofile(tmp_path: pathlib.Path) -> None:
    script = tmp_path / "script.lua"
    script.write_text("return 7", encoding="utf-8")

    env = create_default_environment()
    env.module_system.set_base_path(tmp_path)  # type: ignore[attr-defined]

    out = run_source('local fn = loadfile("script.lua"); return fn()', env)
    assert out == [7.0]

    do_result = run_source('return dofile("script.lua")', env)
    assert do_result == [7.0]


def test_require_caches_modules(tmp_path: pathlib.Path) -> None:
    module_path = tmp_path / "mod.lua"
    module_path.write_text(
        """
local count = rawget(_G, "load_count") or 0
count = count + 1
_G.load_count = count
return { value = count }
""".strip(),
        encoding="utf-8",
    )

    env = create_default_environment()
    env.module_system.set_base_path(tmp_path)  # type: ignore[attr-defined]

    script = """
local first = require("mod")
local second = require("mod")
return first.value, second.value, load_count
"""
    result = run_source(script, env)
    assert result == [1.0, 1.0, 1.0]


def test_package_sandbox_allows_custom_environment(tmp_path: pathlib.Path) -> None:
    module_path = tmp_path / "secure.lua"
    module_path.write_text("return value", encoding="utf-8")

    env = create_default_environment()
    env.module_system.set_base_path(tmp_path)  # type: ignore[attr-defined]

    script = """
local sandbox = { value = 42 }
package.sandbox("secure", sandbox, false)
return require("secure")
"""
    result = run_source(script, env)
    assert result == [42.0]


def test_require_missing_module_reports_error(tmp_path: pathlib.Path) -> None:
    env = create_default_environment()
    env.module_system.set_base_path(tmp_path)  # type: ignore[attr-defined]

    with pytest.raises(Exception) as exc:
        run_source('return require("missing")', env)
    assert "module 'missing' not found" in str(exc.value)
