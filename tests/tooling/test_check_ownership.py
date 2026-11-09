"""`scripts/check_ownership.py` judges a pull request's changed paths with the base's own map and script.

Three layers keep the suite fast without losing a failure mode:

- a few end-to-end tests run the real script as a subprocess in a temporary clone with a local bare remote (see
  `conftest.py`). Like CI's `ownership` job, it runs from the checked-out base (`master`), and the head is fetched from
  `refs/pull/1/head` into `FETCH_HEAD`, never checked out;
- the `lab` tests run the real script against one shared repository whose heads are built with Git plumbing, so each
  scenario costs one commit and one run;
- the in-process tests call `main` and the pure functions for everything that is decided before Git is involved.
"""

import ast
import itertools
import json
import os
import shutil
import subprocess
import sys
from argparse import Namespace
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

type Repo = Any
type Script = Callable[[str], Any]

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SELF = "acme/poker"


def fixture_map(mode: str) -> dict[str, Any]:
    return {
        "version": 1,
        "mode": mode,
        "patterns": {"precedence": ["exact", "longest-prefix", "root-wildcard"], "unmapped": "fail-closed"},
        "kinds": ["production", "tests", "records", "architecture", "tooling", "control"],
        "lanes": {
            "core": {"prefix": "core/", "paths": {"src/core/": "production", "tests/core/": "tests"}},
            "design": {"prefix": "design/", "paths": {"docs/design/": "records"}},
            "org": {"prefix": "org/", "paths": {"docs/records/": "records"}},
            "meta": {
                "prefix": "meta/",
                "includes": ["org"],
                "paths": {"scripts/": "tooling", ".claude/ownership.json": "control", "*": "control"},
            },
        },
        "co_owned": {"docs/ARCH.md": {"kind": "architecture", "lanes": ["core", "org"]}},
        "roles": {"engineer": ["production"]},
        "closeout_kinds": ["architecture"],
    }


def populate(target: Any, mode: str, map_text: str | None) -> None:
    """Master gets the real scripts, the map and a file in each area (`target` has `root` and `write`)."""
    (target.root / "scripts").mkdir(exist_ok=True)
    for name in ("check_ownership.py", "ownership_map.py"):
        shutil.copy(SCRIPTS / name, target.root / "scripts" / name)
    target.write(".claude/ownership.json", map_text or json.dumps(fixture_map(mode), indent=2) + "\n")
    target.write("src/core/a.py", "A = 1\n")
    target.write("tests/core/test_a.py", "def test_a(): ...\n")
    target.write("docs/records/r.md", "record\n")
    target.write("docs/ARCH.md", "architecture\n")
    target.write("other/x.txt", "unmapped\n")


def seed(repo: Repo, mode: str = "multi-lane", map_text: str | None = None) -> None:
    populate(repo, mode, map_text)
    repo.commit_all("seed")
    repo.git("push", "--quiet", "origin", "master")


def propose(repo: Repo, branch: str, changes: dict[str, str | None]) -> None:
    """Commit `changes` (None deletes) on a new branch, publish it as `refs/pull/1/head`, return to master."""
    repo.git("checkout", "--quiet", "-b", branch)
    for path, text in changes.items():
        if text is None:
            (repo.root / path).unlink()
        else:
            repo.write(path, text)
    repo.commit_all("proposal")
    publish_head(repo, branch)


def publish_head(repo: Repo, branch: str) -> None:
    repo.git("push", "--quiet", "origin", f"+{branch}:refs/pull/1/head")
    repo.git("checkout", "--quiet", "master")
    repo.git("fetch", "--quiet", "--no-tags", "origin", "refs/pull/1/head")


def rename(repo: Repo, branch: str, old: str, new: str) -> None:
    repo.git("checkout", "--quiet", "-b", branch)
    (repo.root / new).parent.mkdir(parents=True, exist_ok=True)
    repo.git("mv", old, new)
    repo.git("commit", "--quiet", "-m", "rename")
    publish_head(repo, branch)


def workflow_arguments(branch: str = "core/feature", **overrides: str) -> list[str]:
    """The script's arguments as separate tokens, like the workflow's shell command."""
    values = {
        "--base": "HEAD",
        "--head": "FETCH_HEAD",
        "--branch": branch,
        "--base-ref": "master",
        "--head-repo": SELF,
        "--repository": SELF,
        **{f"--{key.replace('_', '-')}": value for key, value in overrides.items()},
    }
    return [token for option, value in values.items() for token in (option, value)]


