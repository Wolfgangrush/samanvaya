"""Loader and canonical-hash helpers for samanvaya declarations.

The loader is intentionally tiny: it reads, it dispatches to the schema
validator and it is done. The credential firewall is deliberately NOT here:
it lives in `samanvaya.credentials` and runs inside `schema.validate`, so a
caller who validates an already-parsed dict gets the same refusal as one who
loads a file.  Writing back is banned — there is no dump, save or
serialise function in this module on purpose.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from samanvaya.schema import canonical_dict, validate
from samanvaya.types import Declaration, DeclarationError



class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys in any mapping it parses."""


def _construct_mapping(loader: yaml.Loader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    """Raise on duplicate keys; otherwise behave like safe_load."""
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DeclarationError(f"duplicate mapping key {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _raise_json_constant(_name: str) -> None:
    """Reject NaN/Infinity when parsing JSON."""
    raise DeclarationError("JSON literal NaN/Infinity is not permitted in a declaration")


def _parse_json(text: str) -> Any:
    """Parse JSON while refusing NaN/Infinity constants."""
    return json.loads(text, parse_constant=_raise_json_constant)


def _parse_yaml(text: str) -> Any:
    """Parse YAML safely with duplicate keys and unsupported tags refused."""
    try:
        loaded = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 — safe by construction
    except yaml.YAMLError as exc:
        raise DeclarationError(f"could not parse YAML: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise DeclarationError(
            f"top-level YAML document must be a mapping, got {type(loaded).__name__}"
        )
    return loaded


def load_text(text: str, fmt: str) -> Declaration:
    """Parse ``text`` in the given format and return a validated declaration."""
    if fmt == "json":
        try:
            obj = _parse_json(text)
        except DeclarationError:
            raise
        except json.JSONDecodeError as exc:
            raise DeclarationError(f"could not parse JSON: {exc}") from exc
    elif fmt == "yaml":
        obj = _parse_yaml(text)
    else:
        raise DeclarationError(f"unsupported format {fmt!r}; expected 'json' or 'yaml'")

    if not isinstance(obj, Mapping):
        raise DeclarationError(
            f"top-level document must be a mapping, got {type(obj).__name__}"
        )

    return validate(obj)


def load(path: Path) -> Declaration:
    """Load a declaration from a file, dispatching on the suffix."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        fmt = "json"
    elif suffix in (".yaml", ".yml"):
        fmt = "yaml"
    else:
        raise DeclarationError(f"unsupported file suffix {suffix!r}; expected .json/.yaml/.yml")
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DeclarationError(f"file not found: {path}") from exc
    return load_text(text, fmt)


def canonical_hash(declaration: Declaration) -> str:
    """Return the SHA-256 hex digest of the canonical declaration form."""
    encoded = json.dumps(
        canonical_dict(declaration),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["canonical_hash", "load", "load_text"]
