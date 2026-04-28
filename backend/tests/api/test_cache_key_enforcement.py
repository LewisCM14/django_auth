"""Guardrail tests for cache key construction conventions."""

from __future__ import annotations

import ast
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[2] / "api"
CACHE_KEY_MODULE = API_ROOT / "cache_keys.py"
KEY_METHODS = {"get", "set", "delete", "get_or_set", "add", "touch", "incr", "decr"}


def _is_literal_key_expression(node: ast.AST) -> bool:
    """Return True when the AST node represents an inline string key literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    return isinstance(node, ast.JoinedStr)


def _cache_method_name(call: ast.Call) -> str | None:
    """Return cache method name for direct ``cache.<method>(...)`` calls."""
    if not isinstance(call.func, ast.Attribute):
        return None

    if not isinstance(call.func.value, ast.Name):
        return None

    if call.func.value.id != "cache":
        return None

    if call.func.attr not in KEY_METHODS:
        return None

    return call.func.attr


class TestCacheKeyEnforcement:
    """Guardrail tests for cache key construction conventions."""

    def test_application_code_does_not_use_literal_cache_keys(self) -> None:
        """Application cache API calls must use api.cache_keys builders for keys."""
        violations: list[str] = []

        for path in sorted(API_ROOT.rglob("*.py")):
            if path == CACHE_KEY_MODULE:
                continue

            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            rel_path = path.relative_to(API_ROOT.parent)

            for node in ast.walk(module):
                if not isinstance(node, ast.Call):
                    continue

                method_name = _cache_method_name(node)
                if method_name is None:
                    continue

                key_node: ast.AST | None = node.args[0] if node.args else None
                if key_node is None:
                    for keyword in node.keywords:
                        if keyword.arg == "key":
                            key_node = keyword.value
                            break

                if key_node is None:
                    continue

                if _is_literal_key_expression(key_node):
                    violations.append(
                        f"{rel_path}:{node.lineno} uses literal key in cache.{method_name}()"
                    )

        assert not violations, "\n".join(
            [
                "Found literal cache keys in application code. Use api.cache_keys builders instead:",
                *violations,
            ]
        )
