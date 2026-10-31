"""Commit and push one approved Cycle closeout, failing closed on anything unexpected.

Only the user's explicit `/finish-cycle` invocation authorizes running this script. It reads the approved closeout
manifest from standard input and runs from anywhere inside the repository:

    python3 scripts/finish_cycle.py <<'MANIFEST'
    message: feat: add continuous Hold'em game
    path: src/go_poker/game/variants/texas_holdem/game.py
    path: tests/game/variants/texas_holdem/test_holdem_game.py
    MANIFEST

The manifest has exactly one `message:` line (the one-line commit message) and one `path:` line per changed path:
repository-relative, normalized, including deleted files and both sides of a rename. Blank lines are ignored.

In order, the script stops at the first failed check:

1. no manifest path is machine-local;
2. no merge, rebase, cherry-pick, revert, or bisect is in progress, and nothing is unmerged;
3. HEAD is a branch that tracks a remote upstream; the upstream is fetched; the branch is neither ahead of, behind,
   nor diverged from it (unpushed commits are listed, never pushed);
4. no manifest path is git-ignored;
5. the working tree's changed paths, untracked files included, are exactly the manifest paths;
6. `scripts/verify.py` passes, and verification left every path unchanged;
7. only the manifest paths are staged, by explicit path, and the staged set equals the manifest;
8. `git commit` runs with hooks;
9. before any push: HEAD is a new single-parent commit on the previous HEAD, exactly one commit ahead of the
   upstream, containing exactly the manifest paths, with the manifest message, and the working tree is clean;
10. that exact commit alone is pushed, without force or tags, to the upstream branch; the upstream is fetched
    again and must equal it, with a clean working tree.

On success it prints a `SESSION COMPLETE` block and exits 0. When it stops it prints the reason and the resulting Git
state and exits 1; nothing after the failed check runs. An invalid manifest exits 2 before any Git command.
Every Git command goes through a guard that refuses force, amend, skipped hooks, and any history-rewriting or
working-tree-discarding subcommand (reset, restore, stash, rebase, checkout, ...). The script never repairs state.

The script uses only the standard library and runs on Python 3.9+, so it does not need the project environment.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ALLOWED_GIT_SUBCOMMANDS = frozenset(
    {
        "add",
        "check-ignore",
        "commit",
        "config",
        "diff",
        "diff-tree",
        "fetch",
        "log",
        "push",
        "rev-list",
        "rev-parse",
        "status",
        "symbolic-ref",
    }
)
FORBIDDEN_GIT_ARGUMENTS = frozenset({"-f", "-n", "-d", "-D", "--mirror", "--delete", "--prune", "--all", "--tags"})

MACHINE_LOCAL_FILES = frozenset({".claude/settings.local.json"})
MACHINE_LOCAL_NAMES = frozenset({".DS_Store", ".coverage", ".env"})
MACHINE_LOCAL_PREFIXES = (".claude/usage/", ".venv/")

IN_PROGRESS_MARKERS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "rebase-merge", "rebase-apply")
UNMERGED_STATUSES = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})


class ManifestError(Exception):
    """The manifest is malformed; nothing has run."""


class Stop(Exception):
    """A check failed; the closeout stops here."""


class GitPolicyError(Exception):
    """A Git command outside the closeout's allowed set was attempted."""


@dataclass(frozen=True)
class Manifest:
    message: str
    paths: tuple[str, ...]


def parse_manifest(text: str) -> Manifest:
    message = None
    paths: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        value = value.strip()
        if not separator or key not in ("message", "path"):
            raise ManifestError(f"line {number}: expected 'message: <text>' or 'path: <path>'")
        if not value:
            raise ManifestError(f"line {number}: empty {key}")
        if key == "message":
            if message is not None:
                raise ManifestError(f"line {number}: more than one message line")
            message = value
            continue
        posix = PurePosixPath(value)
        if posix.is_absolute() or str(posix) != value or any(part in (".", "..") for part in posix.parts):
            raise ManifestError(f"line {number}: path must be repository-relative and normalized: {value}")
        if value in paths:
            raise ManifestError(f"line {number}: duplicate path: {value}")
        paths.append(value)
    if message is None:
        raise ManifestError("missing 'message:' line")
    if not paths:
        raise ManifestError("missing 'path:' lines")
    return Manifest(message, tuple(paths))


def check_git_arguments(args: Sequence[str]) -> None:
    """Refuse any Git command outside the closeout's allowed set. Arguments after `--` are paths, never options."""
    if not args or args[0] not in ALLOWED_GIT_SUBCOMMANDS:
        raise GitPolicyError(f"git subcommand not allowed: {' '.join(args)}")
    options = args[1 : args.index("--")] if "--" in args else args[1:]
    for argument in options:
        if argument in FORBIDDEN_GIT_ARGUMENTS or argument.startswith(("--force", "--no-verify", "--amend")):
            raise GitPolicyError(f"git argument not allowed: {' '.join(args)}")
        if args[0] == "push" and argument.startswith(("+", ":")):
            raise GitPolicyError(f"git refspec not allowed: {' '.join(args)}")


