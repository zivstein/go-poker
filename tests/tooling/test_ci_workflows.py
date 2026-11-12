"""The CI workflows keep the trust boundary: `quality` runs the pull request's code, `ownership` never does.

These are text assertions on `.github/workflows/`, with no YAML dependency. `ownership.yml` runs on
`pull_request_target`, so it must run only `master`'s own check, with read-only permissions and no PR-controlled text
in any shell command.
"""

import re
import shlex
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
CI = (WORKFLOWS / "ci.yml").read_text()
OWNERSHIP = (WORKFLOWS / "ownership.yml").read_text()

type Script = Callable[[str], ModuleType]


def code_lines(text: str) -> list[str]:
    """Lines without full-line comments and trailing comments (none of the workflows quote a '#')."""
    lines = []
    for line in text.splitlines():
        stripped = re.sub(r"\s+#.*$", "", line).rstrip()
        if stripped.strip() and not stripped.lstrip().startswith("#"):
            lines.append(stripped)
    return lines


def indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def block(text: str, key: str) -> list[str]:
    """The lines under a top-level `key:` (without it), up to the next top-level key."""
    lines = code_lines(text)
    start = next(index for index, line in enumerate(lines) if line == f"{key}:")
    body = []
    for line in lines[start + 1 :]:
        if indent(line) == 0:
            break
        body.append(line)
    return body


def child_keys(lines: list[str], depth: int) -> list[str]:
    return [line.strip().split(":")[0] for line in lines if indent(line) == depth and ":" in line]


