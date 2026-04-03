"""Cache key builder utilities.

Centralizes cache-key composition so application code does not construct
ad-hoc string keys inline. This keeps key patterns consistent and makes
invalidation predictable as the codebase grows.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _normalize_component(component: str) -> str:
    """Normalize a key component to a deterministic, safe token."""
    normalized = component.strip().lower().replace(" ", "_")
    return normalized.replace(":", "_")


def _stable_hash(payload: Mapping[str, Any]) -> str:
    """Return a short deterministic hash for arbitrary mapping payloads."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return digest[:12]


def adapter_key(source: str, resource: str, identifier: str) -> str:
    """Build an adapter-layer cache key.

    Pattern: ``adapter:{source}:{resource}:{identifier}``
    """
    return ":".join(
        (
            "adapter",
            _normalize_component(source),
            _normalize_component(resource),
            _normalize_component(identifier),
        )
    )


def view_key(view_name: str, query_params: Mapping[str, Any]) -> str:
    """Build a view-layer cache key.

    Pattern: ``view:{view_name}:{query_hash}``
    """
    return ":".join(
        ("view", _normalize_component(view_name), _stable_hash(query_params))
    )


def service_key(domain: str, operation: str, params: Mapping[str, Any]) -> str:
    """Build a service-layer cache key.

    Pattern: ``service:{domain}:{operation}:{params_hash}``
    """
    return ":".join(
        (
            "service",
            _normalize_component(domain),
            _normalize_component(operation),
            _stable_hash(params),
        )
    )