def is_machine_local(path: str) -> bool:
    return (
        path in MACHINE_LOCAL_FILES
        or PurePosixPath(path).name in MACHINE_LOCAL_NAMES
        or path.startswith(MACHINE_LOCAL_PREFIXES)
    )


class Closeout:
    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest
        self.expected = frozenset(manifest.paths)
        self.state = "nothing staged, committed, or pushed"
        self.root = Path(self.git("rev-parse", "--show-toplevel", cwd=Path.cwd()).strip())

    def git_result(self, *args: str, cwd: Path | None = None, stdin: str = "") -> subprocess.CompletedProcess[str]:
        check_git_arguments(args)
        return subprocess.run(
            ("git", *args), cwd=cwd or self.root, input=stdin, capture_output=True, text=True, check=False
        )

    def git(self, *args: str, cwd: Path | None = None, allowed_codes: tuple[int, ...] = (0,), stdin: str = "") -> str:
        completed = self.git_result(*args, cwd=cwd, stdin=stdin)
        if completed.returncode not in allowed_codes:
            detail = (completed.stderr or completed.stdout).strip()
            raise Stop(f"`git {' '.join(args)}` failed (exit {completed.returncode}): {detail}")
        return completed.stdout

    def status_entries(self) -> list[tuple[str, str, bool]]:
        """(XY status, path, is rename source) for every changed path, untracked included."""
        fields = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
        entries = []
        index = 0
        while index < len(fields):
            entry = fields[index]
            index += 1
            if not entry:
                continue
            status, path = entry[:2], entry[3:]
            entries.append((status, path, False))
            if "R" in status or "C" in status:
                if "R" in status:
                    entries.append((status, fields[index], True))
                index += 1
        return entries

    def changed_paths(self) -> frozenset[str]:
        return frozenset(path for _, path, _ in self.status_entries())

    def unstaged_paths(self) -> frozenset[str]:
        """Paths with working-tree changes not in the index; a staged rename's source has none."""
        return frozenset(
            path
            for status, path, source in self.status_entries()
            if not source and (status == "??" or status[1] != " ")
        )

    def snapshot(self) -> dict[str, str]:
        """Content fingerprint of every manifest path; a missing path is recorded as missing."""
        fingerprints = {}
        for path in self.manifest.paths:
            target = self.root / path
            if target.is_symlink():
                fingerprints[path] = "symlink:" + os.readlink(target)
            elif target.is_file():
                fingerprints[path] = hashlib.sha256(target.read_bytes()).hexdigest()
            else:
                fingerprints[path] = "missing" if not target.exists() else "not a file"
        return fingerprints

    def ahead_behind(self) -> tuple[int, int]:
        behind, ahead = self.git("rev-list", "--left-right", "--count", "@{upstream}...HEAD").split()
        return int(ahead), int(behind)

    def run(self) -> str:
        machine_local = sorted(path for path in self.manifest.paths if is_machine_local(path))
        if machine_local:
            raise Stop(f"manifest includes machine-local paths: {', '.join(machine_local)}")

        for marker in IN_PROGRESS_MARKERS:
            if (self.root / self.git("rev-parse", "--git-path", marker).strip()).exists():
                raise Stop(f"a Git operation is in progress ({marker})")
        unmerged = sorted(path for status, path, _ in self.status_entries() if status in UNMERGED_STATUSES)
        if unmerged:
            raise Stop(f"unmerged paths: {', '.join(unmerged)}")

        branch = self.git("symbolic-ref", "--quiet", "--short", "HEAD", allowed_codes=(0, 1)).strip()
        if not branch:
            raise Stop("HEAD is detached")
        remote = self.git("config", "--get", f"branch.{branch}.remote", allowed_codes=(0, 1)).strip()
        merge_ref = self.git("config", "--get", f"branch.{branch}.merge", allowed_codes=(0, 1)).strip()
        if not remote or not merge_ref:
            raise Stop(f"branch {branch} has no upstream")
        if remote == ".":
            raise Stop(f"branch {branch} tracks a local branch, not a remote")
        if not merge_ref.startswith("refs/heads/"):
            raise Stop(f"branch {branch} has an unexpected upstream ref: {merge_ref}")
        upstream = self.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}").strip()

        self.git("fetch", "--quiet", remote)
        ahead, behind = self.ahead_behind()
        if ahead or behind:
            unpushed = self.git("log", "--format=%h %s", "@{upstream}..HEAD").strip()
            listing = f"; unpushed commits (not pushed):\n{unpushed}" if unpushed else ""
            raise Stop(f"{branch} is {ahead} ahead of and {behind} behind {upstream}{listing}")

        ignored_output = self.git(
            "check-ignore",
            "--no-index",
            "--stdin",
            "-z",
            stdin="\0".join(self.manifest.paths) + "\0",
            allowed_codes=(0, 1),
        )
        ignored = sorted(path for path in ignored_output.split("\0") if path)
        if ignored:
            raise Stop(f"manifest includes git-ignored paths: {', '.join(ignored)}")
        self.require_changed_paths_match()

        before = self.snapshot()
        verifier = self.root / "scripts" / "verify.py"
        if not verifier.is_file():
            raise Stop("scripts/verify.py is missing")
        sys.stdout.flush()
        if subprocess.run((sys.executable, str(verifier)), cwd=self.root, check=False).returncode != 0:
            raise Stop("verification failed")
        self.require_changed_paths_match()
        changed_by_verification = sorted(path for path, value in self.snapshot().items() if before[path] != value)
        if changed_by_verification:
            raise Stop(f"verification changed manifest paths: {', '.join(changed_by_verification)}")

        previous_head = self.git("rev-parse", "HEAD").strip()
        to_stage = sorted(self.unstaged_paths())
        if to_stage:
            self.state = "manifest paths may be partly staged; nothing committed or pushed"
            self.git("add", "--", *to_stage)
        self.state = "manifest paths staged; nothing committed or pushed"
        staged = frozenset(self.git("diff", "--cached", "--name-only", "--no-renames", "-z").split("\0")) - {""}
        if staged != self.expected:
            raise Stop(f"staged paths differ from the manifest: {self.describe_difference(staged, 'staged')}")
        if self.unstaged_paths():
            raise Stop(f"unstaged changes remain after staging: {', '.join(sorted(self.unstaged_paths()))}")

        self.git("commit", "--quiet", f"--message={self.manifest.message}")
        commit = self.git("rev-parse", "HEAD").strip()
        if commit == previous_head:
            raise Stop("git commit did not create a commit")
        self.state = f"committed locally as {commit[:7]}; NOT pushed"
        self.require_commit(commit, previous_head)

        self.git("push", "--quiet", "--no-follow-tags", remote, f"{commit}:{merge_ref}")
        self.state = f"pushed {commit[:7]} to {upstream}"
        self.git("fetch", "--quiet", remote)
        if self.git("rev-parse", "@{upstream}").strip() != commit:
            raise Stop(f"{upstream} does not point at {commit[:7]} after the push")
        if self.ahead_behind() != (0, 0) or self.status_entries():
            raise Stop("branch or working tree is not clean and in sync after the push")

        subject = self.git("log", "--format=%s", "--max-count=1", commit).strip()
        return (
            "SESSION COMPLETE\n"
            f"Commit: {commit[:7]} {subject}\n"
            f"Branch: {branch}\n"
            f"Push: pushed to {upstream} ({previous_head[:7]}..{commit[:7]}); in sync with upstream\n"
            "Working tree: clean\n"
        )

    def require_changed_paths_match(self) -> None:
        changed = self.changed_paths()
        if changed != self.expected:
            raise Stop(f"working-tree changes differ from the manifest: {self.describe_difference(changed, 'changed')}")

    def require_commit(self, commit: str, previous_head: str) -> None:
        """Every check the push depends on; any failure stops before the push runs."""
        parents = self.git("rev-list", "--parents", "--max-count=1", commit).split()[1:]
        if parents != [previous_head]:
            raise Stop("the new commit's parent is not the previous HEAD")
        ahead, behind = self.ahead_behind()
        if (ahead, behind) != (1, 0):
            raise Stop(f"expected exactly 1 commit ahead and 0 behind, found {ahead} ahead and {behind} behind")
        files = self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", "-z", commit)
        committed = frozenset(files.split("\0")) - {""}
        if committed != self.expected:
            raise Stop(f"committed paths differ from the manifest: {self.describe_difference(committed, 'committed')}")
        if self.git("log", "--format=%B", "--max-count=1", commit).strip() != self.manifest.message:
            raise Stop("the commit message differs from the manifest")
        if self.status_entries():
            raise Stop("the working tree is not clean after the commit")

    def describe_difference(self, actual: frozenset[str], verb: str) -> str:
        parts = []
        unexpected = sorted(actual - self.expected)
        missing = sorted(self.expected - actual)
        if unexpected:
            parts.append(f"not in manifest: {', '.join(unexpected)}")
        if missing:
            parts.append(f"in manifest but not {verb}: {', '.join(missing)}")
        return "; ".join(parts)


def main() -> int:
    try:
        manifest = parse_manifest(sys.stdin.read())
    except ManifestError as error:
        print(f"FINISH: INVALID MANIFEST: {error}")
        return 2
    closeout = None
    try:
        closeout = Closeout(manifest)
        print(closeout.run(), end="")
    except (Stop, GitPolicyError) as error:
        reason = str(error)
    except Exception as error:  # fail closed and still report the Git state
        reason = f"unexpected error: {error!r}"
    else:
        return 0
    print(f"FINISH: STOPPED: {reason}")
    print(f"Git state: {closeout.state if closeout else 'nothing staged, committed, or pushed'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