def run_values(text: str) -> list[str]:
    """Every `run:` value, joined onto one line: the same line, or the block scalar that follows."""
    lines = code_lines(text)
    values = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", line)
        if not match:
            continue
        run_indent = len(match.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
        parts = [match.group(2)] if match.group(2) not in (">", ">-", "|", "|-", "") else []
        for following in lines[index + 1 :]:
            if indent(following) <= run_indent:
                break
            parts.append(following.strip())
        values.append(" ".join(parts))
    return values


def uses_values(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\s*(?:- )?uses:\s*(\S+)", "\n".join(code_lines(text)), re.MULTILINE)]


def test_quality_runs_on_pushes_to_master_and_pull_requests_only() -> None:
    triggers = block(CI, "on")

    assert child_keys(triggers, 2) == ["push", "pull_request"]
    push = triggers[triggers.index("  push:") + 1 : triggers.index("  pull_request:")]
    assert [line.strip() for line in push] == ["branches: [master]"]


def test_quality_never_runs_on_pull_request_target() -> None:
    assert "pull_request_target" not in CI
    assert child_keys(block(CI, "jobs"), 2) == ["quality"]


def test_ownership_triggers_only_on_pull_request_target() -> None:
    assert child_keys(block(OWNERSHIP, "on"), 2) == ["pull_request_target"]
    assert re.search(r"^\s+pull_request:", OWNERSHIP, re.MULTILINE) is None
    assert child_keys(block(OWNERSHIP, "jobs"), 2) == ["ownership"]


def test_ownership_has_read_only_contents_permission_and_nothing_else() -> None:
    assert [line.strip() for line in block(OWNERSHIP, "permissions")] == ["contents: read"]


def test_every_ownership_action_is_pinned_to_a_full_commit_sha() -> None:
    uses = uses_values(OWNERSHIP)

    assert len(uses) == 1 and uses[0].startswith("actions/checkout@")
    assert all(re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", value) for value in uses), uses


def test_ownership_runs_the_base_check_with_arguments_the_script_accepts(
    script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    command = next(value for value in run_values(OWNERSHIP) if "check_ownership.py" in value)
    tokens = shlex.split(command)
    assert tokens[:2] == ["python3", "scripts/check_ownership.py"]

    parsed = script("check_ownership").build_parser().parse_args(tokens[2:])

    assert (parsed.base, parsed.head) == ("HEAD", "FETCH_HEAD")
    assert parsed.branch == "$HEAD_REF"
    assert parsed.base_ref == "$BASE_REF"
    assert parsed.head_repo == "$HEAD_REPO"
    assert parsed.repository == "$REPOSITORY"
    assert command.count("check_ownership.py") == 1
    assert len([token for token in tokens if token.startswith("--")]) == 6


FETCH_COMMAND = 'git fetch --no-tags --quiet origin "refs/pull/${PR_NUMBER}/head"'
CHECK_COMMAND = (
    'python3 scripts/check_ownership.py --base HEAD --head FETCH_HEAD --branch "$HEAD_REF" '
    '--base-ref "$BASE_REF" --head-repo "$HEAD_REPO" --repository "$REPOSITORY"'
)


def top_level_keys(text: str) -> list[str]:
    return [line.split(":")[0] for line in code_lines(text) if indent(line) == 0]


def job_steps(text: str) -> list[list[str]]:
    """The ownership job's steps, each as its code lines (the `- name:` line first)."""
    steps: list[list[str]] = []
    for line in block(text, "jobs"):
        if indent(line) == 6 and line.lstrip().startswith("- "):
            steps.append([])
        if steps and indent(line) >= 6:
            steps[-1].append(line)
    return steps


def step_keys(step: list[str]) -> list[str]:
    first = step[0].lstrip()[2:].split(":")[0]
    return [first] + [line.strip().split(":")[0] for line in step[1:] if indent(line) == 8]


def step_mapping(step: list[str], key: str) -> dict[str, str]:
    """The `key:` mapping of a step, as name to raw value."""
    start = next(index for index, line in enumerate(step) if line.strip() == f"{key}:")
    mapping: dict[str, str] = {}
    for line in step[start + 1 :]:
        if indent(line) <= indent(step[start]):
            break
        name, _, value = line.strip().partition(": ")
        mapping[name] = value
    return mapping


def test_the_ownership_workflow_has_only_the_expected_top_level_and_job_keys() -> None:
    assert top_level_keys(OWNERSHIP) == ["name", "on", "permissions", "jobs"]
    job = [line for line in block(OWNERSHIP, "jobs") if indent(line) == 4]
    assert [line.strip() for line in job] == ["runs-on: ubuntu-latest", "steps:"]


def test_the_ownership_job_has_exactly_checkout_fetch_and_check_steps() -> None:
    steps = job_steps(OWNERSHIP)

    assert [step_keys(step) for step in steps] == [
        ["name", "uses", "with"],
        ["name", "env", "run"],
        ["name", "env", "run"],
    ]
    assert run_values(OWNERSHIP) == [FETCH_COMMAND, CHECK_COMMAND]
    assert step_mapping(steps[0], "with") == {"ref": "master", "fetch-depth": "0", "persist-credentials": "false"}


def test_the_ownership_environment_maps_each_value_to_its_trusted_source() -> None:
    _, fetch, check = job_steps(OWNERSHIP)

    assert step_mapping(fetch, "env") == {"PR_NUMBER": "${{ github.event.pull_request.number }}"}
    assert step_mapping(check, "env") == {
        "HEAD_REF": "${{ github.event.pull_request.head.ref }}",
        "HEAD_REPO": "${{ github.event.pull_request.head.repo.full_name }}",
        "BASE_REF": "${{ github.event.pull_request.base.ref }}",
        "REPOSITORY": "${{ github.repository }}",
    }


def test_the_ownership_job_reruns_whenever_the_pull_request_changes() -> None:
    triggers = block(OWNERSHIP, "on")
    types_line = next(line.strip() for line in triggers if line.strip().startswith("types:"))
    types = set(re.findall(r"[a-z_]+", types_line.removeprefix("types:")))

    assert {"opened", "synchronize", "reopened", "edited"} <= types


def test_quality_has_no_privileged_trigger_secrets_or_write_permissions() -> None:
    assert top_level_keys(CI) == ["name", "on", "jobs"]
    text = "\n".join(code_lines(CI))

    for forbidden in ("secrets.", "write", "pull_request_target", "workflow_run", "issue_comment"):
        assert forbidden not in text, forbidden


def test_quality_installs_both_toolchains_from_their_pins_then_runs_the_one_verification() -> None:
    steps = job_steps(CI)

    assert [step_keys(step) for step in steps] == [
        ["name", "uses"],
        ["name", "uses", "with"],
        ["name", "run"],
        ["name", "run"],
        ["name", "uses", "with"],
        ["name", "working-directory", "run"],
        ["name", "run"],
    ]
    assert run_values(CI) == ["uv python install 3.14", "uv sync --locked", "npm ci", "uv run scripts/verify.py"]
    setup_node = steps[4]
    assert uses_values("\n".join(setup_node)) == ["actions/setup-node@v7"]
    assert step_mapping(setup_node, "with") == {
        "node-version-file": "web/.nvmrc",
        "cache": "npm",
        "cache-dependency-path": "web/package-lock.json",
    }
    assert [line.strip() for line in steps[5] if line.strip().startswith("working-directory:")] == [
        "working-directory: web"
    ]
