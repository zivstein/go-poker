"""`scripts/ownership_map.py` loads the ownership map strictly and resolves paths, lanes and permissions from it."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

type Script = Callable[[str], ModuleType]
type Mutation = Callable[[dict[str, Any]], None]

REAL_MAP = Path(__file__).resolve().parents[2] / ".claude" / "ownership.json"


def valid_map() -> dict[str, Any]:
    return {
        "about": "test map",
        "version": 1,
        "mode": "multi-lane",
        "patterns": {
            "syntax": "syntax text",
            "precedence": ["exact", "longest-prefix", "root-wildcard"],
            "co_owned": "co-owned text",
            "includes": "includes text",
            "unmapped": "fail-closed",
        },
        "kinds": ["production", "tests", "records", "architecture", "tooling", "control"],
        "lanes": {
            "core": {
                "prefix": "core/",
                "paths": {
                    "src/core/": "production",
                    "src/core/special/": "tests",
                    "src/core/special/exact.py": "records",
                    "tests/core/": "tests",
                },
            },
            "org": {"prefix": "org/", "paths": {"docs/records/": "records"}},
            "meta": {
                "prefix": "meta/",
                "includes": ["org"],
                "paths": {"scripts/": "tooling", ".claude/ownership.json": "control", "*": "control"},
            },
        },
        "co_owned": {
            "docs/ARCH.md": {"kind": "architecture", "lanes": ["core", "org"]},
            "src/core/shared/": {"kind": "production", "lanes": ["core", "org"]},
        },
        "roles": {"engineer": ["production", "tests"], "reviewer": []},
        "closeout_kinds": ["architecture"],
    }


@pytest.fixture
def omap(script: Script) -> ModuleType:
    """One loaded `ownership_map` module per test, so its `MapError` is the one the test catches."""
    return script("ownership_map")


def build(omap: ModuleType, mutate: Mutation | None = None) -> Any:
    data = copy.deepcopy(valid_map())
    if mutate is not None:
        mutate(data)
    return omap.parse_map(data)


def drop(*keys: str) -> Mutation:
    def apply(data: dict[str, Any]) -> None:
        target = data
        for key in keys[:-1]:
            target = target[key]
        del target[keys[-1]]

    return apply


def put(value: Any, *keys: str) -> Mutation:
    def apply(data: dict[str, Any]) -> None:
        target = data
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return apply


def lane_path(pattern: str, kind: str = "production") -> Mutation:
    return put(kind, "lanes", "core", "paths", pattern)


INVALID_MAPS: list[tuple[str, Mutation, str]] = [
    ("unknown top-level key", put(1, "extra"), "unknown key(s): extra"),
    ("unknown patterns key", put("x", "patterns", "extra"), "patterns: unknown key(s): extra"),
    ("unknown lane key", put("x", "lanes", "core", "extra"), "lanes.core: unknown key(s): extra"),
    ("unknown co_owned key", put("x", "co_owned", "docs/ARCH.md", "extra"), "unknown key(s): extra"),
    ("missing version", drop("version"), "missing key(s): version"),
    ("missing co_owned", drop("co_owned"), "missing key(s): co_owned"),
    ("missing lane paths", drop("lanes", "core", "paths"), "missing key(s): paths"),
    ("version 2", put(2, "version"), "version must be 1"),
    ("version true", put(True, "version"), "version must be 1"),
    ("version string", put("1", "version"), "version must be 1"),
    ("unknown mode", put("some-team", "mode"), "mode must be one of"),
    ("about not text", put(5, "about"), "about must be a non-empty string"),
    ("syntax not text", put(["x"], "patterns", "syntax"), "patterns.syntax must be a non-empty string"),
    (
        "different precedence",
        put(["exact", "root-wildcard", "longest-prefix"], "patterns", "precedence"),
        "patterns.precedence must be",
    ),
    ("unmapped not fail-closed", put("allow", "patterns", "unmapped"), "patterns.unmapped must be"),
    ("duplicate kinds", put(["tests", "tests"], "kinds"), "kinds has duplicate(s): tests"),
    ("no lanes", put({}, "lanes"), "lanes must be a non-empty object"),
    ("prefix without slash", put("core", "lanes", "core", "prefix"), "must be a normalized name ending in '/'"),
    ("prefix with dot segment", put("./core/", "lanes", "core", "prefix"), "must be a normalized name ending in '/'"),
    ("prefix leading slash", put("/core/", "lanes", "core", "prefix"), "must be a normalized name ending in '/'"),
    ("duplicate prefix", put("core/", "lanes", "org", "prefix"), "is a prefix of"),
    ("prefix of another prefix", put("core/sub/", "lanes", "org", "prefix"), "is a prefix of"),
    ("leading slash pattern", lane_path("/src/x.py"), "not a normalized"),
    ("dotdot pattern", lane_path("src/../x.py"), "not a normalized"),
    ("dot pattern", lane_path("./x.py"), "not a normalized"),
    ("empty segment pattern", lane_path("src//x.py"), "not a normalized"),
    ("backslash pattern", lane_path("src\\x.py"), "not a normalized"),
    ("empty pattern", lane_path(""), "must be a non-empty string"),
    ("embedded wildcard", lane_path("docs/*"), "only as the whole pattern"),
    ("glob wildcard", lane_path("src/*.py"), "only as the whole pattern"),
    ("undeclared lane kind", lane_path("src/x.py", "mystery"), "undeclared kind 'mystery'"),
    ("lane kind not text", lane_path("src/x.py", 5), "must be a non-empty string"),
    (
        "undeclared co_owned kind",
        put("mystery", "co_owned", "docs/ARCH.md", "kind"),
        "undeclared kind 'mystery'",
    ),
    ("undeclared role kind", put(["mystery"], "roles", "engineer"), "undeclared kind 'mystery'"),
    ("closeout kind not declared", put(["mystery"], "closeout_kinds"), "undeclared kind 'mystery'"),
    ("pattern in two lanes", put("production", "lanes", "org", "paths", "src/core/"), "more than one home"),
    ("pattern in a lane and co_owned", lane_path("docs/ARCH.md"), "more than one home"),
    ("includes unknown lane", put(["ghost"], "lanes", "meta", "includes"), "not another lane"),
    ("includes itself", put(["meta"], "lanes", "meta", "includes"), "not another lane"),
    ("co_owned with one lane", put(["core"], "co_owned", "docs/ARCH.md", "lanes"), "at least two lanes"),
    ("co_owned repeats a lane", put(["core", "core"], "co_owned", "docs/ARCH.md", "lanes"), "duplicate(s): core"),
    ("co_owned unknown lane", put(["core", "ghost"], "co_owned", "docs/ARCH.md", "lanes"), "unknown lane(s): ghost"),
    (
        "co_owned bad pattern",
        put({"kind": "tests", "lanes": ["core", "org"]}, "co_owned", "../x.md"),
        "not a normalized",
    ),
    ("roles not an object", put([], "roles"), "roles must be an object"),
    ("lanes is a list", put([], "lanes"), "lanes must be a non-empty object"),
    ("lane body is a list", put([], "lanes", "core"), "lanes.core must be an object"),
    ("lane paths is a list", put([], "lanes", "core", "paths"), "must be an object"),
    ("lane includes is a string", put("org", "lanes", "meta", "includes"), "must be a list"),
    ("lane prefix empty", put("", "lanes", "core", "prefix"), "must be a non-empty string"),
    ("lane prefix is a bare slash", put("/", "lanes", "core", "prefix"), "must be a normalized name ending in '/'"),
    ("lane prefix with an empty segment", put("core//", "lanes", "core", "prefix"), "must be a normalized name"),
    ("co_owned is a list", put([], "co_owned"), "co_owned must be an object"),
    ("co_owned body is a list", put([], "co_owned", "docs/ARCH.md"), "must be an object"),
    ("co_owned lanes is a string", put("core", "co_owned", "docs/ARCH.md", "lanes"), "must be a list"),
    ("co_owned kind is an object", put({}, "co_owned", "docs/ARCH.md", "kind"), "must be a non-empty string"),
    ("co_owned kind missing", drop("co_owned", "docs/ARCH.md", "kind"), "missing key(s): kind"),
    (
        "co_owned wildcard glob",
        put({"kind": "tests", "lanes": ["core", "org"]}, "co_owned", "docs/*.md"),
        "only as the whole",
    ),
    ("roles value is a string", put("tests", "roles", "engineer"), "must be a list"),
    ("closeout_kinds is a string", put("architecture", "closeout_kinds"), "must be a list"),
    ("kinds is a string", put("tests", "kinds"), "must be a list"),
    ("kinds entry is empty", put(["tests", ""], "kinds"), "must be a non-empty string"),
    ("version is a float", put(1.0, "version"), "version must be 1"),
    ("version is null", put(None, "version"), "version must be 1"),
    ("mode in another case", put("Multi-Lane", "mode"), "mode must be one of"),
    ("mode with whitespace", put("multi-lane ", "mode"), "mode must be one of"),
    ("mode is a list", put(["multi-lane"], "mode"), "mode must be one of"),
    ("patterns is a list", put([], "patterns"), "patterns must be an object"),
    ("precedence is a string", put("exact", "patterns", "precedence"), "patterns.precedence must be"),
    ("unmapped is null", put(None, "patterns", "unmapped"), "patterns.unmapped must be"),
    ("pattern dot segment inside", lane_path("src/./x.py"), "not a normalized"),
    ("pattern with NUL", lane_path("src/\x00x.py"), "not a normalized"),
    ("pattern only a slash", lane_path("/"), "not a normalized"),
    ("role repeats a kind", put(["tests", "tests"], "roles", "engineer"), "roles.engineer has duplicate(s): tests"),
    (
        "closeout_kinds repeats a kind",
        put(["architecture", "architecture"], "closeout_kinds"),
        "closeout_kinds has duplicate(s): architecture",
    ),
]


@pytest.mark.parametrize(("mutation", "message"), [case[1:] for case in INVALID_MAPS], ids=[c[0] for c in INVALID_MAPS])
def test_a_map_that_breaks_a_rule_is_rejected(omap: ModuleType, mutation: Mutation, message: str) -> None:
    with pytest.raises(omap.MapError, match=r".*" + message.replace("(", r"\(").replace(")", r"\)")):
        build(omap, mutation)


def test_the_valid_fixture_map_is_accepted(omap: ModuleType) -> None:
    assert build(omap).mode == "multi-lane"


@pytest.mark.parametrize("mode", ["single-team", "multi-lane"])
def test_both_modes_are_accepted(omap: ModuleType, mode: str) -> None:
    assert build(omap, put(mode, "mode")).mode == mode


def write_map(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "ownership.json"
    target.write_text(text)
    return target


def test_invalid_json_is_rejected(omap: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(omap.MapError, match="not valid JSON"):
        omap.load_map(write_map(tmp_path, "{"))


def test_a_missing_map_is_rejected(omap: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(omap.MapError, match="cannot read"):
        omap.load_map(tmp_path / "absent.json")


def test_a_map_that_is_not_an_object_is_rejected(omap: ModuleType) -> None:
    with pytest.raises(omap.MapError, match="map must be an object"):
        omap.parse_map([])


def test_the_committed_map_loads_and_validates(omap: ModuleType) -> None:
    ownership = omap.load_map(REAL_MAP)

    assert ownership.mode in {"single-team", "multi-lane"}
    assert set(ownership.lanes) == {"core", "backend", "design", "org", "meta"}
    assert ownership.lane_for_branch("meta/ownership-map") == "meta"


def test_the_committed_map_gives_meta_org_paths_but_not_the_co_owned_architecture(omap: ModuleType) -> None:
    ownership = omap.load_map(REAL_MAP)

    assert ownership.may_change("meta", "docs/ROADMAP.md")
    assert not ownership.may_change("meta", "docs/ARCHITECTURE.md")
    assert ownership.may_change("core", "docs/ARCHITECTURE.md")
    assert ownership.may_change("org", "docs/ARCHITECTURE.md")
    assert not ownership.may_change("core", ".claude/ownership.json")
    assert ownership.may_change("meta", ".claude/ownership.json")


@pytest.mark.parametrize(
    ("path", "pattern", "kind"),
    [
        ("src/core/special/exact.py", "src/core/special/exact.py", "records"),
        ("src/core/special/other.py", "src/core/special/", "tests"),
        ("src/core/special/deep/more.py", "src/core/special/", "tests"),
        ("src/core/plain.py", "src/core/", "production"),
        ("README.md", "*", "control"),
        ("docs/ARCH.md", "docs/ARCH.md", "architecture"),
        ("src/core/shared/x.py", "src/core/shared/", "production"),
        ("scripts/tool.py", "scripts/", "tooling"),
    ],
)
def test_a_path_resolves_by_exact_then_longest_prefix_then_root_wildcard(
    omap: ModuleType, path: str, pattern: str, kind: str
) -> None:
    resolution = build(omap).resolve(path)

    assert resolution is not None
    assert (resolution.pattern, resolution.kind) == (pattern, kind)


@pytest.mark.parametrize(
    "path",
    [
        "src/unrelated.py",
        "docs/other/deep.md",
        "src/corex/file.py",
        "src/core",
        "tests/core",
        "src/core/../core/a.py",
        "./src/core/a.py",
        "/src/core/a.py",
        "src//core/a.py",
        "src\\core\\a.py",
        "",
        "docs/records/",
    ],
)
def test_a_nested_or_malformed_path_outside_every_pattern_is_unmapped(omap: ModuleType, path: str) -> None:
    assert build(omap).resolve(path) is None


def test_the_root_wildcard_matches_only_files_directly_at_the_root(omap: ModuleType) -> None:
    ownership = build(omap)

    assert ownership.resolve("Makefile") is not None
    assert ownership.resolve("sub/Makefile") is None
    assert ownership.resolve("*") is not None


def test_a_co_owned_key_takes_part_in_the_same_precedence(omap: ModuleType) -> None:
    ownership = build(omap)

    shared = ownership.resolve("src/core/shared/x.py")
    arch = ownership.resolve("docs/ARCH.md")

    assert shared is not None and shared.lane is None and shared.co_lanes == ("core", "org")
    assert arch is not None and arch.lane is None and arch.co_lanes == ("core", "org")
    assert ownership.resolve("src/core/other.py").lane == "core"


@pytest.mark.parametrize(
    ("lane", "path", "allowed"),
    [
        ("core", "src/core/a.py", True),
        ("core", "docs/records/r.md", False),
        ("core", "scripts/tool.py", False),
        ("org", "docs/records/r.md", True),
        ("org", "src/core/a.py", False),
        ("meta", "scripts/tool.py", True),
        ("meta", "docs/records/r.md", True),
        ("meta", "src/core/a.py", False),
        ("core", "docs/ARCH.md", True),
        ("org", "docs/ARCH.md", True),
        ("meta", "docs/ARCH.md", False),
        ("meta", "src/core/shared/x.py", False),
        ("core", "src/unmapped/x.py", False),
        ("meta", "src/unmapped/x.py", False),
        ("meta", "README.md", True),
        ("core", "README.md", False),
        ("core", ".claude/ownership.json", False),
        ("ghost", "src/core/a.py", False),
    ],
)
def test_a_lane_may_change_its_own_included_and_co_owned_paths_only(
    omap: ModuleType, lane: str, path: str, allowed: bool
) -> None:
    assert build(omap).may_change(lane, path) is allowed


def test_includes_are_direct_only(omap: ModuleType) -> None:
    def chain(data: dict[str, Any]) -> None:
        data["lanes"]["core"]["includes"] = ["org"]
        data["lanes"]["meta"]["includes"] = ["core"]

    ownership = build(omap, chain)

    assert ownership.may_change("meta", "src/core/a.py")
    assert not ownership.may_change("meta", "docs/records/r.md")
    assert ownership.may_change("core", "docs/records/r.md")
    assert not ownership.may_change("org", "src/core/a.py")


def test_a_control_path_is_for_the_meta_lane_even_when_the_map_gives_it_to_another_lane(omap: ModuleType) -> None:
    ownership = build(omap, lane_path("src/core/guard.py", "control"))

    assert not ownership.may_change("core", "src/core/guard.py")
    assert "control path" in ownership.denial("core", "src/core/guard.py")
    assert ownership.may_change("meta", ".claude/ownership.json")


def test_denial_explains_unmapped_and_foreign_paths(omap: ModuleType) -> None:
    ownership = build(omap)

    assert ownership.denial("core", "src/unmapped/x.py") == "unmapped"
    assert ownership.denial("core", "docs/records/r.md") == "outside lane core (owner: org)"
    assert ownership.denial("meta", "docs/ARCH.md") == "outside lane meta (owner: co-owned by core, org)"
    assert ownership.denial("core", "src/core/a.py") is None


@pytest.mark.parametrize(
    ("branch", "lane"),
    [
        ("core/feature", "core"),
        ("meta/ownership-map", "meta"),
        ("org/records", "org"),
        ("master", None),
        ("main", None),
        ("feature/x", None),
        ("core", None),
        ("corefeature", None),
        ("Core/feature", None),
        ("", None),
        ("refs/heads/core/x", None),
        ("core/", "core"),
        ("core/meta/x", "core"),
        ("meta/core/x", "meta"),
        ("core/core/core", "core"),
        (" core/x", None),
        ("core/x ", "core"),
        ("\u0441ore/x", None),
        ("core\\x", None),
        ("CORE/x", None),
        ("core:x", None),
        ("/core/x", None),
        ("heads/core/x", None),
        ("c", None),
        ("-", None),
    ],
)
def test_the_lane_comes_from_the_branch_prefix(omap: ModuleType, branch: str, lane: str | None) -> None:
    assert build(omap).lane_for_branch(branch) == lane


def test_a_duplicate_json_key_is_rejected_at_every_depth(omap: ModuleType, tmp_path: Path) -> None:
    base = json.dumps(valid_map())
    duplicates = {
        "pattern kind in a lane": ('"scripts/": "tooling"', '"scripts/": "tooling", "scripts/": "control"'),
        "lane name": ('"org": {', '"org": {"prefix": "x/", "paths": {}}, "org": {'),
        "co_owned entry": (
            '"docs/ARCH.md": {',
            '"docs/ARCH.md": {"kind": "tests", "lanes": ["a", "b"]}, "docs/ARCH.md": {',
        ),
        "role": ('"reviewer": []', '"reviewer": [], "reviewer": ["production"]'),
        "top-level key": ('"mode": "multi-lane"', '"mode": "single-team", "mode": "multi-lane"'),
    }

    for old, new in duplicates.values():
        assert old in base
        target = tmp_path / "ownership.json"
        target.write_text(base.replace(old, new, 1))
        with pytest.raises(omap.MapError, match="duplicate key"):
            omap.load_map(target)


def test_a_deeply_nested_map_is_a_map_error_not_a_crash(omap: ModuleType, tmp_path: Path) -> None:
    target = tmp_path / "ownership.json"
    target.write_text("[" * 200_000)

    with pytest.raises(omap.MapError):
        omap.load_map(target)


RESEMBLING_NAMES: dict[str, str | None] = {
    "src/core.py": None,
    "src/core-extra/a.py": None,
    "src/coreX/a.py": None,
    "src/Core/a.py": None,
    "SRC/core/a.py": None,
    "tests/core.py": None,
    "docs/records.md": None,
    "docs/records-old/r.md": None,
    "docs/ARCH.md.bak": None,
    "docs/ARCH.mdx": None,
    "docs/arch.md": None,
    "docs/ARCH.md/child": None,
    "src/core/.": None,
    "src/core/..": None,
    "src/core/\x00a.py": None,
    "scripts": "*",
    ".": None,
    "..": None,
    "/": None,
    "//": None,
    "docs//records/r.md": None,
    "docs/records//r.md": None,
    "docs/records/./r.md": None,
    "docs/records/../records/r.md": None,
}


@pytest.mark.parametrize("path", sorted(RESEMBLING_NAMES))
def test_names_that_merely_resemble_a_pattern_do_not_match_it(omap: ModuleType, path: str) -> None:
    resolution = build(omap).resolve(path)

    assert (resolution.pattern if resolution else None) == RESEMBLING_NAMES[path]


@pytest.mark.parametrize(
    "path",
    [
        "src/core/new file.py",
        "src/core/café.py",
        "src/core/a\nb.py",
        "src/core/a\tb.py",
        "src/core/-dash.py",
        "src/core/*",
        "src/core/special",
        "src/core/special.py",
        "src/core/shared",
        "src/core/.hidden",
        "src/core/a/b/c/d/e/f.py",
    ],
)
def test_odd_but_legal_names_inside_a_directory_resolve_to_that_directory(omap: ModuleType, path: str) -> None:
    resolution = build(omap).resolve(path)

    assert resolution is not None
    assert resolution.pattern == "src/core/"
    assert resolution.lane == "core"


def test_a_file_named_like_a_directory_pattern_at_the_root_falls_to_the_root_wildcard(omap: ModuleType) -> None:
    ownership = build(omap)

    for name in ("scripts", "tests", "src", "docs", "core"):
        resolution = ownership.resolve(name)
        assert resolution is not None and resolution.pattern == "*"


def test_a_nested_file_named_star_is_not_the_root_wildcard(omap: ModuleType) -> None:
    ownership = build(omap)

    assert ownership.resolve("other/*") is None
    assert ownership.resolve("*") is not None


def test_a_lane_directory_nested_in_a_co_owned_directory_wins_and_the_rest_stays_co_owned(omap: ModuleType) -> None:
    def nest(data: dict[str, Any]) -> None:
        data["co_owned"]["pkg/"] = {"kind": "tests", "lanes": ["core", "org"]}
        data["lanes"]["org"]["paths"]["pkg/org/"] = "records"
        data["co_owned"]["pkg/org/deep/"] = {"kind": "tests", "lanes": ["core", "meta"]}

    ownership = build(omap, nest)

    assert ownership.resolve("pkg/a.py").co_lanes == ("core", "org")
    assert ownership.resolve("pkg/org/a.py").lane == "org"
    assert ownership.resolve("pkg/org/deep/a.py").co_lanes == ("core", "meta")
    assert ownership.may_change("meta", "pkg/org/deep/a.py")
    assert not ownership.may_change("meta", "pkg/a.py")


def test_a_control_path_is_denied_to_every_other_lane_even_when_co_owned_or_included(omap: ModuleType) -> None:
    def make_control(data: dict[str, Any]) -> None:
        data["co_owned"]["docs/ARCH.md"]["kind"] = "control"
        data["lanes"]["org"]["paths"]["docs/records/"] = "control"

    ownership = build(omap, make_control)

    for lane in ("core", "org", "ghost"):
        assert "control path" in (ownership.denial(lane, "docs/ARCH.md") or "")
    assert "control path" in (ownership.denial("org", "docs/records/r.md") or "")
    assert ownership.denial("meta", "docs/records/r.md") is None


def test_a_path_with_no_owner_is_denied_to_every_lane_including_meta_and_unknown_lanes(omap: ModuleType) -> None:
    ownership = build(omap)

    for lane in (*ownership.lanes, "ghost", "", "Meta"):
        assert ownership.denial(lane, "nowhere/at/all.py") == "unmapped"


# What each lane of the committed map may change, spelled out from the map's rules, so an edit to the map or to the
# resolver that moves a boundary shows up as a failing row.
ALL_LANES = ("core", "backend", "design", "org", "meta")
REAL_MAP_OWNERS: dict[str, tuple[str, ...]] = {
    "src/go_poker/core/x.py": ("core",),
    "src/go_poker/game/x.py": ("core",),
    "src/go_poker/__init__.py": ("core",),
    "src/go_poker/__init__.pyc": (),
    "src/go_poker/app/x.py": ("backend",),
    "src/go_poker/app": (),
    "src/go_poker/core": (),
    "src/go_poker/core_extra/x.py": (),
    "src/go_poker/other/x.py": (),
    "tests/core/x.py": ("core",),
    "tests/game/x.py": ("core",),
    "tests/app/x.py": ("backend",),
    "tests/test_layering.py": ("core", "backend"),
    "tests/test_other.py": (),
    "tests/tooling/x.py": ("meta",),
    "tests/tooling": (),
    "docs/design/x.md": ("design",),
    "docs/designer.md": (),
    "docs/design": (),
    "docs/ARCHITECTURE.md": ("core", "backend", "org"),
    "docs/ARCHITECTURE.md.bak": (),
    "docs/ROADMAP.md": ("org", "meta"),
    "docs/CURRENT_CYCLE.md": ("org", "meta"),
    "docs/milestones/M9.md": ("org", "meta"),
    "docs/adr/0009-x.md": ("org", "meta"),
    "docs/product/x.md": ("org", "meta"),
    "docs/company/x.md": ("org", "meta"),
    "README.md": ("org", "meta"),
    "docs/ENGINEERING_PROCESS.md": ("meta",),
    "docs/other.md": (),
    "CLAUDE.md": ("meta",),
    "AGENTS.md": ("meta",),
    ".claude/agents/x.md": ("meta",),
    ".claude/skills/x/SKILL.md": ("meta",),
    ".claude/settings.json": ("meta",),
    ".claude/ownership.json": ("meta",),
    ".claude/settings.local.json": (),
    ".claude/other.md": (),
    "pyproject.toml": ("meta",),
    "uv.lock": ("meta",),
    ".gitignore": ("meta",),
    ".gitattributes": ("meta",),
    ".gitmodules": ("meta",),
    "NEW_ROOT_FILE.txt": ("meta",),
    "scripts/x.py": ("meta",),
    ".github/workflows/ownership.yml": ("meta",),
    "sub/NEW.txt": (),
    "vendor/lib/x.py": (),
}


@pytest.mark.parametrize("path", sorted(REAL_MAP_OWNERS))
def test_the_committed_map_gives_each_path_to_exactly_the_expected_lanes(omap: ModuleType, path: str) -> None:
    ownership = omap.load_map(REAL_MAP)

    allowed = tuple(lane for lane in ALL_LANES if ownership.may_change(lane, path))

    assert sorted(allowed) == sorted(REAL_MAP_OWNERS[path]), path
    assert not ownership.may_change("ghost", path)


def test_in_the_committed_map_only_meta_may_change_any_control_path(omap: ModuleType) -> None:
    ownership = omap.load_map(REAL_MAP)
    control = [pattern for pattern, resolution in ownership.entries.items() if resolution.kind == "control"]

    assert control
    for pattern in control:
        sample = "ROOT_SAMPLE.txt" if pattern == "*" else pattern + ("x" if pattern.endswith("/") else "")
        assert ownership.may_change("meta", sample), sample
        for lane in ALL_LANES:
            if lane != "meta":
                assert "control path" in (ownership.denial(lane, sample) or ""), (lane, sample)


def test_a_map_that_is_not_utf8_or_not_a_file_cannot_be_read(omap: ModuleType, tmp_path: Path) -> None:
    target = tmp_path / "ownership.json"
    target.write_bytes(b"\xff\xfe")

    with pytest.raises(omap.MapError, match="cannot read"):
        omap.load_map(target)
    with pytest.raises(omap.MapError, match="cannot read"):
        omap.load_map(tmp_path)


def test_a_nested_map_just_inside_the_recursion_limit_is_still_parsed_and_rejected_normally(
    omap: ModuleType, tmp_path: Path
) -> None:
    target = tmp_path / "ownership.json"
    target.write_text('{"about": ' + "[" * 300 + "]" * 300 + "}")

    with pytest.raises(omap.MapError, match="missing key"):
        omap.load_map(target)
