"""Guardrail tests for the shared API view base class."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from api.views.base import BaseAPIView


VIEWS_ROOT = Path(__file__).resolve().parents[2] / "api" / "views"


def _iter_project_view_classes() -> list[tuple[str, type[object]]]:
    """Return all concrete view classes defined under api.views."""

    classes: list[tuple[str, type[object]]] = []
    for path in sorted(VIEWS_ROOT.glob("*.py")):
        if path.name in {"__init__.py", "base.py"}:
            continue

        module = importlib.import_module(f"api.views.{path.stem}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__ and name != "BaseAPIView":
                classes.append((f"{path.name}:{name}", obj))

    return classes


def test_project_views_inherit_from_base_apiview() -> None:
    """Every concrete project view should inherit from BaseAPIView."""

    violations = [
        label
        for label, view_class in _iter_project_view_classes()
        if not issubclass(view_class, BaseAPIView)
    ]

    assert not violations, "\n".join(
        [
            "Views must inherit from BaseAPIView:",
            *violations,
        ]
    )


def test_non_docs_views_define_serializer_class() -> None:
    """Non-wrapper views must declare serializer metadata for spectacular."""

    violations = []
    for label, view_class in _iter_project_view_classes():
        if label.startswith("docs.py:"):
            continue

        if getattr(view_class, "serializer_class", None) is None:
            violations.append(label)

    assert not violations, "\n".join(
        [
            "Views must define serializer_class unless they are schema/docs wrappers:",
            *violations,
        ]
    )
