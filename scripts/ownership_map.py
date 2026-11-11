"""Load, validate and resolve the lane ownership map (`.claude/ownership.json`).

This module is the single home of the map's meaning: strict loading, validation, path resolution, lane-from-branch and
the "may this lane change this path" decision. `scripts/check_ownership.py` uses it.

Loading fails closed: every violation raises `MapError` with the offending location. The declared rules in the map
(`patterns.precedence`, `patterns.unmapped`) must be exactly the ones implemented here.

Patterns are normalized repository-relative paths: an exact file path, a directory prefix ending in `/`, or `*`
(any file directly at the repository root). A pattern has exactly one home across all lanes' `paths` and `co_owned`.

Resolution of a path, in order:

1. an exact pattern;
2. the longest directory prefix that contains the path;
3. `*`, for a file directly at the repository root;
4. otherwise the path is unmapped.

The owner is a lane, or a `co_owned` entry (its keys take part in the same precedence).
A lane is read from a branch name by its prefix: the branch must start with exactly one lane prefix.

Lane L may change a path when:

- the path's owner is L; or
- the path's owner is a lane that L directly includes (not transitively, and not that lane's co-owned memberships); or
- the path is co-owned and lists L.

A path of kind `control` may be changed only by the `meta` lane, whatever the rules above say. Unmapped paths are never
allowed.

The module uses only the standard library and runs on Python 3.9+, so it does not need the project environment.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_VERSION = 1
MODES = ("single-team", "multi-lane")
PRECEDENCE = ["exact", "longest-prefix", "root-wildcard"]
UNMAPPED_RULE = "fail-closed"
ROOT_WILDCARD = "*"
CONTROL_KIND = "control"
META_LANE = "meta"

TOP_LEVEL_REQUIRED = ("version", "mode", "patterns", "kinds", "lanes", "co_owned", "roles", "closeout_kinds")
TOP_LEVEL_OPTIONAL = ("about",)
PATTERNS_REQUIRED = ("precedence", "unmapped")
PATTERNS_OPTIONAL = ("syntax", "co_owned", "includes")
LANE_REQUIRED = ("prefix", "paths")
LANE_OPTIONAL = ("includes",)
CO_OWNED_REQUIRED = ("kind", "lanes")


class MapError(Exception):
    """The map is unreadable or violates a rule; nothing may rely on it."""


@dataclass(frozen=True)
class Lane:
    name: str
    prefix: str
    includes: tuple[str, ...]
    paths: dict[str, str]


@dataclass(frozen=True)
class Resolution:
    """The owner and kind of a mapped path. `lane` is set for a lane's own path, `co_lanes` for a co-owned one."""

    pattern: str
    kind: str
    lane: str | None
    co_lanes: tuple[str, ...]

    @property
    def owner(self) -> str:
        return self.lane if self.lane is not None else "co-owned by " + ", ".join(self.co_lanes)


@dataclass(frozen=True)
class OwnershipMap:
    mode: str
    kinds: tuple[str, ...]
    lanes: dict[str, Lane]
    co_owned: dict[str, Resolution]
    roles: dict[str, tuple[str, ...]]
    closeout_kinds: tuple[str, ...]
    entries: dict[str, Resolution]

    def resolve(self, path: str) -> Resolution | None:
        """The owner and kind of file `path`, or None when unmapped (also when not a normalized file path)."""
        if path.endswith("/") or not _is_normalized(path):
            return None
        if path != ROOT_WILDCARD and path in self.entries:
            return self.entries[path]
        prefixes = [pattern for pattern in self.entries if pattern.endswith("/") and path.startswith(pattern)]
        if prefixes:
            return self.entries[max(prefixes, key=len)]
        if "/" not in path and ROOT_WILDCARD in self.entries:
            return self.entries[ROOT_WILDCARD]
        return None

    def lane_for_branch(self, branch: str) -> str | None:
        """The lane whose prefix starts `branch`, or None (`master` and any other name are unknown)."""
        matches = [lane.name for lane in self.lanes.values() if branch.startswith(lane.prefix)]
        return matches[0] if len(matches) == 1 else None

    def denial(self, lane: str, path: str) -> str | None:
        """Why `lane` may not change `path`, or None when it may."""
        resolution = self.resolve(path)
        if resolution is None:
            return "unmapped"
        if resolution.kind == CONTROL_KIND and lane != META_LANE:
            return f"control path, reserved for the {META_LANE} lane"
        if not self._owns(lane, resolution):
            return f"outside lane {lane} (owner: {resolution.owner})"
        return None

    def may_change(self, lane: str, path: str) -> bool:
        return self.denial(lane, path) is None

    def _owns(self, lane: str, resolution: Resolution) -> bool:
        if resolution.lane is None:
            return lane in resolution.co_lanes
        if lane == resolution.lane:
            return True
        known = self.lanes.get(lane)
        return known is not None and resolution.lane in known.includes


