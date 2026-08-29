# Claude Project Instructions

Before beginning any work in this repository, read `progress.md` completely. It is the
required handoff context for the current agent architecture, latest benchmark, known
limitations, prior experiments, and prioritized next steps.

After reading it, inspect `git status` and preserve all existing changes. Consult the
challenge specification and relevant source files for the task, but use `progress.md`
as the starting project map.

After every meaningful code iteration, experiment, evaluator run, or design decision,
update `progress.md` in the same work session. Refresh current status and improvement
priorities, then append an iteration-log entry containing the hypothesis, files
changed, verification commands, before/after metrics, findings, risks, and next action.
Never erase prior accepted, rejected, or reverted iteration history.

If the progress document is stale or conflicts with verified code/results, correct it
from the evidence. Never improve reported scores by modifying the evaluator or public
labels, and never hard-code public target IDs or commit secrets.
