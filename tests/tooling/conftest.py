"""Helpers for the workflow tooling tests under `scripts/`.

Git tests run only in temporary repositories with a local bare remote. Their environment drops every inherited
`GIT_*` variable (a hook running the suite could otherwise point Git at the real repository) and replaces the global
and system Git configuration with an empty one.
"""

import importlib.util
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

FAKE_VERIFY = """\
import os
import pathlib
import sys

touch = os.environ.get("FAKE_VERIFY_TOUCH")
if touch:
    pathlib.Path(touch).write_text("changed by verification\\n")
failing = bool(os.environ.get("FAKE_VERIFY_FAIL"))
print("VERIFY: FAIL" if failing else "VERIFY: PASS")
sys.exit(1 if failing else 0)
"""


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"scripts_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script() -> Callable[[str], ModuleType]:
    return load_script


class Repo:
    """A working clone with an `origin` bare remote, both inside the test's temporary directory."""

    def __init__(self, root: Path, remote: Path, env: dict[str, str]) -> None:
        self.root = root
        self.remote = remote
        self.env = env

    def git(self, *args: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ("git", *args), cwd=cwd or self.root, env=self.env, capture_output=True, text=True, check=True
        )
        return completed.stdout

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def remote_head(self) -> str:
        return self.git("--git-dir", str(self.remote), "rev-parse", "refs/heads/master").strip()

    def status(self) -> str:
        return self.git("status", "--porcelain=v1", "--untracked-files=all")

    def staged(self) -> str:
        return self.git("diff", "--cached", "--name-only")

    def commit_all(self, message: str) -> None:
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)

    def hook(self, name: str, body: str) -> None:
        hook = self.root / ".git" / "hooks" / name
        hook.write_text("#!/bin/sh\n" + body)
        hook.chmod(0o755)

    def finish(self, manifest: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (sys.executable, str(SCRIPTS / "finish_cycle.py")),
            input=manifest,
            cwd=self.root,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.fixture
def git_env(tmp_path: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    empty_config = tmp_path / "empty-gitconfig"
    empty_config.write_text("")
    home = tmp_path / "home"
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


@pytest.fixture
def repo(tmp_path: Path, git_env: dict[str, str]) -> Repo:
    remote = tmp_path / "remote.git"
    subprocess.run(
        ("git", "init", "--quiet", "--bare", "--initial-branch=master", str(remote)), env=git_env, check=True
    )
    root = tmp_path / "work"
    root.mkdir()
    work = Repo(root, remote, git_env)
    work.git("init", "--quiet", "--initial-branch=master")
    work.git("remote", "add", "origin", str(remote))
    work.write(".gitignore", "ignored.txt\n")
    work.write("README.md", "readme\n")
    work.write("src/app.py", "VALUE = 1\n")
    work.write("docs/notes.md", "notes\n")
    work.write("scripts/verify.py", FAKE_VERIFY)
    work.commit_all("initial")
    work.git("push", "--quiet", "--set-upstream", "origin", "master")
    return work