def run_cli(
    repo: Repo,
    arguments: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    python: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [python or sys.executable, str(repo.root / "scripts" / "check_ownership.py"), *arguments]
    return subprocess.run(
        command, cwd=cwd or repo.root, env={**repo.env, **(env or {})}, capture_output=True, text=True, check=False
    )


def check(repo: Repo, branch: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Run the script with `--option=value` arguments (so a value may start with a dash or be empty)."""
    arguments = workflow_arguments(branch, **overrides)
    return run_cli(repo, [f"{option}={value}" for option, value in zip(arguments[::2], arguments[1::2], strict=True)])


def assert_passes(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OWNERSHIP: PASS\n")


def assert_fails(result: subprocess.CompletedProcess[str], *reasons: str) -> None:
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith("OWNERSHIP: FAIL\n")
    assert "PASS" not in result.stdout
    for reason in reasons:
        assert reason in result.stdout, result.stdout


def assert_errors(result: subprocess.CompletedProcess[str], reason: str) -> None:
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout.startswith("OWNERSHIP: ERROR: ")
    assert reason in result.stdout
    assert "PASS" not in result.stdout


def assert_single_line_reasons(stdout: str, expected_reasons: int) -> None:
    """A failure report is the header and one printable `- ` line per reason, however hostile the paths."""
    lines = stdout.split("\n")[:-1]
    assert all(char == "\n" or char.isprintable() for char in stdout), repr(stdout)
    assert len(stdout.splitlines()) == len(lines) == 1 + expected_reasons, repr(stdout)
    assert lines[0] == "OWNERSHIP: FAIL"
    assert all(line.startswith("- ") for line in lines[1:]), repr(stdout)


# --- A shared repository whose heads are built with Git plumbing -----------------------------------------------------


@dataclass(frozen=True)
class Entry:
    """A tree entry other than a regular file: `content` is the blob text, or the commit id of a gitlink (160000)."""

    mode: str
    content: str


type Change = str | Entry | None


def isolated_git_env(directory: Path) -> dict[str, str]:
    """Like `conftest.git_env`, which is function-scoped and so cannot serve a module-scoped repository."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    empty_config = directory / "empty-gitconfig"
    empty_config.write_text("")
    home = directory / "home"
    home.mkdir()
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        GIT_CONFIG_GLOBAL=str(empty_config),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.com",
    )
    return env


class Lab:
    """One repository: `base` holds the seeded files, and master has moved on past it (it changed a record).

    `head(changes)` is a commit on `base` (never checked out) with the given paths changed, so the merge-base diff
    is exactly `changes` while master's own later change must stay out of the verdict. The script is told the head
    by commit id instead of `FETCH_HEAD`.
    """

    def __init__(self, root: Path, env: dict[str, str]) -> None:
        self.root = root
        self.env = env
        self._indexes = itertools.count()
        self._blobs: dict[str, str] = {}
        self.git("init", "--quiet", "--initial-branch=master")
        populate(self, "multi-lane", None)
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", "seed")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.write("docs/records/r.md", "master moved on\n")
        self.git("commit", "--quiet", "--all", "-m", "master moves on")

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def git(self, *args: str, data: bytes | None = None, env: dict[str, str] | None = None) -> str:
        completed = subprocess.run(
            ("git", *args), cwd=self.root, env=env or self.env, input=data, capture_output=True, check=True
        )
        return completed.stdout.decode("utf-8", errors="replace")

    def paths_under(self, prefix: str) -> list[str]:
        listing = self.git("ls-tree", "-r", "--name-only", "-z", self.base, prefix)
        return [name for name in listing.split("\0") if name]

    def _blob(self, text: str) -> str:
        if text not in self._blobs:
            self._blobs[text] = self.git("hash-object", "-w", "--stdin", data=text.encode()).strip()
        return self._blobs[text]

    def head(self, changes: Mapping[str, Change], *, unrelated: bool = False) -> str:
        """The id of a commit that applies `changes` (applied in order; None deletes) to `base`."""
        env = {**self.env, "GIT_INDEX_FILE": str(self.root / ".git" / f"scratch-index-{next(self._indexes)}")}
        if not unrelated:
            self.git("read-tree", self.base, env=env)
        lines = b""
        for path, change in changes.items():
            if change is None:
                prefix = f"0 {'0' * 40}\t"
            else:
                entry = Entry("100644", change) if isinstance(change, str) else change
                blob = entry.content if entry.mode == "160000" else self._blob(entry.content)
                prefix = f"{entry.mode} {blob}\t"
            lines += prefix.encode() + os.fsencode(path) + b"\0"
        self.git("update-index", "-z", "--index-info", data=lines, env=env)
        tree = self.git("write-tree", env=env).strip()
        parent = [] if unrelated else ["-p", self.base]
        return self.git("commit-tree", tree, "-m", "proposal", *parent).strip()


@pytest.fixture(scope="module")
def lab(tmp_path_factory: pytest.TempPathFactory) -> Lab:
    root = tmp_path_factory.mktemp("lab")
    work = root / "work"
    work.mkdir()
    return Lab(work, isolated_git_env(root))


def verdict(lab: Lab, branch: str, changes: Mapping[str, Change], **overrides: str) -> subprocess.CompletedProcess[str]:
    return check(lab, branch, **{"head": lab.head(changes), **overrides})


def map_granting_other() -> dict[str, Any]:
    granted = fixture_map("multi-lane")
    granted["lanes"]["core"]["paths"]["other/"] = "production"
    return granted


# Branch, changes, and the reasons expected (none: the check passes).
LANE_CASES: dict[str, tuple[str, dict[str, Change], list[str]]] = {
    "own paths": ("core/feature", {"src/core/a.py": "A = 2\n", "tests/core/test_new.py": "x = 1\n"}, []),
    "a foreign path": (
        "core/feature",
        {"src/core/a.py": "A = 2\n", "docs/records/r.md": "edited\n"},
        ["- docs/records/r.md: outside lane core (owner: org)"],
    ),
    "an unmapped path": ("core/feature", {"other/x.txt": "edited\n"}, ["- other/x.txt: unmapped"]),
    "control paths from a non-meta lane": (
        "core/feature",
        {".claude/ownership.json": "{}\n", "NOTES.md": "root file\n"},
        [
            "- .claude/ownership.json: control path, reserved for the meta lane",
            "- NOTES.md: control path, reserved for the meta lane",
        ],
    ),
    "control paths from the meta lane": (
        "meta/tooling",
        {".claude/ownership.json": "{}\n", "NOTES.md": "root\n", "scripts/new.py": "x = 1\n"},
        [],
    ),
    "included records from the meta lane": ("meta/records", {"docs/records/r.md": "edited\n"}, []),
    "co-owned architecture from the meta lane": (
        "meta/architecture",
        {"docs/ARCH.md": "edited\n"},
        ["- docs/ARCH.md: outside lane meta (owner: co-owned by core, org)"],
    ),
    "co-owned architecture from a listed lane": (
        "org/records",
        {"docs/ARCH.md": "edited\n", "docs/records/r.md": "edited\n"},
        [],
    ),
    "co-owned architecture from an unlisted lane": (
        "design/art",
        {"docs/ARCH.md": "edited\n", "docs/design/d.md": "design\n"},
        ["- docs/ARCH.md: outside lane design (owner: co-owned by core, org)"],
    ),
    "deleting a foreign file": (
        "core/feature",
        {"docs/records/r.md": None},
        ["- docs/records/r.md: outside lane core"],
    ),
    "deleting an own file": ("core/feature", {"src/core/a.py": None}, []),
    "names that only resemble a pattern": (
        "core/feature",
        {
            "src/corex/a.py": "x\n",
            "tests/core.py": "x\n",
            "docs/ARCH.md.bak": "x\n",
            "docs/records-old/r.md": "x\n",
            "docs/records.md": "x\n",
        },
        [
            "- src/corex/a.py: unmapped",
            "- tests/core.py: unmapped",
            "- docs/ARCH.md.bak: unmapped",
            "- docs/records-old/r.md: unmapped",
            "- docs/records.md: unmapped",
        ],
    ),
    "a branch without a lane prefix": (
        "feature/x",
        {"src/core/a.py": "A = 2\n"},
        ["'feature/x' does not start with exactly one lane prefix"],
    ),
    "a branch named master": (
        "master",
        {"src/core/a.py": "A = 2\n"},
        ["'master' does not start with exactly one lane prefix"],
    ),
    "a branch in the wrong case": (
        "Core/x",
        {"src/core/a.py": "A = 2\n"},
        ["'Core/x' does not start with exactly one lane prefix"],
    ),
    "an empty branch": ("", {"src/core/a.py": "A = 2\n"}, ["'' does not start with exactly one lane prefix"]),
    "a lane name later in the branch": (
        "core/meta/x",
        {"scripts/new.py": "x = 1\n"},
        ["- scripts/new.py: outside lane core (owner: meta)"],
    ),
    "a head that grants its own lane a path": (
        "core/sneaky",
        {".claude/ownership.json": json.dumps(map_granting_other()), "other/x.txt": "sneaked in\n"},
        ["- .claude/ownership.json: control path, reserved", "- other/x.txt: unmapped"],
    ),
    "a head that switches the mode to single-team": (
        "core/sneaky",
        {".claude/ownership.json": json.dumps(fixture_map("single-team")), "other/x.txt": "sneaked in\n"},
        ["- other/x.txt: unmapped"],
    ),
    "a head that replaces the check scripts": (
        "core/sneaky",
        {"scripts/check_ownership.py": 'print("OWNERSHIP: PASS")\n', "scripts/ownership_map.py": "x = 1\n"},
        ["- scripts/check_ownership.py: outside lane core", "- scripts/ownership_map.py: outside lane core"],
    ),
    "a meta head that replaces the check scripts and a core file": (
        "meta/sneaky",
        {"scripts/check_ownership.py": 'print("OWNERSHIP: PASS")\n', "src/core/a.py": "A = 2\n"},
        ["- src/core/a.py: outside lane meta"],
    ),
    "root control files shipped by a head": (
        "core/sneaky",
        {".gitattributes": "* diff=evil\n", ".gitmodules": "x\n", ".github/workflows/ownership.yml": "name: x\n"},
        [
            "- .gitattributes: control path",
            "- .gitmodules: control path",
            "- .github/workflows/ownership.yml: unmapped",
        ],
    ),
}


@pytest.mark.parametrize("case", LANE_CASES, ids=list(LANE_CASES))
def test_the_verdict_follows_the_branch_lane_and_the_map(lab: Lab, case: str) -> None:
    branch, changes, reasons = LANE_CASES[case]

    result = verdict(lab, branch, changes)

    if reasons:
        assert_fails(result, *reasons)
    else:
        assert_passes(result)


def test_a_nested_lane_prefix_is_still_the_first_prefix(lab: Lab) -> None:
    assert_passes(verdict(lab, "meta/core/x", {"scripts/new.py": "x = 1\n"}))
    assert_passes(verdict(lab, "core/meta/x", {"src/core/a.py": "A = 2\n"}))


def test_every_offending_path_is_listed_and_no_other(lab: Lab) -> None:
    changes: dict[str, Change] = {f"docs/records/n{number}.md": "x\n" for number in range(5)}
    changes.update({"other/y.txt": "y\n", "src/core/a.py": "2\n"})

    result = verdict(lab, "core/many", changes)

    assert_single_line_reasons(result.stdout, 6)
    assert result.returncode == 1
    assert "src/core/a.py" not in result.stdout


def test_a_head_equal_to_the_base_has_no_changed_paths_and_passes(lab: Lab) -> None:
    assert_passes(verdict(lab, "core/empty", {}))


def test_masters_later_change_is_not_part_of_the_verdict(lab: Lab) -> None:
    # Master changed docs/records/r.md after the head's base; a two-dot diff would charge that to the head.
    assert_passes(verdict(lab, "core/feature", {"src/core/a.py": "A = 2\n"}))


def test_a_head_with_no_history_in_common_is_a_git_error(lab: Lab) -> None:
    unrelated = lab.head({"src/core/a.py": "A = 9\n"}, unrelated=True)

    result = check(lab, "core/orphan", head=unrelated)

    assert_errors(result, f"git diff HEAD...{unrelated} failed")
    assert "no merge base" in result.stdout


def test_an_unknown_head_revision_is_a_git_error(lab: Lab) -> None:
    assert_errors(check(lab, "core/feature", head="no-such-revision"), "git diff HEAD...no-such-revision failed")


def test_a_revision_that_looks_like_an_option_is_a_usage_error(lab: Lab) -> None:
    assert_errors(check(lab, "core/feature", head="--output=leak.txt"), "invalid revision")
    assert not (lab.root / "leak.txt").exists()


def test_a_file_named_like_the_revision_range_does_not_confuse_the_diff(lab: Lab) -> None:
    head = lab.head({"src/core/a.py": "A = 2\n"})
    lookalike = lab.root / f"HEAD...{head}"
    lookalike.write_text("a path that looks like the revision range\n")
    try:
        assert_passes(check(lab, "core/feature", head=head))
    finally:
        lookalike.unlink()


def test_running_outside_a_repository_is_an_error(lab: Lab, tmp_path: Path) -> None:
    elsewhere = tmp_path / "not-a-repository"
    elsewhere.mkdir()
    head = lab.head({"src/core/a.py": "A = 2\n"})

    result = run_cli(lab, workflow_arguments(head=head), cwd=elsewhere, env={"GIT_CEILING_DIRECTORIES": str(tmp_path)})

    assert_errors(result, "failed")


NAMES = [
    "café-ü.py",
    "日本語.py",
    "with space.py",
    "new\nline.py",
    "tab\tname.py",
    "semi;colon&amp|pipe.py",
    "quo\"te'.py",
    "dollar$HOME`id`.py",
    "-leading-dash.py",
    "nested dir/sub dir/f.py",
    "\udcff\udcfe.py",  # not UTF-8 on disk: the bytes ff fe
]


def test_unusual_file_names_are_judged_by_their_directory(lab: Lab) -> None:
    assert_passes(verdict(lab, "core/inside", {f"src/core/{name}": "x = 1\n" for name in NAMES}))

    result = verdict(lab, "core/outside", {f"docs/records/{name}": "x = 1\n" for name in NAMES})

    assert_single_line_reasons(result.stdout, len(NAMES))
    assert result.stdout.count("outside lane core (owner: org)") == len(NAMES)
    assert "- docs/records/café-ü.py:" in result.stdout
    assert "- docs/records/new\\nline.py:" in result.stdout


def test_a_path_cannot_forge_report_lines(lab: Lab) -> None:
    forged = "docs/records/x\nOWNERSHIP: PASS\n::error::forged"

    result = verdict(lab, "core/sneaky", {forged: "x\n", "other/y.txt": "y\n"})

    assert result.returncode == 1
    assert_single_line_reasons(result.stdout, 2)


def test_non_ascii_paths_stay_readable_in_the_report(lab: Lab) -> None:
    name = "docs/records/café 日本語 \U0001f0cf.md"

    assert_fails(verdict(lab, "core/sneaky", {name: "x\n"}), f"- {name}: outside lane core")


def test_a_branch_name_cannot_forge_lines_in_the_pass_detail(lab: Lab) -> None:
    branch = "core/x\nOWNERSHIP: FAIL ::error::x\r"

    result = verdict(lab, branch, {"src/core/a.py": "A = 2\n"})

    assert result.returncode == 0
    assert all(char == "\n" or char.isprintable() for char in result.stdout), repr(result.stdout)
    assert result.stdout.splitlines()[0] == "OWNERSHIP: PASS"
    assert len(result.stdout.splitlines()) == 2


def test_a_large_diff_is_judged_completely(lab: Lab) -> None:
    changes: dict[str, Change] = {f"src/core/gen/f{number}.py": "x = 1\n" for number in range(1500)}
    assert_passes(verdict(lab, "core/bulk", changes))

    changes["docs/records/hidden-in-the-crowd.md"] = "x\n"
    result = verdict(lab, "core/bulk", changes)

    assert_single_line_reasons(result.stdout, 1)
    assert "- docs/records/hidden-in-the-crowd.md: outside lane core" in result.stdout


EXECUTABLE = "100755"
SYMLINK = "120000"
GITLINK = "160000"
SOME_COMMIT = "1" * 40

ENTRY_CASES: dict[str, tuple[dict[str, Change], list[str]]] = {
    "a mode change of a foreign file": (
        {"docs/records/r.md": Entry(EXECUTABLE, "record\n")},
        ["- docs/records/r.md: outside lane core"],
    ),
    "a mode change of an own file": ({"src/core/a.py": Entry(EXECUTABLE, "A = 1\n")}, []),
    "a foreign file turned into a symlink": (
        {"docs/records/r.md": Entry(SYMLINK, "../../src/core/a.py")},
        ["- docs/records/r.md: outside lane core"],
    ),
    "a gitlink in a foreign directory": (
        {"docs/records/sub": Entry(GITLINK, SOME_COMMIT)},
        ["- docs/records/sub: outside lane core"],
    ),
    "a gitlink at the root": ({"vendor": Entry(GITLINK, SOME_COMMIT)}, ["- vendor: control path"]),
    "a gitlink in an own directory": ({"src/core/sub": Entry(GITLINK, SOME_COMMIT)}, []),
}


@pytest.mark.parametrize("case", ENTRY_CASES, ids=list(ENTRY_CASES))
def test_special_tree_entries_are_judged_like_any_other_path(lab: Lab, case: str) -> None:
    changes, reasons = ENTRY_CASES[case]

    result = verdict(lab, "core/feature", changes)

    if reasons:
        assert_fails(result, *reasons)
    else:
        assert_passes(result)


def test_replacing_a_lane_directory_with_a_symlink_is_caught_as_unmapped(lab: Lab) -> None:
    changes: dict[str, Change] = dict.fromkeys(lab.paths_under("src/core/"))
    changes["src/core"] = Entry(SYMLINK, "../docs/records")

    assert_fails(verdict(lab, "core/swap", changes), "- src/core: unmapped")


# --- End to end: a real pull request ref, fetched into FETCH_HEAD -----------------------------------------------------


def test_a_change_inside_the_branch_lane_passes(repo: Repo) -> None:
    seed(repo)
    propose(repo, "core/feature", {"src/core/a.py": "A = 2\n", "tests/core/test_new.py": "x = 1\n"})

    result = check(repo, "core/feature")

    assert_passes(result)
    assert result.stdout.endswith("every changed path is permitted for branch core/feature\n")


def test_a_change_outside_the_branch_lane_fails_naming_the_path(repo: Repo) -> None:
    seed(repo)
    propose(repo, "core/feature", {"src/core/a.py": "A = 2\n", "docs/records/r.md": "edited\n"})

    result = check(repo, "core/feature")

    assert_fails(result, "- docs/records/r.md: outside lane core (owner: org)")
    assert "src/core/a.py" not in result.stdout


def test_both_sides_of_a_rename_are_checked(repo: Repo) -> None:
    seed(repo)
    rename(repo, "core/move-in", "docs/records/r.md", "src/core/r.md")
    assert_fails(check(repo, "core/move-in"), "- docs/records/r.md: outside lane core")

    repo.git("branch", "--quiet", "-D", "core/move-in")
    rename(repo, "core/move-out", "src/core/a.py", "other/a.py")
    result = check(repo, "core/move-out")
    assert_fails(result, "- other/a.py: unmapped")
    assert "src/core/a.py" not in result.stdout

    repo.git("branch", "--quiet", "-D", "core/move-out")
    rename(repo, "core/move", "src/core/a.py", "src/core/b.py")
    assert_passes(check(repo, "core/move"))


def test_only_the_merge_base_diff_counts_when_master_moved_on(repo: Repo) -> None:
    seed(repo)
    propose(repo, "core/feature", {"src/core/a.py": "A = 2\n"})
    repo.write("docs/records/r.md", "master moved on\n")
    repo.commit_all("master change")
    assert_passes(check(repo, "core/feature"))

    repo.git("checkout", "--quiet", "core/feature")
    repo.git("merge", "--quiet", "--no-edit", "master")
    publish_head(repo, "core/feature")
    assert_passes(check(repo, "core/feature"))


def test_the_head_is_read_only_as_git_data(repo: Repo) -> None:
    seed(repo)
    propose(repo, "core/feature", {"src/core/a.py": "A = 2\n"})
    before = repo.status()

    check(repo, "core/feature")

    assert repo.status() == before == ""
    assert (repo.root / "src/core/a.py").read_text() == "A = 1\n"


def test_a_fork_or_a_non_master_base_fails(repo: Repo) -> None:
    seed(repo)
    propose(repo, "core/feature", {"src/core/a.py": "A = 2\n"})

    assert_fails(check(repo, "core/feature", head_repo="mallory/poker"), "'mallory/poker' is not 'acme/poker'")
    assert_fails(check(repo, "core/feature", base_ref="develop"), "base branch 'develop' is not 'master'")
    both = check(repo, "core/feature", head_repo="", base_ref="develop")
    assert_fails(both, "forks are not accepted", "base branch 'develop'")


def test_single_team_mode_passes_with_no_path_checks(repo: Repo) -> None:
    seed(repo, mode="single-team")
    propose(repo, "feature/x", {"other/x.txt": "unmapped\n", ".claude/ownership.json": "{}\n"})

    result = check(repo, "feature/x")

    assert_passes(result)
    assert result.stdout == "OWNERSHIP: PASS\nsingle-team mode: no path checks apply\n"


def test_an_invalid_map_is_an_error(repo: Repo) -> None:
    broken = fixture_map("multi-lane")
    broken["lanes"]["core"]["paths"]["../escape"] = "production"
    seed(repo, map_text=json.dumps(broken))
    propose(repo, "core/feature", {"src/core/a.py": "A = 2\n"})

    assert_errors(check(repo, "core/feature"), "not a normalized repository-relative path")


def test_the_verdict_does_not_depend_on_the_working_tree_or_the_directory(repo: Repo) -> None:
    seed(repo)
    propose(repo, "core/own", {"src/core/a.py": "A = 2\n"})
    own = repo.git("rev-parse", "FETCH_HEAD").strip()
    propose(repo, "core/foreign", {"src/core/a.py": "A = 2\n", "other/x.txt": "edited\n"})
    foreign = repo.git("rev-parse", "FETCH_HEAD").strip()
    # Dirty and untracked work, and a relaxed map in the directory the check runs from: none of it may count.
    repo.write("docs/records/r.md", "dirty\n")
    repo.git("add", "docs/records/r.md")
    repo.write("untracked-root.txt", "dirty\n")
    subdirectory = repo.root / "src" / "core"
    repo.write("src/core/.claude/ownership.json", json.dumps(fixture_map("single-team")))

    assert_passes(run_cli(repo, workflow_arguments(head=own), cwd=subdirectory))
    result = run_cli(repo, workflow_arguments(head=foreign), cwd=subdirectory)

    assert_fails(result, "- other/x.txt: unmapped")
    assert "src/core/a.py" not in result.stdout


def test_git_settings_and_drivers_on_master_cannot_hide_or_run_anything(repo: Repo, tmp_path: Path) -> None:
    seed(repo)
    marker = tmp_path / "driver-ran"
    driver = tmp_path / "driver.sh"
    driver.write_text(f"#!/bin/sh\ntouch {marker}\n")
    driver.chmod(0o755)
    repo.write(".gitattributes", "* diff=evil\n")
    repo.commit_all("attributes")
    repo.git("push", "--quiet", "origin", "master")
    for key, value in (
        ("diff.renames", "copies"),
        ("diff.noprefix", "true"),
        ("core.quotepath", "true"),
        ("diff.relative", "true"),
        ("diff.evil.command", str(driver)),
        ("diff.evil.textconv", str(driver)),
        ("diff.external", str(driver)),
    ):
        repo.git("config", key, value)
    rename(repo, "core/move-out", "docs/records/r.md", "src/core/r.md")

    assert_fails(check(repo, "core/move-out"), "- docs/records/r.md: outside lane core")
    assert not marker.exists()


def test_a_submodule_ignore_setting_on_master_cannot_hide_a_submodule_change(repo: Repo) -> None:
    seed(repo)
    commit = repo.head()
    repo.git("update-index", "--add", "--cacheinfo", f"{GITLINK},{commit},docs/records/sub")
    repo.write(
        ".gitmodules", '[submodule "docs/records/sub"]\n\tpath = docs/records/sub\n\turl = ../sub\n\tignore = all\n'
    )
    repo.git("add", ".gitmodules")
    repo.git("config", "diff.ignoreSubmodules", "all")
    repo.git("commit", "--quiet", "-m", "master has a submodule that is ignored")
    repo.git("push", "--quiet", "origin", "master")
    repo.git("checkout", "--quiet", "-b", "core/submodule-bump")
    repo.git("update-index", "--cacheinfo", f"{GITLINK},{'1' * 40},docs/records/sub")
    repo.git("commit", "--quiet", "-m", "bump")
    publish_head(repo, "core/submodule-bump")

    assert_fails(check(repo, "core/submodule-bump"), "- docs/records/sub: outside lane core")


# --- Python versions -------------------------------------------------------------------------------------------

SYSTEM_PYTHON = Path("/usr/bin/python3")


def test_the_scripts_use_no_syntax_newer_than_python_39() -> None:
    for name in ("ownership_map.py", "check_ownership.py"):
        ast.parse((SCRIPTS / name).read_text(), filename=name, feature_version=(3, 9))


@pytest.mark.skipif(not SYSTEM_PYTHON.exists(), reason="no system python3 at /usr/bin/python3")
def test_the_check_runs_on_the_system_python(lab: Lab, tmp_path: Path) -> None:
    # The version differs by machine (3.9 on macOS, newer on CI): the check must run on whichever one it is.
    python = str(SYSTEM_PYTHON)
    own, foreign = lab.head({"src/core/a.py": "A = 3\n"}), lab.head({"docs/records/r.md": "edited\n"})
    single = tmp_path / "single.json"
    single.write_text(json.dumps(fixture_map("single-team")))

    assert_passes(run_cli(lab, workflow_arguments(head=own), python=python))
    assert_fails(run_cli(lab, workflow_arguments(head=foreign), python=python), "- docs/records/r.md")
    assert_passes(run_cli(lab, [*workflow_arguments(head=foreign), "--map", str(single)], python=python))


def test_ascii_only_output_encoding_never_turns_a_failure_into_a_pass(lab: Lab) -> None:
    head = lab.head({"docs/records/café.md": "x\n"})

    result = run_cli(lab, workflow_arguments(head=head), env={"PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"})

    assert result.returncode != 0
    assert "OWNERSHIP: PASS" not in result.stdout


# --- In process: everything decided before Git is involved -----------------------------------------------------


@pytest.fixture
def cli(script: Script, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """The script's module, run from an empty directory so nothing here can reach a repository."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.chdir(tmp_path)
    return script("check_ownership")


def map_file(tmp_path: Path, mode: str = "multi-lane") -> Path:
    target = tmp_path / "map.json"
    target.write_text(json.dumps(fixture_map(mode)))
    return target


def main_with(cli: Any, capsys: pytest.CaptureFixture[str], arguments: list[str], mode_map: Path) -> tuple[int, str]:
    code = cli.main([*arguments, "--map", str(mode_map)])
    return code, capsys.readouterr().out


REPOSITORY_DIFFERENCES = [
    {"head_repo": "Acme/Poker"},
    {"head_repo": "acme/poker "},
    {"head_repo": " acme/poker"},
    {"head_repo": "acme/poker/"},
    {"head_repo": "acme/poker\n"},
    {"head_repo": "mallory/acme/poker"},
    {"head_repo": ""},
    {"head_repo": "null"},
    {"repository": "Acme/Poker"},
    {"base_ref": "Master"},
    {"base_ref": "refs/heads/master"},
    {"base_ref": "master "},
    {"base_ref": "master\n"},
    {"base_ref": "master/"},
    {"base_ref": ""},
    {"base_ref": "main"},
]


def test_any_repository_or_base_difference_is_a_failure(cli: Any) -> None:
    def failures(**overrides: str) -> list[str]:
        values = {"head_repo": SELF, "repository": SELF, "base_ref": "master", **overrides}
        return list(cli.repository_failures(Namespace(**values)))

    assert failures() == []
    for overrides in REPOSITORY_DIFFERENCES:
        assert len(failures(**overrides)) == 1, overrides
    assert len(failures(head_repo="mallory/poker", base_ref="develop")) == 2
    with pytest.raises(cli.UsageError, match="--repository must not be empty"):
        failures(head_repo="", repository="")


@pytest.mark.parametrize("mode", ["single-team", "multi-lane"])
def test_a_fork_or_a_non_master_base_fails_before_any_path_check_in_both_modes(
    cli: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path, mode: str
) -> None:
    for overrides in ({"head_repo": "mallory/poker"}, {"base_ref": "develop"}, {"head_repo": ""}):
        code, output = main_with(cli, capsys, workflow_arguments(**overrides), map_file(tmp_path, mode))

        assert code == 1, overrides
        assert output.startswith("OWNERSHIP: FAIL\n- "), output
        assert "PASS" not in output


@pytest.mark.parametrize("value", ["-x", "--help", "-h", "--map=custom.json", "--branch"])
def test_no_pull_request_value_can_turn_into_an_option_or_a_pass(
    cli: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path, value: str
) -> None:
    for option in ("branch", "head_repo", "base_ref", "repository"):
        code, output = main_with(cli, capsys, workflow_arguments(**{option: value}), map_file(tmp_path, "single-team"))

        assert code == 2, (option, output)
        assert output.startswith("OWNERSHIP: ERROR: ")
        assert "PASS" not in output


def test_single_team_mode_passes_without_touching_git(
    cli: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, output = main_with(cli, capsys, workflow_arguments("feature/x"), map_file(tmp_path, "single-team"))

    assert (code, output) == (0, "OWNERSHIP: PASS\nsingle-team mode: no path checks apply\n")


def broken_map_texts() -> dict[str, str]:
    good = json.dumps(fixture_map("multi-lane"))
    return {
        "empty": "",
        "unterminated": "{",
        "a list": "[]",
        "null": "null",
        "a string": '"text"',
        "a number": "1",
        "a byte order mark": "﻿" + good,
        "far too deeply nested": "[" * 200000,
        "NaN": '{"version": NaN}',
        "a duplicate mode": good.replace('"mode": "multi-lane"', '"mode": "multi-lane", "mode": "single-team"'),
        "a duplicate path": good.replace('"scripts/": "tooling"', '"scripts/": "tooling", "scripts/": "control"'),
        "another case of the mode": good.replace('"mode": "multi-lane"', '"mode": "Multi-Lane"'),
        "an invalid kind": good.replace('"src/core/": "production"', '"src/core/": "undeclared-kind"'),
    }


@pytest.mark.parametrize("name", list(broken_map_texts()))
def test_an_unusable_map_is_an_error_and_never_a_pass(
    cli: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path, name: str
) -> None:
    target = tmp_path / "bad.json"
    target.write_text(broken_map_texts()[name], encoding="utf-8")

    code, output = main_with(cli, capsys, workflow_arguments(), target)

    assert code == 2, output
    assert output.startswith("OWNERSHIP: ERROR: ")
    assert "PASS" not in output


def test_a_map_that_is_missing_not_utf8_or_not_a_file_is_an_error(
    cli: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "latin.json").write_bytes(b'{"about": "caf\xe9"}')
    for target in (tmp_path / "absent.json", tmp_path / "latin.json", tmp_path):
        code, output = main_with(cli, capsys, workflow_arguments(), target)

        assert code == 2
        assert output.startswith("OWNERSHIP: ERROR: cannot read")


def test_missing_unknown_and_abbreviated_arguments_are_usage_errors(
    cli: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    for arguments in (["--base", "HEAD"], ["--bogus"], [*workflow_arguments(), "--head-rep", "x"]):
        assert cli.main(arguments) == 2
        assert capsys.readouterr().out.startswith("OWNERSHIP: ERROR: ")


def test_a_help_request_exits_cleanly_and_never_reports_a_pass(cli: Any, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--help"])

    assert stopped.value.code == 0
    assert "OWNERSHIP: PASS" not in capsys.readouterr().out


SEPARATORS = [
    "\n",
    "\r",
    "\r\n",
    "\x0b",
    "\x0c",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    " ",
    " ",
    "​",
    "‮",
    "﻿",
    "\x1b[31m",
    "\x07",
]


def test_printable_escapes_every_separator_and_nothing_readable(cli: Any) -> None:
    for separator in SEPARATORS:
        hostile = f"a{separator}::error::x{separator}OWNERSHIP: PASS"
        escaped = cli.printable(hostile)

        assert escaped.isprintable() and len(escaped.splitlines()) == 1, repr(separator)
        assert escaped.startswith("a\\") and "::error::x" in escaped
    assert cli.printable("plain/café 日本.md \U0001f0cf") == "plain/café 日本.md \U0001f0cf"
    assert cli.printable("a\r\nb") == "a\\r\\nb"
    assert cli.printable("a b c\x85d") == "a\\u2028b\\u2029c\\x85d"
    assert cli.printable("") == ""


@pytest.mark.parametrize("separator", ["\n", "\r", "\u2028", "\x85"], ids=repr)
def test_error_text_built_from_given_values_stays_on_one_line(
    cli: Any, capsys: pytest.CaptureFixture[str], tmp_path: Path, separator: str
) -> None:
    hostile = f"x{separator}OWNERSHIP: PASS{separator}::error::x"
    known = [token for token in workflow_arguments() if token not in ("--head", "FETCH_HEAD")]
    valid_map = str(map_file(tmp_path))

    for arguments in (
        [*workflow_arguments(), "--map", str(tmp_path / hostile)],
        [*known, "--head=-" + hostile, "--map", valid_map],
        [*workflow_arguments(), "--bogus", hostile, "--map", valid_map],
    ):
        assert cli.main(arguments) == 2
        output = capsys.readouterr().out
        assert all(char == "\n" or char.isprintable() for char in output), repr(output)
        assert len(output.splitlines()) == 1 and output.startswith("OWNERSHIP: ERROR: "), repr(output)
