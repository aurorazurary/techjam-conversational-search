# Repository Agent Instructions

These instructions apply to the entire repository.

## Mandatory startup context

Before planning, editing files, running experiments, or answering project-status
questions, read `progress.md` in full. Treat it as the living source of truth for the
current implementation, benchmark, known gaps, rejected approaches, and next work.

Then inspect `git status` so existing user or agent changes are preserved. Read the
specific source/specification files relevant to the task after loading `progress.md`.

If `progress.md` conflicts with verified source code or a fresh evaluator result,
follow the verified evidence and correct `progress.md` in the same iteration.

## Mandatory iteration handoff

After every meaningful implementation, experiment, benchmark, or architectural
decision, update `progress.md` before ending the work session:

- refresh the current status and metrics when they changed;
- update the prioritized improvements and known gaps;
- append a new iteration-log entry with hypothesis, changes, tests, before/after
  metrics, findings, and next action; and
- retain rejected/reverted experiment history instead of deleting it.

Do not claim an iteration is complete without recording the verification commands and
results. Do not hard-code public labels or target IDs, edit the evaluator to improve a
score, or overwrite unrelated working-tree changes.
