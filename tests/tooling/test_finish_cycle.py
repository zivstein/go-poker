"""`scripts/finish_cycle.py` commits and pushes exactly the approved manifest, and otherwise stops without pushing.

Every test runs the real script against a temporary clone and a local bare remote (see `conftest.py`).
"""

import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

type Repo = Any
type Script = Callable[[str], ModuleType]


def manifest(message: str, *paths: str) -> str:
    return "".join([f"message: {message}\n", *(f"path: {path}\n" for path in paths)])


def assert_stopped(result: Any, reason: str) -> None:
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FINISH: STOPPED:" in result.stdout
    assert reason in result.stdout
    assert "SESSION COMPLETE" not in result.stdout


def assert_untouched(repo: Repo, head: str) -> None:
    """Nothing committed, nothing pushed, nothing staged."""
    assert repo.head() == head
    assert repo.remote_head() == head
    assert repo.staged() == ""


def test_commits_and_pushes_exactly_the_manifest(repo: Repo) -> None:
    previous = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")
    repo.write("src/new_module.py", "NEW = True\n")
    (repo.root / "docs/notes.md").unlink()

    result = repo.finish(manifest("feat: add Hold'em things", "src/app.py", "src/new_module.py", "docs/notes.md"))

    assert result.returncode == 0, result.stdout + result.stderr
    commit = repo.head()
    assert repo.remote_head() == commit
    assert repo.git("rev-parse", "HEAD^").strip() == previous
    assert repo.git("log", "--format=%B", "-1").strip() == "feat: add Hold'em things"
    committed = repo.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").split()
    assert sorted(committed) == ["docs/notes.md", "src/app.py", "src/new_module.py"]
    assert repo.status() == ""
    assert result.stdout.endswith(
        "SESSION COMPLETE\n"
        f"Commit: {commit[:7]} feat: add Hold'em things\n"
        "Branch: master\n"
        f"Push: pushed to origin/master ({previous[:7]}..{commit[:7]}); in sync with upstream\n"
        "Working tree: clean\n"
    )
    assert "VERIFY: PASS" in result.stdout


def test_commits_a_staged_rename_listed_by_both_paths(repo: Repo) -> None:
    repo.git("mv", "docs/notes.md", "docs/guide.md")

    result = repo.finish(manifest("docs: rename notes", "docs/notes.md", "docs/guide.md"))

    assert result.returncode == 0, result.stdout
    assert repo.remote_head() == repo.head()
    assert repo.status() == ""


def test_a_changed_path_missing_from_the_manifest_stops_before_staging(repo: Repo) -> None:
    head = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")
    repo.write("scratch.txt", "unrelated\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "not in manifest: scratch.txt")
    assert_untouched(repo, head)
    assert "VERIFY:" not in result.stdout


def test_a_manifest_path_without_a_change_stops(repo: Repo) -> None:
    head = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py", "README.md"))

    assert_stopped(result, "in manifest but not changed: README.md")
    assert_untouched(repo, head)


def test_an_ignored_manifest_path_stops(repo: Repo) -> None:
    head = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")
    repo.write("ignored.txt", "local\n")

    result = repo.finish(manifest("feat: change", "src/app.py", "ignored.txt"))

    assert_stopped(result, "git-ignored paths: ignored.txt")
    assert_untouched(repo, head)


@pytest.mark.parametrize("path", [".claude/settings.local.json", ".claude/usage/history.csv", "docs/.DS_Store"])
def test_a_machine_local_manifest_path_stops_even_when_not_ignored(repo: Repo, path: str) -> None:
    head = repo.head()
    repo.write(path, "{}\n")

    result = repo.finish(manifest("chore: local", path))

    assert_stopped(result, f"machine-local paths: {path}")
    assert_untouched(repo, head)


def test_failed_verification_stops_before_staging(repo: Repo) -> None:
    head = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"), FAKE_VERIFY_FAIL="1")

    assert_stopped(result, "verification failed")
    assert_untouched(repo, head)
    assert repo.status() == " M src/app.py\n"


def test_verification_that_changes_a_manifest_path_stops(repo: Repo) -> None:
    head = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"), FAKE_VERIFY_TOUCH=str(repo.root / "src/app.py"))

    assert_stopped(result, "verification changed manifest paths: src/app.py")
    assert_untouched(repo, head)


def test_an_unpushed_local_commit_stops_and_is_listed_not_pushed(repo: Repo) -> None:
    pushed = repo.head()
    repo.write("README.md", "older work\n")
    repo.commit_all("chore: older unpushed work")
    local = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "1 ahead of and 0 behind origin/master")
    assert "chore: older unpushed work" in result.stdout
    assert repo.head() == local
    assert repo.remote_head() == pushed


