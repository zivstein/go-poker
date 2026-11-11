"""`.claude/settings.json` holds only native deny rules for state-changing `git` and `gh` commands.

The settings file is the Permit layer (`docs/ENGINEERING_PROCESS.md`, Enforcement). It registers no hooks: the C5.4b
guard was stopped (`docs/company/C5_4_ENFORCEMENT_RETROSPECTIVE.md`), and adding a hook again is Meta work that changes
these tests. The deny rules must never stop the commands the project relies on.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

SETTINGS = Path(__file__).resolve().parents[2] / ".claude" / "settings.json"
RULE = re.compile(r"Bash\((?P<prefix>[^()*]+?)(?P<wildcard> \*)?\)")

# State-changing commands that must stay denied.
DENIED_COMMANDS = [
    "git add .",
    "git commit",
    "git commit -m x",
    "git commit --dry-run -m native-deny-smoke-test",  # the Owner's live smoke test
    "git push",
    "git push origin master",
    "git merge x",
    "git rebase master",
    "git reset --hard",
    "git restore x",
    "git checkout x",
    "git switch x",
    "git stash",
    "git clean -fd",
    "gh pr create --fill",
    "gh pr merge 1",
    "gh auth token",
]

# Commands the project relies on: no deny rule may stop them.
ALLOWED_COMMANDS = [
    "uv run scripts/verify.py",
    "uv run scripts/verify.py --fix",
    "uv run scripts/usage_report.py",
    "python3 scripts/check_ownership.py --base HEAD --head FETCH_HEAD --branch meta/x --base-ref master",
    "python3 scripts/finish_cycle.py <<'MANIFEST'\nmessage: M8 | C6: x\npath: docs/x.md\nMANIFEST\n",
    "git status",
    "git diff --stat",
    "git log --oneline -5",
    "git worktree list",
]


def reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    assert len(keys) == len(set(keys)), f"duplicate key in {keys}"
    return dict(pairs)


@pytest.fixture(scope="module")
def settings() -> dict[str, Any]:
    data = json.loads(SETTINGS.read_text(), parse_constant=reject_constant, object_pairs_hook=reject_duplicates)
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def deny_rules(settings: dict[str, Any]) -> list[str]:
    rules = settings["permissions"]["deny"]
    assert isinstance(rules, list) and rules
    return rules  # type: ignore[no-any-return]


def rule_matches(rule: str, command: str) -> bool:
    """Whether the rule covers `command`, counting `X *` as covering the bare `X` too (the strictest reading)."""
    match = RULE.fullmatch(rule)
    assert match is not None, rule
    prefix = match["prefix"]
    return command == prefix or (match["wildcard"] is not None and command.startswith(prefix + " "))


def test_the_settings_hold_only_permissions_and_register_no_hooks(settings: dict[str, Any]) -> None:
    assert set(settings) == {"permissions"}


def test_permissions_only_deny_and_never_allow(settings: dict[str, Any]) -> None:
    assert set(settings["permissions"]) == {"deny"}


def test_every_deny_rule_is_a_bash_rule_for_a_git_or_gh_command(deny_rules: list[str]) -> None:
    for rule in deny_rules:
        match = RULE.fullmatch(rule)
        assert match is not None, rule
        assert match["prefix"].split()[0] in {"git", "gh"}, rule
    assert len(deny_rules) == len(set(deny_rules))


@pytest.mark.parametrize("command", DENIED_COMMANDS)
def test_state_changing_commands_are_denied(deny_rules: list[str], command: str) -> None:
    assert [rule for rule in deny_rules if rule_matches(rule, command)]


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_no_deny_rule_covers_the_project_commands(deny_rules: list[str], command: str) -> None:
    assert not [rule for rule in deny_rules if rule_matches(rule, command)]


def test_the_rule_matcher_used_here_understands_both_forms() -> None:
    assert rule_matches("Bash(git add *)", "git add .")
    assert rule_matches("Bash(git add *)", "git add")
    assert not rule_matches("Bash(git add *)", "git addendum")
    assert rule_matches("Bash(git commit)", "git commit")
    assert not rule_matches("Bash(git commit)", "git commit -m x")
