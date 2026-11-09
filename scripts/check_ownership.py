"""Judge a pull request's changed paths against the ownership map, failing closed on anything unexpected.

CI's `ownership` job runs this from a checkout of `master`, with the pull request head fetched as Git data only:

    python3 scripts/check_ownership.py --base HEAD --head FETCH_HEAD --branch "$HEAD_REF" \\
        --base-ref "$BASE_REF" --head-repo "$HEAD_REPO" --repository "$REPOSITORY"

The ownership map is read from the repository that contains this script (`.claude/ownership.json`, or `--map PATH`),
never from the head revision, and the head is read only through `git diff`: nothing from it is checked out, imported,
or run. A pull request therefore cannot change the rules or the code that judge it. The script writes nothing into
the checkout, not even a bytecode cache.

In order, the script stops at the first failed group of checks:

1. the map loads and validates (`scripts/ownership_map.py`);
2. `--head-repo` equals `--repository` (a pull request from a fork fails) and `--base-ref` is `master`; both are
   checked in both modes, and every failure of this group is reported together;
3. `single-team` mode: it passes, and no path checks apply;
4. `multi-lane` mode: the branch starts with exactly one lane prefix (`master` and unknown names fail), and every path
   of the merge-base diff (`git diff --name-only -z --no-renames --ignore-submodules=none <base>...<head>`: deletions
   included, both sides of a rename) must be permitted for that lane by `OwnershipMap.denial` in
   `scripts/ownership_map.py`, the home of that rule (including unmapped and control paths).
   Every offending path is listed.

On success it prints `OWNERSHIP: PASS` and exits 0. A failed check prints `OWNERSHIP: FAIL` and one line per reason,
and exits 1. Values from the pull request (paths, branch, repository names) are printed with control characters
escaped, so each reason stays on one line and no output line can be forged or start with `::`.
An invalid map, invalid usage, or a Git error prints `OWNERSHIP: ERROR: <reason>` and exits 2; the script never exits 0
on an error.

The script uses only the standard library and runs on Python 3.9+, so it does not need the project environment.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

# Importing the sibling module must not write a bytecode cache into the checkout being judged.
sys.dont_write_bytecode = True

from ownership_map import MapError, OwnershipMap, load_map  # noqa: E402

REQUIRED_BASE_REF = "master"
DEFAULT_MAP = Path(__file__).resolve().parents[1] / ".claude" / "ownership.json"


class UsageError(Exception):
    """The command line is invalid."""


class GitError(Exception):
    """A Git command failed."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def printable(text: str) -> str:
    """`text` with control characters and other unprintable ones escaped, so a value never spans or forges a line."""
    return "".join(char if char.isprintable() else char.encode("unicode_escape").decode("ascii") for char in text)


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(description="Check a pull request's changed paths against the ownership map.", allow_abbrev=False)
    parser.add_argument("--base", required=True, help="base revision of the merge-base diff (master's HEAD)")
    parser.add_argument("--head", required=True, help="head revision of the merge-base diff (FETCH_HEAD)")
    parser.add_argument("--branch", required=True, help="the pull request's head branch name")
    parser.add_argument("--base-ref", required=True, help="the branch the pull request targets")
    parser.add_argument("--head-repo", required=True, help="full name of the repository the head comes from")
    parser.add_argument("--repository", required=True, help="full name of the repository the pull request targets")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP, help="ownership map (default: the checked-out one)")
    return parser


def changed_paths(base: str, head: str) -> list[str]:
    """The merge-base diff's paths: deletions included, both sides of a rename, never touching the working tree."""
    for revision in (base, head):
        if not revision or revision.startswith("-"):
            raise UsageError(f"invalid revision {revision!r}")
    command = (
        "git",
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        f"{base}...{head}",
        "--",
    )
    try:
        completed = subprocess.run(command, capture_output=True, check=False)
    except OSError as error:
        raise GitError(f"cannot run git: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git diff {base}...{head} failed: {detail}")
    names = completed.stdout.decode("utf-8", errors="replace").split("\0")
    return sorted({name for name in names if name})


def repository_failures(args: argparse.Namespace) -> list[str]:
    failures = []
    if not args.repository:
        raise UsageError("--repository must not be empty")
    if args.head_repo != args.repository:
        failures.append(
            f"head repository {args.head_repo!r} is not {args.repository!r}: pull requests from forks are not accepted"
        )
    if args.base_ref != REQUIRED_BASE_REF:
        failures.append(f"base branch {args.base_ref!r} is not {REQUIRED_BASE_REF!r}")
    return failures


def path_failures(ownership: OwnershipMap, args: argparse.Namespace) -> list[str]:
    lane = ownership.lane_for_branch(args.branch)
    if lane is None:
        return [f"branch {args.branch!r} does not start with exactly one lane prefix"]
    failures = []
    for path in changed_paths(args.base, args.head):
        reason = ownership.denial(lane, path)
        if reason is not None:
            failures.append(f"{path}: {reason}")
    return failures


def run(argv: Sequence[str] | None) -> int:
    args = build_parser().parse_args(argv)
    ownership = load_map(args.map)
    failures = repository_failures(args)
    if not failures and ownership.mode == "multi-lane":
        failures = path_failures(ownership, args)
    if failures:
        print("OWNERSHIP: FAIL")
        for reason in failures:
            print("- " + printable(reason))
        return 1
    print("OWNERSHIP: PASS")
    if ownership.mode == "single-team":
        print("single-team mode: no path checks apply")
    else:
        print(f"every changed path is permitted for branch {printable(args.branch)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except (UsageError, MapError, GitError) as error:
        print("OWNERSHIP: ERROR: " + printable(str(error)))
    except Exception as error:
        print("OWNERSHIP: ERROR: " + printable(f"unexpected {type(error).__name__}: {error}"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
