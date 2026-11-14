"""The wire mapping is an allowlist, not a copy (ADR 0008 §2, C6.4 Brief §5.1).

A field added to a `TableView`, to a log event or to any other engine value must not reach the wire unless a mapper
names it. The durable guard for that is a source scan: no server module may use a bulk copy of a value's fields, so
the only way onto the wire is an explicit field in `mapping`.

The scan reads the syntax tree, not the text, so that a docstring or a comment may name these very constructs to
explain why they are forbidden.
"""

import ast
from pathlib import Path

import pytest

SERVER_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "go_poker" / "server"
SERVER_MODULES = sorted(SERVER_PACKAGE.glob("*.py"))

# Every way of copying a value's fields in bulk instead of naming them. `model_validate` is included because
# validating a view (or anything with `from_attributes`) into a wire model is exactly that copy; `model_construct`
# because it would build a wire model from a mapping while skipping validation.
FORBIDDEN_NAMES = frozenset({"asdict", "model_validate", "model_construct", "vars", "from_attributes", "__dict__"})


def _referenced_names(source: str) -> set[str]:
    """Every name, attribute, keyword argument and import alias a module's code uses."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[-1])
    return names


def test_the_scan_sees_the_server_modules() -> None:
    names = {path.name for path in SERVER_MODULES}
    assert {"mapping.py", "dto.py"} <= names, f"no server modules found under {SERVER_PACKAGE}"


def test_the_scan_detects_a_bulk_copy() -> None:
    bulk_copies = (
        "import dataclasses\n\n\ndef wire(view):\n    return dataclasses.asdict(view)\n",
        "def wire(view):\n    return Wire.model_validate(view, from_attributes=True)\n",
        "def wire(view):\n    return dict(view.__dict__)\n",
        "def wire(view):\n    return vars(view)\n",
    )
    for source in bulk_copies:
        assert FORBIDDEN_NAMES & _referenced_names(source), source


@pytest.mark.parametrize("path", SERVER_MODULES, ids=lambda path: path.name)
def test_a_server_module_never_copies_a_value_in_bulk(path: Path) -> None:
    used = FORBIDDEN_NAMES & _referenced_names(path.read_text(encoding="utf-8"))
    assert used == set(), f"{path.name} uses {sorted(used)}, which would copy fields instead of naming them"