def test_a_branch_behind_its_upstream_stops(repo: Repo, tmp_path: Path) -> None:
    head = repo.head()
    other = tmp_path / "other"
    repo.git("clone", "--quiet", str(repo.remote), str(other), cwd=tmp_path)
    (other / "README.md").write_text("someone else\n")
    repo.git("commit", "--quiet", "-am", "elsewhere", cwd=other)
    repo.git("push", "--quiet", cwd=other)
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "0 ahead of and 1 behind origin/master")
    assert repo.head() == head
    assert repo.staged() == ""


def test_a_detached_head_stops(repo: Repo) -> None:
    head = repo.head()
    repo.git("switch", "--quiet", "--detach")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "HEAD is detached")
    assert_untouched(repo, head)


def test_a_branch_without_upstream_stops(repo: Repo) -> None:
    head = repo.head()
    repo.git("switch", "--quiet", "-c", "feature")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "branch feature has no upstream")
    assert_untouched(repo, head)


def test_a_git_operation_in_progress_stops(repo: Repo) -> None:
    head = repo.head()
    (repo.root / ".git" / "MERGE_HEAD").write_text(head + "\n")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "a Git operation is in progress (MERGE_HEAD)")
    assert_untouched(repo, head)


def test_a_failing_pre_commit_hook_stops_without_a_commit(repo: Repo) -> None:
    head = repo.head()
    repo.hook("pre-commit", "echo rejected by hook >&2\nexit 1\n")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "rejected by hook")
    assert "Git state: manifest paths staged; nothing committed or pushed" in result.stdout
    assert repo.head() == head
    assert repo.remote_head() == head


def test_a_second_commit_made_during_the_commit_blocks_the_push(repo: Repo, tmp_path: Path) -> None:
    pushed = repo.head()
    marker = tmp_path / "hook-ran"
    repo.hook(
        "post-commit", f'[ -e "{marker}" ] && exit 0\ntouch "{marker}"\ngit commit --quiet --allow-empty -m extra\n'
    )
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "the new commit's parent is not the previous HEAD")
    assert "NOT pushed" in result.stdout
    assert repo.remote_head() == pushed


def test_an_upstream_that_moves_during_the_commit_blocks_the_push(repo: Repo, tmp_path: Path) -> None:
    """Exactly one ahead and zero behind must hold before the push runs."""
    other = tmp_path / "other"
    repo.git("clone", "--quiet", str(repo.remote), str(other), cwd=tmp_path)
    (other / "README.md").write_text("someone else\n")
    repo.git("commit", "--quiet", "-am", "elsewhere", cwd=other)
    clean_env = "env -u GIT_DIR -u GIT_INDEX_FILE -u GIT_WORK_TREE"
    repo.hook("post-commit", f'{clean_env} git -C "{other}" push --quiet\n{clean_env} git fetch --quiet origin\n')
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "expected exactly 1 commit ahead and 0 behind, found 1 ahead and 1 behind")
    assert "NOT pushed" in result.stdout
    assert repo.remote_head() == repo.git("-C", str(other), "rev-parse", "HEAD").strip()


def test_a_post_commit_change_to_the_tree_blocks_the_push(repo: Repo) -> None:
    pushed = repo.head()
    repo.hook("post-commit", 'echo "late edit" >> README.md\n')
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "the working tree is not clean after the commit")
    assert repo.remote_head() == pushed


def test_a_failing_pre_push_hook_leaves_the_commit_local_and_unpushed(repo: Repo) -> None:
    pushed = repo.head()
    repo.hook("pre-push", "exit 1\n")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "git push")
    assert f"Git state: committed locally as {repo.head()[:7]}; NOT pushed" in result.stdout
    assert repo.remote_head() == pushed


def test_a_path_staged_then_deleted_stops_at_the_staged_set_check(repo: Repo) -> None:
    head = repo.head()
    repo.write("src/new_module.py", "NEW = True\n")
    repo.git("add", "src/new_module.py")
    (repo.root / "src/new_module.py").unlink()

    result = repo.finish(manifest("feat: change", "src/new_module.py"))

    assert_stopped(result, "staged paths differ from the manifest: in manifest but not staged: src/new_module.py")
    assert repo.head() == head
    assert repo.remote_head() == head


