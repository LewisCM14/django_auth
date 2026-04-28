"""Guardrail tests for required view decorator ordering.

Why this matters:
- Throttle should run first so denied requests are short-circuited before cache
    header wrappers are applied in custom view paths.
- A single canonical decorator sequence keeps policy intent readable and
    reduces behavior drift as new endpoints are added.
"""

from __future__ import annotations

import ast
from pathlib import Path


VIEWS_ROOT = Path(__file__).resolve().parents[2] / "api" / "views"

THROTTLE_DECORATORS = {"throttle", "throttle_exempt"}
CACHE_DECORATORS = {"cache_public", "cache_private", "cache_disabled"}
AUTH_DECORATORS = {"authz_public", "authz_authenticated", "authz_roles"}


def _decorator_name(node: ast.expr) -> str | None:
    """Return base decorator function name from a decorator AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _collect_targets(
    module: ast.Module,
) -> list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]:
    """Collect class/function definitions from a parsed module."""
    return [
        node
        for node in ast.walk(module)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]


class TestViewDecoratorOrder:
    """Guardrail tests for required view decorator ordering."""

    def test_view_decorator_ordering_is_enforced(self) -> None:
        """Project views must use throttle -> cache -> auth decorator ordering.

        Enforcing this in one place prevents subtle regressions from decorator
        reordering and makes future maintenance and review predictable.
        """
        violations: list[str] = []

        for path in sorted(VIEWS_ROOT.glob("*.py")):
            if path.name == "__init__.py":
                continue

            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            rel_path = path.relative_to(VIEWS_ROOT.parent.parent)

            for node in _collect_targets(module):
                decorator_names = [
                    name
                    for name in (
                        _decorator_name(decorator) for decorator in node.decorator_list
                    )
                    if name is not None
                ]

                if not decorator_names:
                    continue

                throttle_positions = [
                    idx
                    for idx, name in enumerate(decorator_names)
                    if name in THROTTLE_DECORATORS
                ]
                cache_positions = [
                    idx
                    for idx, name in enumerate(decorator_names)
                    if name in CACHE_DECORATORS
                ]
                auth_positions = [
                    idx
                    for idx, name in enumerate(decorator_names)
                    if name in AUTH_DECORATORS
                ]

                # Ignore helper functions/classes that do not participate in view policy decorators.
                if (
                    not throttle_positions
                    and not cache_positions
                    and not auth_positions
                ):
                    continue

                if (
                    len(throttle_positions) != 1
                    or len(cache_positions) != 1
                    or len(auth_positions) != 1
                ):
                    violations.append(
                        f"{rel_path}:{node.lineno} must include exactly one throttle, cache, and auth decorator"
                    )
                    continue

                throttle_pos = throttle_positions[0]
                cache_pos = cache_positions[0]
                auth_pos = auth_positions[0]

                if not (throttle_pos < cache_pos < auth_pos):
                    violations.append(
                        f"{rel_path}:{node.lineno} has invalid order {decorator_names}; expected throttle -> cache -> auth"
                    )

        assert not violations, "\n".join(
            [
                "View decorator ordering violations found:",
                *violations,
            ]
        )