def load_map(path: Path) -> OwnershipMap:
    """Read and validate the map at `path`."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise MapError(f"cannot read {path}: {error}") from error
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, RecursionError) as error:
        raise MapError(f"{path} is not valid JSON: {error}") from error
    return parse_map(data)


def parse_map(data: Any) -> OwnershipMap:
    """Validate the decoded map and build the resolver, raising `MapError` on the first violation."""
    top = _object(data, "map", TOP_LEVEL_REQUIRED, TOP_LEVEL_OPTIONAL)
    if "about" in top:
        _text(top["about"], "about")
    version = top["version"]
    if type(version) is not int or version != SUPPORTED_VERSION:
        raise MapError(f"version must be {SUPPORTED_VERSION}")
    mode = top["mode"]
    if mode not in MODES:
        raise MapError("mode must be one of {}".format(", ".join(MODES)))
    _validate_patterns(top["patterns"])
    kinds = _unique_texts(top["kinds"], "kinds")
    lanes = _validate_lanes(top["lanes"], kinds)
    co_owned = _validate_co_owned(top["co_owned"], kinds, lanes)
    entries = _build_entries(lanes, co_owned)
    return OwnershipMap(
        mode=mode,
        kinds=kinds,
        lanes=lanes,
        co_owned=co_owned,
        roles=_validate_roles(top["roles"], kinds),
        closeout_kinds=_validate_closeout_kinds(top["closeout_kinds"], kinds),
        entries=entries,
    )


def _no_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _object(value: Any, where: str, required: Sequence[str], optional: Sequence[str] = ()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MapError(f"{where} must be an object")
    unknown = sorted(set(value) - set(required) - set(optional))
    if unknown:
        raise MapError("{}: unknown key(s): {}".format(where, ", ".join(unknown)))
    missing = [key for key in required if key not in value]
    if missing:
        raise MapError("{}: missing key(s): {}".format(where, ", ".join(missing)))
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise MapError(f"{where} must be a non-empty string")
    return value


def _texts(value: Any, where: str) -> list[str]:
    if not isinstance(value, list):
        raise MapError(f"{where} must be a list")
    return [_text(item, f"{where} entry") for item in value]


def _unique_texts(value: Any, where: str) -> tuple[str, ...]:
    items = _texts(value, where)
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise MapError("{} has duplicate(s): {}".format(where, ", ".join(duplicates)))
    return tuple(items)


def _is_normalized(path: str) -> bool:
    body = path[:-1] if path.endswith("/") else path
    if not body or "\\" in path or "\x00" in path:
        return False
    return all(segment not in ("", ".", "..") for segment in body.split("/"))


def _validate_pattern(pattern: Any, where: str) -> str:
    text = _text(pattern, where)
    if text == ROOT_WILDCARD:
        return text
    if "*" in text:
        raise MapError(f"{where}: pattern {text!r} may use '*' only as the whole pattern")
    if not _is_normalized(text):
        raise MapError(f"{where}: pattern {text!r} is not a normalized repository-relative path")
    return text


def _validate_patterns(value: Any) -> None:
    patterns = _object(value, "patterns", PATTERNS_REQUIRED, PATTERNS_OPTIONAL)
    for key in PATTERNS_OPTIONAL:
        if key in patterns:
            _text(patterns[key], f"patterns.{key}")
    if patterns["precedence"] != PRECEDENCE:
        raise MapError(f"patterns.precedence must be {PRECEDENCE}")
    if patterns["unmapped"] != UNMAPPED_RULE:
        raise MapError(f"patterns.unmapped must be {UNMAPPED_RULE!r}")


def _validate_lanes(value: Any, kinds: tuple[str, ...]) -> dict[str, Lane]:
    if not isinstance(value, dict) or not value:
        raise MapError("lanes must be a non-empty object")
    raw: dict[str, dict[str, Any]] = {}
    for name, body in value.items():
        _text(name, "lane name")
        raw[name] = _object(body, f"lanes.{name}", LANE_REQUIRED, LANE_OPTIONAL)
    prefixes = _lane_prefixes(raw)
    lanes: dict[str, Lane] = {}
    for name, body in raw.items():
        where = f"lanes.{name}"
        includes = _unique_texts(body.get("includes", []), where + ".includes")
        for included in includes:
            if included == name or included not in raw:
                raise MapError(f"{where}.includes names {included!r}, which is not another lane")
        lanes[name] = Lane(name, prefixes[name], includes, _validate_lane_paths(body["paths"], where + ".paths", kinds))
    return lanes


def _lane_prefixes(raw: dict[str, dict[str, Any]]) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for name, body in raw.items():
        prefix = _text(body["prefix"], f"lanes.{name}.prefix")
        if not prefix.endswith("/") or not _is_normalized(prefix):
            raise MapError(f"lanes.{name}.prefix {prefix!r} must be a normalized name ending in '/'")
        prefixes[name] = prefix
    for name, prefix in prefixes.items():
        for other, other_prefix in prefixes.items():
            if name != other and other_prefix.startswith(prefix):
                raise MapError(f"lane prefix {prefix!r} ({name}) is a prefix of {other_prefix!r} ({other})")
    return prefixes


def _validate_lane_paths(value: Any, where: str, kinds: tuple[str, ...]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise MapError(f"{where} must be an object")
    paths: dict[str, str] = {}
    for pattern, kind in value.items():
        _validate_pattern(pattern, where)
        paths[pattern] = _declared_kind(kind, f"{where}[{pattern!r}]", kinds)
    return paths


def _declared_kind(kind: Any, where: str, kinds: Sequence[str]) -> str:
    text = _text(kind, where + " kind")
    if text not in kinds:
        raise MapError(f"{where} uses undeclared kind {text!r}")
    return text


def _validate_co_owned(value: Any, kinds: tuple[str, ...], lanes: dict[str, Lane]) -> dict[str, Resolution]:
    if not isinstance(value, dict):
        raise MapError("co_owned must be an object")
    co_owned: dict[str, Resolution] = {}
    for pattern, body in value.items():
        where = f"co_owned[{pattern!r}]"
        _validate_pattern(pattern, "co_owned")
        entry = _object(body, where, CO_OWNED_REQUIRED)
        kind = _declared_kind(entry["kind"], where, kinds)
        owners = _unique_texts(entry["lanes"], where + ".lanes")
        if len(owners) < 2:
            raise MapError(f"{where} must list at least two lanes")
        unknown = [owner for owner in owners if owner not in lanes]
        if unknown:
            raise MapError("{} names unknown lane(s): {}".format(where, ", ".join(unknown)))
        co_owned[pattern] = Resolution(pattern, kind, None, owners)
    return co_owned


def _build_entries(lanes: dict[str, Lane], co_owned: dict[str, Resolution]) -> dict[str, Resolution]:
    entries: dict[str, Resolution] = {}
    for lane in lanes.values():
        for pattern, kind in lane.paths.items():
            _claim(entries, pattern, Resolution(pattern, kind, lane.name, ()))
    for pattern, resolution in co_owned.items():
        _claim(entries, pattern, resolution)
    return entries


def _claim(entries: dict[str, Resolution], pattern: str, resolution: Resolution) -> None:
    if pattern in entries:
        raise MapError(f"pattern {pattern!r} has more than one home ({entries[pattern].owner} and {resolution.owner})")
    entries[pattern] = resolution


def _validate_roles(value: Any, kinds: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise MapError("roles must be an object")
    roles: dict[str, tuple[str, ...]] = {}
    for role, role_kinds in value.items():
        _text(role, "role name")
        listed = _unique_texts(role_kinds, f"roles.{role}")
        for kind in listed:
            _declared_kind(kind, f"roles.{role}", kinds)
        roles[role] = tuple(listed)
    return roles


def _validate_closeout_kinds(value: Any, kinds: tuple[str, ...]) -> tuple[str, ...]:
    listed = _unique_texts(value, "closeout_kinds")
    for kind in listed:
        _declared_kind(kind, "closeout_kinds", kinds)
    return tuple(listed)