def test_a_hook_that_stages_another_path_blocks_the_push(repo: Repo) -> None:
    pushed = repo.head()
    repo.hook("pre-commit", "echo extra > extra.txt\ngit add extra.txt\n")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "committed paths differ from the manifest: not in manifest: extra.txt")
    assert "NOT pushed" in result.stdout
    assert repo.remote_head() == pushed


def test_a_hook_that_rewrites_the_message_blocks_the_push(repo: Repo) -> None:
    pushed = repo.head()
    repo.hook("commit-msg", 'echo "rewritten" > "$1"\n')
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "the commit message differs from the manifest")
    assert "NOT pushed" in result.stdout
    assert repo.remote_head() == pushed


def test_unmerged_paths_stop(repo: Repo) -> None:
    """A conflicted `stash apply` (in this temporary repo only) leaves unmerged paths without a merge in progress."""
    head = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")
    repo.git("stash", "push", "--quiet")
    repo.write("src/app.py", "VALUE = 3\n")
    repo.git("add", "src/app.py")
    repo.git("commit", "--quiet", "-m", "local change")
    local = repo.head()
    conflict = subprocess.run(("git", "stash", "apply"), cwd=repo.root, env=repo.env, capture_output=True, check=False)
    assert conflict.returncode != 0

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "unmerged paths: src/app.py")
    assert repo.head() == local
    assert repo.remote_head() == head


def test_a_branch_tracking_a_local_branch_stops(repo: Repo) -> None:
    head = repo.head()
    repo.git("branch", "--quiet", "base")
    repo.git("branch", "--quiet", "--set-upstream-to=base")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert_stopped(result, "branch master tracks a local branch, not a remote")
    assert_untouched(repo, head)


def test_the_push_sends_no_tags(repo: Repo) -> None:
    repo.git("config", "push.followTags", "true")
    repo.git("tag", "-a", "local-only", "-m", "not for the remote")
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(manifest("feat: change", "src/app.py"))

    assert result.returncode == 0, result.stdout
    assert repo.git("--git-dir", str(repo.remote), "tag") == ""


def test_the_repository_ignores_machine_local_settings_and_usage_data() -> None:
    ignored = (Path(__file__).resolve().parents[2] / ".gitignore").read_text().splitlines()

    assert ".claude/settings.local.json" in ignored
    assert ".claude/usage/" in ignored


@pytest.mark.parametrize(
    "text",
    [
        "",
        "path: src/app.py\n",
        "message: feat: change\n",
        "message: feat: change\nmessage: again\npath: src/app.py\n",
        "message: feat: change\npath: src/app.py\npath: src/app.py\n",
        "message: feat: change\npath: /etc/passwd\n",
        "message: feat: change\npath: ../outside.py\n",
        "message: feat: change\npath: ./src/app.py\n",
        "message: feat: change\npath: src/\n",
        "message: feat: change\n- path: src/app.py\n",
        "message:\npath: src/app.py\n",
    ],
)
def test_an_invalid_manifest_exits_before_any_git_change(repo: Repo, text: str) -> None:
    head = repo.head()
    repo.write("src/app.py", "VALUE = 2\n")

    result = repo.finish(text)

    assert result.returncode == 2
    assert result.stdout.startswith("FINISH: INVALID MANIFEST:")
    assert_untouched(repo, head)


@pytest.mark.parametrize(
    "args",
    [
        ("push", "--force", "origin", "master"),
        ("push", "--force-with-lease", "origin", "master"),
        ("push", "-f", "origin", "master"),
        ("push", "origin", "+abc:refs/heads/master"),
        ("push", "origin", ":refs/heads/master"),
        ("push", "--delete", "origin", "master"),
        ("commit", "--amend"),
        ("commit", "--no-verify", "-m", "x"),
        ("commit", "-n", "-m", "x"),
        ("add", "-f", "--", "ignored.txt"),
        ("reset", "--hard"),
        ("restore", "src/app.py"),
        ("stash",),
        ("rebase", "origin/master"),
        ("checkout", "--", "src/app.py"),
        ("clean", "-fd"),
    ],
)
def test_the_git_guard_refuses_forbidden_commands(script: Script, args: tuple[str, ...]) -> None:
    finish_cycle = script("finish_cycle")

    with pytest.raises(finish_cycle.GitPolicyError):
        finish_cycle.check_git_arguments(args)


def test_the_git_guard_treats_arguments_after_the_separator_as_paths(script: Script) -> None:
    finish_cycle = script("finish_cycle")

    finish_cycle.check_git_arguments(("add", "--", "-f", "--force"))
    finish_cycle.check_git_arguments(("commit", "--quiet", "--message=--amend"))
