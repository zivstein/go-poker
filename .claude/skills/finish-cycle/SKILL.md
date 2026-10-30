---
name: finish-cycle
description: Verify, commit, push, and close already-approved completed work.
argument-hint: "[optional commit message]"
disable-model-invocation: true
model: sonnet
effort: medium
---

# Finish Cycle

Invocation is explicit user approval to commit and push the current approved closeout only. It does not authorize pushing older local commits.

Follow the closeout policy in `docs/ENGINEERING_PROCESS.md`.

## Git Preflight

Before staging or committing:

1. Determine the current branch and its upstream.
2. Fetch the upstream so the comparison is current.
3. Stop if the branch is detached or has no upstream.
4. Stop if the branch is ahead of, behind, or diverged from its upstream. List any pre-existing unpushed commits by hash and message instead of pushing them.

## Closeout

1. Inspect Git state, including untracked files, and confirm only approved work will be committed.
2. Run the standard verification from `CLAUDE.md`.
3. Stage only approved files, by explicit path.
4. If `$ARGUMENTS` is non-empty, use it exactly as the commit message. Otherwise derive a concise Conventional Commit message from the approved changes.
5. Commit.
6. Verify the branch is now exactly one commit ahead of its upstream and that commit is the one just created.
7. Push the current branch normally.
8. Verify the push, the upstream state, and the working tree.

Stop and report instead of committing or pushing when:

- verification fails;
- approved scope is unclear;
- unrelated changes cannot be safely separated;
- Git state is unsafe or does not match the checks above.

Never:

- force-push;
- rewrite history;
- amend;
- reset;
- restore unrelated changes;
- stash unrelated changes;
- skip hooks or checks;
- include unrelated or machine-local files.

Finish with:

    SESSION COMPLETE
    Commit: <hash> <message>
    Branch: <branch>
    Push: <status>
    Working tree: <status>

Do no further project work after `SESSION COMPLETE`.
