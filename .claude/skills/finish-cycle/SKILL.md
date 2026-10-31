---
name: finish-cycle
description: Commit and push already-approved completed work from its closeout manifest.
argument-hint: "[optional commit message]"
disable-model-invocation: true
effort: medium
---

# Finish Cycle

Invocation is the user's explicit approval to commit and push the work in the latest closeout manifest only. It does not authorize pushing older local commits or any other change.

`scripts/finish_cycle.py` performs and checks the whole Git closeout and stops without committing or pushing on anything unexpected. Do not run Git commands that change state yourself.

## Steps

1. Take the closeout manifest from the latest Cycle Report in this conversation. If there is none, or the work changed after that report, stop and say so. Never build a manifest from `git status`.
2. If `$ARGUMENTS` is non-empty, use it exactly as the `message:` line. Otherwise keep the manifest's message.
3. Run the script once, passing the manifest through a quoted heredoc so the shell does not interpret it:

       python3 scripts/finish_cycle.py <<'MANIFEST'
       message: <commit message>
       path: <path>
       MANIFEST

4. If it prints `SESSION COMPLETE`, finish with its final block exactly as printed.
5. If it stops, report its reason and Git state, explain the likely cause from this conversation, and stop. Do not retry with a different manifest and do not repair Git state; the user decides the next step.

Do no further project work after `SESSION COMPLETE`.
