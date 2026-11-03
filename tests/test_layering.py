"""Layering: `core` and `game` never import `app` or `server`, and `app` never imports `server`.

Checked on the source with `ast`, so it holds for imports in any position (also inside functions and under
`TYPE_CHECKING`).
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "go_poker"


def _imported_modules(path: Path, root: Path) -> set[str]:
    """Every module the file imports, absolute names; `root` is the directory that holds the `go_poker` package."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module.split(".") if node.module else []
            if node.level:
                # `from .x import y` in go_poker/game/m.py is go_poker.game.x; level 2 is go_poker.x.
                here = path.relative_to(root).with_suffix("").parts[: -node.level]
                base = [*here, *base]
            target = ".".join(base)
            modules.add(target)
            modules.update(f"{target}.{alias.name}" for alias in node.names)
    return modules


def _is_within(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")


@pytest.mark.parametrize(
    ("source", "forbidden"),
    [
        ("core", ("go_poker.app", "go_poker.server")),
        ("game", ("go_poker.app", "go_poker.server")),
        ("app", ("go_poker.server",)),
    ],
)
def test_a_layer_never_imports_a_layer_above_it(source: str, forbidden: tuple[str, ...]) -> None:
    files = sorted((PACKAGE / source).rglob("*.py"))
    assert files, f"no source files found under {PACKAGE / source}"
    violations = [
        f"{path.relative_to(PACKAGE)} imports {module}"
        for path in files
        for module in sorted(_imported_modules(path, PACKAGE.parent))
        if any(_is_within(module, package) for package in forbidden)
    ]
    assert violations == []


def test_the_import_scan_detects_absolute_and_relative_forbidden_imports(tmp_path: Path) -> None:
    module = tmp_path / "go_poker" / "game" / "sample.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from go_poker.app import session\nimport go_poker.server.api\nfrom .. import app\nfrom ..app import x\n",
        encoding="utf-8",
    )
    modules = _imported_modules(module, tmp_path)
    assert {"go_poker.app.session", "go_poker.server.api", "go_poker.app", "go_poker.app.x"} <= modules
