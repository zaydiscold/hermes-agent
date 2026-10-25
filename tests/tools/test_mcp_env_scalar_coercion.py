"""Regression tests for MCP stdio env coercion.

An MCP server's ``env`` block in config.yaml is YAML, so an unquoted value like
``FOO: 1`` parses as ``int`` and ``FOO: true`` as ``bool``. The MCP SDK's
``StdioServerParameters`` declares ``env: dict[str, str]``, so any non-string
value makes the SDK raise a validation error and the whole server never starts:

    env.ROBINHOOD_ALLOW_LIVE_WRITE
      Input should be a valid string [type=string_type, input_value=1, input_type=int]

The failure mode is nasty because the config looks correct and the error names a
pydantic type rather than the config file. ``_coerce_env_value`` renders scalars
as the string a subprocess expects so natural YAML keeps working.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[2] / "tools" / "mcp_tool_config.py"


def _load_coercer():
    """Import ``_coerce_env_value`` without pulling in the module's heavy deps."""
    try:  # preferred: real import when the environment supports it
        from tools.mcp_tool_config import _coerce_env_value  # type: ignore

        return _coerce_env_value
    except Exception:
        pass
    # fallback: compile just the function out of the source
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_coerce_env_value"
    )
    namespace: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<coerce>", "exec"), namespace)
    return namespace["_coerce_env_value"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        # the exact value that broke robinhood: unquoted YAML int
        (1, "1"),
        (0, "0"),
        # already correct
        ("1", "1"),
        ("abc", "abc"),
        ("", ""),
        # YAML bool -> shell convention, not Python "True"/"False"
        (True, "1"),
        (False, "0"),
        # YAML float
        (1.5, "1.5"),
        (2.0, "2.0"),
        # negatives and large ints
        (-1, "-1"),
        (1245, "1245"),
    ],
)
def test_coerce_env_value_returns_str(raw, expected):
    coerce = _load_coercer()
    got = coerce(raw)
    assert got == expected
    assert isinstance(got, str), f"env value must be str for StdioServerParameters, got {type(got)}"


def test_all_outputs_are_strings():
    """Whatever the YAML type, the result must satisfy dict[str, str]."""
    coerce = _load_coercer()
    for value in (1, 0, True, False, 1.5, "x", -3):
        assert type(coerce(value)) is str


def test_bool_is_shell_convention_not_python_repr():
    """Gates are compared against "1"; ``str(True)`` would yield "True" and fail the check."""
    coerce = _load_coercer()
    assert coerce(True) == "1"
    assert coerce(False) == "0"
    assert coerce(True) != str(True)
