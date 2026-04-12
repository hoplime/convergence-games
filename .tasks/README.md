# .tasks/

Persistent, git-tracked task plans for non-trivial work. Designed for both human and AI agent authors.

## Purpose

Task plans capture the context, requirements, technical design, and phased implementation steps for a piece of work. They serve as:

- **Alignment documents** — confirm approach with stakeholders before writing code
- **Implementation guides** — detailed enough for an agent to execute with minimal guidance
- **Progress trackers** — checklist items are checked off as work progresses
- **Historical record** — completed plans stay in place, showing what was done and why

## Directory structure

```
.tasks/
  README.md              # This file
  TEMPLATE.md            # Copy this to start a new task plan
  <task-name>/
    plan.md              # The task plan
```

Each task gets its own directory named in **kebab-case** (e.g., `multi-event-support`, `add-event-status-enum`). The directory can hold additional files if needed (diagrams, research notes), but `plan.md` is the primary document.

## Creating a new task

1. Create the directory: `.tasks/<task-name>/`
2. Copy `TEMPLATE.md` into it as `plan.md`
3. Fill in the sections
4. Set `status: ready` when the plan is reviewed and approved

## Plan lifecycle

Status is tracked in YAML frontmatter at the top of `plan.md`:

| Status        | Meaning                                             |
| ------------- | --------------------------------------------------- |
| `draft`       | Plan is being written, not yet ready for review     |
| `ready`       | Plan is reviewed and approved, work has not started |
| `in-progress` | Implementation is underway                          |
| `complete`    | All acceptance criteria met, work is done           |
| `abandoned`   | Plan was dropped — add a note explaining why        |

Completed and abandoned tasks stay in `.tasks/` (no archive directory). The status field distinguishes them from active work.

## Conventions

- **One plan per task** — if a task spawns follow-up work, create a new task directory
- **Check items as you go** — update the checklist after each step, not in batches
- **Commit plan updates** — plan progress should be visible in git history
- **Keep plans concise** — detailed enough to execute, not a design document novel
- **Reference code by path** — include file paths so agents and humans can navigate directly
